"""Real loopback lifecycle requests; fictional models and disposable history."""
import copy
import importlib
import time
from unittest.mock import patch
from tests.support import Fixture, FakeRuntime
from tests import test_recovery
from local_model_delegation.store import Store, atomic_json
from local_model_delegation.contracts import canonical, digest
from local_model_delegation.worker import ownership


class Lifecycle(Fixture):
    prepare = test_recovery.Recovery.prepare

    def module(self):
        self.assertIsNotNone(importlib.util.find_spec('local_model_delegation.lifecycle'))
        return importlib.import_module('local_model_delegation.lifecycle')

    def pause(self):
        atomic_json(self.state/'config.json', self.config(enabled=False))

    def reset_fixture(self):
        server, store, job, key = self.prepare()
        with store.db(write=True) as db:
            db.execute("UPDATE jobs SET status='failed',reason='native_verification_failed' WHERE job_id=?",(job['job_id'],))
        self.pause()
        return server, store, job, key

    def test_reset_fences_only_uncertain_generation_preserves_job_and_updates(self):
        api=self.module(); server,store,job,key=self.reset_fixture()
        original=store.job(job['job_id'])
        result=api.reset_external(self.state,key,'fictional-owner-reset')
        self.assertEqual(result['status'],'retired')
        self.assertEqual(store.job(job['job_id']),original)
        attempt=store.attempt(job['attempt_id'])
        self.assertEqual(attempt['state'],'released')
        self.assertEqual(attempt['data']['reset_resolution']['previous_state'],'uncertain')
        self.assertEqual(store.instance(key)['generation'],1)
        self.assertFalse(store.transition(job['attempt_id'],0,'released','submitting',{}))
        self.assertEqual(api.reset_external(self.state,key,'fictional-owner-reset'),result)
        self.assertEqual([c for c in server.calls if c[0]=='POST'],[('POST','/api/v1/models/unload')])
        from local_model_delegation.package import prepare_update
        self.assertEqual(prepare_update(self.state)['status'],'ready')

    def test_reset_reconciles_lost_ack_from_verified_absence_without_reposting(self):
        api=self.module(); server,store,job,key=self.reset_fixture(); server.drop_unload_ack=True
        self.assertEqual(api.reset_external(self.state,key,'owner')['status'],'retired')
        self.assertEqual(api.reset_external(self.state,key,'owner')['status'],'retired')
        self.assertEqual(server.calls.count(('POST','/api/v1/models/unload')),1)

    def test_owner_reset_accepts_changed_scope_without_changing_approval(self):
        api=self.module(); server,store,job,key=self.reset_fixture()
        from local_model_delegation.profiles import read_profiles
        profile=read_profiles(self.state)[0]
        profile['scope'][0]['max_input_bytes']=90000
        profile['approval']['scope']=copy.deepcopy(profile['scope'])
        profile['approval']['owner_reference']='new-fictional-scope-approval'
        atomic_json(self.state/'profiles/fictional.json',profile)
        original=store.instance(key)['data']['profile']
        result=api.reset_external(self.state,key,'owner-reset-after-scope-change')
        self.assertEqual(result['status'],'retired')
        self.assertEqual(read_profiles(self.state)[0],profile)
        self.assertEqual(store.instance(key)['data']['profile'],original)
        self.assertEqual(store.attempt(job['attempt_id'])['state'],'released')
        self.assertEqual(server.requests,[{'instance_id':'fixture-instance'}])

    def test_changed_scope_never_bypasses_reset_runtime_binding(self):
        for field,value in [('endpoint','http://127.0.0.1:2'),('model_id','other'),
                            ('request_settings',{'max_output_tokens':2048,'reasoning':'off','temperature':1})]:
            with self.subTest(field=field):
                api=self.module(); server,store,job,key=self.reset_fixture()
                before=store.instance(key)
                data=copy.deepcopy(before['data'])
                data['profile']['approval']['owner_reference']='older-scope-approval'
                data['profile'][field]=value
                with store.db(write=True) as db:
                    db.execute('UPDATE instances SET data=? WHERE instance_key=?',(canonical(data),key))
                original=store.instance(key)
                with self.assertRaisesRegex(ValueError,'approval_changed'):
                    api.reset_external(self.state,key,'owner-reset')
                self.assertEqual(store.instance(key),original)
                self.assertEqual(store.attempt(job['attempt_id'])['state'],'uncertain')
                self.assertFalse(any(c[0]=='POST' for c in server.calls))

    def test_changed_scope_preserves_historical_approval_identity_guard(self):
        api=self.module(); server,store,job,key=self.reset_fixture()
        data=copy.deepcopy(store.instance(key)['data'])
        data['profile']['approval']['owner_reference']='older-scope-approval'
        data['profile']['approval']['model_identity']['indexed_identifier']='old-runtime-binding'
        with store.db(write=True) as db:
            db.execute('UPDATE instances SET data=? WHERE instance_key=?',(canonical(data),key))
        before=store.instance(key)
        with self.assertRaisesRegex(ValueError,'approval_changed'):
            api.reset_external(self.state,key,'owner-reset')
        self.assertEqual(store.instance(key),before)
        self.assertEqual(store.attempt(job['attempt_id'])['state'],'uncertain')
        self.assertFalse(any(c[0]=='POST' for c in server.calls))

    def test_reset_requires_pause_owner_and_no_observer(self):
        api=self.module(); server,store,job,key=self.reset_fixture()
        with self.assertRaisesRegex(ValueError,'owner_reference_required'):
            api.reset_external(self.state,key,'')
        atomic_json(self.state/'config.json',self.config(enabled=True))
        with self.assertRaisesRegex(ValueError,'admission_must_be_disabled'):
            api.reset_external(self.state,key,'owner')
        self.pause()
        with ownership(store,'attempt-'+job['attempt_id']):
            with self.assertRaisesRegex(ValueError,'observer_active'):
                api.reset_external(self.state,key,'owner')
        self.assertFalse(any(c[0]=='POST' for c in server.calls))
        self.assertEqual(store.attempt(job['attempt_id'])['state'],'uncertain')

    def test_reset_protects_healthy_peer(self):
        api=self.module(); server,store,job,key=self.reset_fixture()
        p=store.job(job['job_id'])['profile']
        other=store.reserve(self.brief('healthy'),p,{**self.loaded(),'endpoint':server.endpoint,'instance_id':'other'})
        self.assertEqual(other['status'],'reserved')
        with self.assertRaisesRegex(ValueError,'endpoint_busy'):
            api.reset_external(self.state,key,'owner')
        self.assertFalse(any(c[0]=='POST' for c in server.calls))

    def test_ambiguous_reset_never_reposts_and_read_only_resume_can_settle(self):
        api=self.module(); server,store,job,key=self.reset_fixture()
        from local_model_delegation.lmstudio import Runtime
        with patch.object(Runtime,'unload',side_effect=OSError('lost before acknowledgement')):
            result=api.reset_external(self.state,key,'owner')
        self.assertEqual(result['status'],'uncertain')
        self.assertEqual(api.reset_external(self.state,key,'owner')['status'],'uncertain')
        self.assertFalse(any(c[0]=='POST' for c in server.calls))
        server.loaded=False
        self.assertEqual(api.reset_external(self.state,key,'owner')['status'],'retired')

    def test_malformed_discovery_is_not_absence_and_retired_flag_is_not_evidence(self):
        api=self.module(); server,store,job,key=self.reset_fixture()
        from local_model_delegation.lmstudio import Runtime
        with patch.object(Runtime,'list_models',return_value={'models':[{'key':'fictional-model'}]}):
            with self.assertRaisesRegex(ValueError,'invalid_model_list'):
                api.reset_external(self.state,key,'owner')
        self.assertFalse(any(c[0]=='POST' for c in server.calls))
        from local_model_delegation.profiles import _quiescent
        with store.db(write=True) as db:
            data=store.instance(key)['data'];data['recovery_phase']='retired'
            db.execute("UPDATE instances SET data=? WHERE instance_key=?",(canonical(data),key))
            db.execute("UPDATE attempts SET state='released'")
        with store.db() as db:
            with self.assertRaisesRegex(ValueError,'unresolved_work'):_quiescent(db)

    def loading_fixture(self):
        api=self.module(); server=FakeRuntime();self.addCleanup(server.close)
        p=self.profile();p['endpoint']=server.endpoint;self.write_config(p,enabled=False)
        api.configure_loading(self.state,'fictional','fictional-owner-load',8192)
        server.loaded=False
        return api,server,Store(self.state),p

    def pressure(self):
        return patch('local_model_delegation.capacity.pressure_snapshot',return_value={'pressure':'normal','observed_at':time.time()})

    def test_load_binds_actual_discovery_without_inference_or_routing(self):
        api,server,store,p=self.loading_fixture()
        with self.pressure(): result=api.ensure_loaded(self.state,'fictional')
        self.assertEqual(result['status'],'loaded')
        self.assertEqual(result['loaded']['instance_id'],'fixture-instance')
        key=digest([server.endpoint,'fictional-model','fixture-instance'])
        owned=store.instance(key)['data']['owned_operation_id']
        self.assertEqual(server.requests,[{'model':'fictional-model','context_length':8192,'echo_load_config':True}])
        with self.pressure(): self.assertEqual(api.ensure_loaded(self.state,'fictional')['status'],'loaded')
        self.assertEqual(store.instance(key)['data'].get('owned_operation_id'),owned)
        self.assertEqual(server.calls.count(('POST','/api/v1/models/load')),1)
        from local_model_delegation.profiles import read_config
        self.assertFalse(read_config(self.state)['routing_enabled'])
        with store.db() as db:self.assertEqual(db.execute('SELECT count(*) FROM attempts').fetchone()[0],0)

    def test_load_refuses_peer_critical_pressure_and_changed_approval(self):
        api,server,store,p=self.loading_fixture();server.peer_loaded=True
        with self.pressure(),self.assertRaisesRegex(ValueError,'runtime_not_empty'):
            api.ensure_loaded(self.state,'fictional')
        server.peer_loaded=False
        with patch('local_model_delegation.capacity.pressure_snapshot',return_value={'pressure':'critical','observed_at':time.time()}):
            with self.assertRaisesRegex(ValueError,'resources_unavailable'):api.ensure_loaded(self.state,'fictional')
        changed=copy.deepcopy(p);changed['approval']['owner_reference']='changed'
        atomic_json(self.state/'profiles/fictional.json',changed)
        with self.pressure(),self.assertRaisesRegex(ValueError,'loading_consent_required'):
            api.ensure_loaded(self.state,'fictional')
        self.assertFalse(any(c[0]=='POST' for c in server.calls))

    def test_ambiguous_load_holds_endpoint_even_when_model_appears(self):
        api,server,store,p=self.loading_fixture();server.drop_load_ack=True
        with self.pressure():result=api.ensure_loaded(self.state,'fictional')
        self.assertEqual(result['status'],'uncertain')
        with self.pressure():self.assertEqual(api.ensure_loaded(self.state,'fictional')['status'],'uncertain')
        self.assertEqual(server.calls.count(('POST','/api/v1/models/load')),1)
        result=store.reserve(self.brief(),p,{**self.loaded(),'endpoint':server.endpoint})
        self.assertIsNone(result['attempt_id'])

    def test_reset_then_reload_reuses_name_but_not_old_generation(self):
        api=self.module();server,store,job,key=self.reset_fixture()
        api.reset_external(self.state,key,'owner')
        api.configure_loading(self.state,'fictional','owner',8192)
        with self.pressure(): result=api.ensure_loaded(self.state,'fictional')
        self.assertEqual(result['status'],'loaded')
        instance=store.instance(key)
        self.assertEqual(instance['state'],'ready');self.assertEqual(instance['generation'],1)
        self.assertEqual(store.attempt(job['attempt_id'])['generation'],0)
        self.assertEqual(store.job(job['job_id'])['status'],'failed')

    def test_scheduler_loads_approved_model_once_before_reserving(self):
        api,server,store,p=self.loading_fixture()
        from local_model_delegation.profiles import read_config
        config=read_config(self.state);config['routing_enabled']=True;atomic_json(self.state/'config.json',config)
        brief=self.brief();job=store.enqueue(brief,brief['fallback'])
        from local_model_delegation.scheduler import schedule_once
        with self.pressure(),patch('local_model_delegation.worker.start_worker'):
            schedule_once(self.state)
        self.assertEqual(store.job(job['job_id'])['status'],'reserved')
        self.assertEqual(server.calls.count(('POST','/api/v1/models/load')),1)
        self.assertFalse(any(c[1]=='/api/v1/chat' for c in server.calls))

    def test_capacity_entrypoint_and_cli_expose_supported_loading(self):
        api,server,store,p=self.loading_fixture()
        from local_model_delegation.capacity import ensure_loaded
        with self.pressure():self.assertEqual(ensure_loaded(self.state,'fictional')['status'],'loaded')
        import subprocess,sys
        from tests import REPO_ROOT
        result=subprocess.run([sys.executable,'-B',str(REPO_ROOT/'delegate.py'),'--state-dir',str(self.state),
                               'models','load','--profile-id','fictional'],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertEqual(server.calls.count(('POST','/api/v1/models/load')),1)

    def test_read_only_load_reconciliation_does_not_invent_ownership(self):
        api,server,store,p=self.loading_fixture();server.drop_load_ack=True
        with self.pressure():result=api.ensure_loaded(self.state,'fictional')
        self.assertEqual(result['status'],'uncertain')
        self.assertTrue(hasattr(api,'reconcile_load'))
        result=api.reconcile_load(self.state,result['operation_id'])
        self.assertEqual(result['status'],'loaded')
        self.assertFalse(result['ownership_verified'])
        with store.db() as db:
            row=db.execute('SELECT data FROM model_operations WHERE operation_id=?',(result['operation_id'],)).fetchone()
            from local_model_delegation.contracts import load_json
            self.assertFalse(load_json(row['data'])['ownership_verified'])
        self.assertEqual(server.calls.count(('POST','/api/v1/models/load')),1)

    def test_reset_never_unloads_an_unrelated_loaded_peer(self):
        api=self.module();server,store,job,key=self.reset_fixture();server.peer_loaded=True
        result=api.reset_external(self.state,key,'owner')
        self.assertEqual(result['status'],'retired');self.assertTrue(server.peer_loaded)
        self.assertEqual(server.requests,[{'instance_id':'fixture-instance'}])

    def test_changed_artifact_and_load_configuration_do_not_become_owned(self):
        api,server,store,p=self.loading_fixture()
        server.parallel=2
        with self.pressure():result=api.ensure_loaded(self.state,'fictional')
        self.assertEqual(result['status'],'uncertain')
        self.assertEqual(result['reason'],'loaded_configuration_mismatch')
        (self.artifact/'weights.bin').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'model_not_approved'):
            api.reconcile_load(self.state,result['operation_id'])

    def test_malformed_load_ack_is_uncertain_not_success_or_unhandled_error(self):
        api,server,store,p=self.loading_fixture()
        from local_model_delegation.lmstudio import Runtime
        original=Runtime.load
        def malformed(runtime, body):
            original(runtime, body)
            return []
        with self.pressure(),patch.object(Runtime,'load',malformed):
            result=api.ensure_loaded(self.state,'fictional')
        self.assertEqual(result['status'],'uncertain')
        self.assertEqual(server.calls.count(('POST','/api/v1/models/load')),1)

    def test_load_reconciliation_replay_preserves_completed_receipt(self):
        api,server,store,p=self.loading_fixture();server.drop_load_ack=True
        with self.pressure():pending=api.ensure_loaded(self.state,'fictional')
        api.reconcile_load(self.state,pending['operation_id'])
        with store.db() as db:
            before=tuple(db.execute('SELECT * FROM model_operations').fetchone())
        api.reconcile_load(self.state,pending['operation_id'])
        with store.db() as db:self.assertEqual(tuple(db.execute('SELECT * FROM model_operations').fetchone()),before)
