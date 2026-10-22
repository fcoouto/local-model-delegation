import copy
import importlib.util
import time
from local_model_delegation.store import Store
from tests import test_scheduler


from tests.support import Fixture


class Capacity(Fixture):
    generic=test_scheduler.Scheduler.generic
    setup_queue=test_scheduler.Scheduler.setup_queue
    resources=test_scheduler.Scheduler.resources
    def module(self):
        self.assertIsNotNone(importlib.util.find_spec('local_model_delegation.capacity'),'capacity module must exist')
        from local_model_delegation import capacity
        return capacity

    def measured(self,p):
        from local_model_delegation.contracts import digest
        return {**p,'capacity_evidence':{'qualified':True,'limit':2,'machine_fingerprint':'fixture-machine',
                 'settings_digest':digest(p['request_settings']),'artifact_digest':p['artifact']['digest'],
                 'context_length':8192,'request_bytes':4*1024**3,'batches':3,'median_slowdown':1.2}}

    def test_unknown_resource_data_closes_admission(self):
        module=self.module(); store,brief,p=self.setup_queue();p=self.measured(p)
        for key in ('pressure','observed_at'):
            r=self.resources();r[key]=None
            with self.subTest(key=key):self.assertEqual(module.qualified_limit(p,self.loaded(2),r),0)

    def test_disk_size_is_not_parallel_capacity(self):
        module=self.module();store,brief,p=self.setup_queue()
        p.pop('capacity_evidence')
        self.assertEqual(module.qualified_limit(p,self.loaded(20),self.resources()),1)
        self.assertEqual(module.qualified_limit(self.measured(p),self.loaded(20),self.resources()),2)

    def test_changed_machine_or_settings_reverts_to_one_slot(self):
        module=self.module();store,brief,p=self.setup_queue();p=self.measured(p)
        changed=copy.deepcopy(p);changed['request_settings']['max_output_tokens']+=1
        self.assertEqual(module.qualified_limit(changed,self.loaded(2),self.resources()),1)
        r=self.resources();r['machine_fingerprint']='changed'
        self.assertEqual(module.qualified_limit(p,self.loaded(2),r),1)

    def test_two_models_cannot_reserve_same_free_memory(self):
        self.module();store,brief,p=self.setup_queue();r=self.resources();estimate={'bytes':10*1024**3,'non_evicting':True}
        first=store.reserve_load(p,estimate,r)
        other={**p,'model_id':'second-fictional-model'}
        with self.assertRaisesRegex(ValueError,'insufficient_resources'):store.reserve_load(other,estimate,r)
        self.assertEqual(first['operation_id'],store.reserve_load(p,estimate,r)['operation_id'])

    def test_unowned_instance_is_never_unloaded(self):
        module=self.module();store,brief,p=self.setup_queue()
        job=store.reserve(brief,p,self.loaded())
        key=store.attempt(job['attempt_id'])['instance_key']
        self.assertEqual(module.release_idle(self.state,key)['reason'],'instance_not_owned')

    def test_unknown_eviction_behavior_blocks_load(self):
        module=self.module();store,brief,p=self.setup_queue()
        self.assertEqual(module.ensure_loaded(self.state,'fictional')['reason'],'lifecycle_unqualified')
        with store.db() as db:self.assertEqual(db.execute('SELECT count(*) FROM model_operations').fetchone()[0],0)

    def test_lost_load_ack_retains_reservation_without_repost(self):
        self.module();store,brief,p=self.setup_queue();estimate={'bytes':2*1024**3,'non_evicting':True}
        first=store.reserve_load(p,estimate,self.resources())
        with store.db(write=True) as db:db.execute("UPDATE model_operations SET state='uncertain'")
        second=store.reserve_load(p,estimate,self.resources())
        self.assertEqual(first['operation_id'],second['operation_id'])
        self.assertEqual(second['state'],'uncertain')

    def test_measurement_steps_require_three_correct_batches(self):
        module=self.module();store,brief,p=self.setup_queue()
        batches=[{'concurrency':1,'task_seconds':[10],'all_correct':True,'request_bytes':1024**3,'pressure':'normal','swapout_delta_bytes':0} for _ in range(3)]
        batches += [{'concurrency':2,'task_seconds':[14,14],'all_correct':True,'request_bytes':1024**3,'pressure':'normal','swapout_delta_bytes':0} for _ in range(3)]
        self.assertEqual(module.qualify_measurements(p,batches,self.resources(),8192)['limit'],2)
        batches[-1]['all_correct']=False
        self.assertEqual(module.qualify_measurements(p,batches,self.resources(),8192)['limit'],1)

    def test_capacity_drop_preserves_healthy_jobs(self):
        module=self.module();store,brief,p=self.setup_queue();first=store.enqueue(brief,brief['fallback'])
        store.admit(first['job_id'],p,self.loaded(2),self.resources())
        other=store.enqueue({**brief,'task_key':'second'},brief['fallback'])
        pressure=self.resources();pressure['pressure']='critical'
        self.assertEqual(store.admit(other['job_id'],p,self.loaded(2),pressure)['status'],'waiting')
        self.assertEqual(store.job(first['job_id'])['status'],'reserved')

    def test_broad_recovery_does_not_reset_external_instance(self):
        module=self.module();store,brief,p=self.setup_queue();job=store.reserve(brief,p,self.loaded())
        attempt=store.attempt(job['attempt_id'])
        from local_model_delegation.recovery import close_instance,recover_once
        from unittest.mock import Mock
        close_instance(store,attempt['instance_key']);runtime=Mock()
        with self.assertRaisesRegex(ValueError,'instance_not_owned'):recover_once(store,attempt['instance_key'],runtime)
        runtime.unload.assert_not_called();runtime.load.assert_not_called()

    def test_lost_unload_ack_reconciles_without_reposting(self):
        from tests.support import FakeRuntime
        from local_model_delegation.contracts import canonical,digest
        server=FakeRuntime();server.drop_unload_ack=True;self.addCleanup(server.close)
        module=self.module();store,brief,p=self.setup_queue();p['endpoint']=server.endpoint
        job=store.reserve(brief,p,{**self.loaded(),'endpoint':server.endpoint})
        key=store.attempt(job['attempt_id'])['instance_key'];instance=store.instance(key)
        with store.db(write=True) as db:
            db.execute("UPDATE attempts SET state='released'")
            db.execute("INSERT INTO model_operations VALUES ('owned',?,'complete',?)",(digest([server.endpoint,p['model_id']]),canonical({'kind':'load','instance_id':instance['data']['instance_id'],'ownership_verified':True})))
            db.execute('UPDATE instances SET data=? WHERE instance_key=?',(canonical({**instance['data'],'owned_operation_id':'owned'}),key))
        module.release_idle(self.state,key)
        self.assertEqual(module.release_idle(self.state,key)['status'],'released')
        self.assertEqual(server.calls.count(('POST','/api/v1/models/unload')),1)

    def test_loaded_request_does_not_use_load_memory_gate(self):
        module=self.module(); store,brief,p=self.setup_queue()
        resources={**self.resources(),'physical_bytes':48*1024**3,'available_bytes':6*1024**3}
        self.assertEqual(module.qualified_limit(p,self.loaded(),resources),1)
        with self.assertRaisesRegex(ValueError,'insufficient_resources'):
            store.reserve_load(p,{'bytes':1024**3,'non_evicting':True},resources)
        for change in ({'available_bytes':4*1024**3},{'pressure':'warning'},{'swapout_delta_bytes':4096}):
            self.assertEqual(module.qualified_limit(p,self.loaded(),{**resources,**change}),1)

    def test_calibration_counts_only_increment_and_adds_margin(self):
        module=self.module()
        self.assertTrue(hasattr(module,'measure_request_memory'),'request memory calibration is missing')
        base={**self.resources(),'observed_at':100,'process_bytes':20*1024**3,'process_identity':'fixture-process'}
        samples=[base,{**base,'observed_at':101,'process_bytes':21*1024**3},
                 {**base,'observed_at':102,'available_bytes':base['available_bytes']-2*1024**3}]
        measured=module.measure_request_memory(samples)
        self.assertEqual(measured['peak_increment_bytes'],2*1024**3)
        self.assertEqual(measured['request_bytes'],3*1024**3)
        for change in ({'pressure':'warning'},{'swapout_delta_bytes':1},{'process_bytes':None},
                       {'machine_fingerprint':'changed'},{'process_identity':'replacement'},{'observed_at':110}):
            with self.assertRaises(ValueError): module.measure_request_memory([*samples[:2],{**samples[2],**change}])

    def test_unqualified_loaded_assessment_reserves_calibration_headroom(self):
        from tests.test_onboarding import Onboarding
        from local_model_delegation import onboarding
        profile=Onboarding.setup_policy(self)
        assessment=onboarding.begin_assessment(self.state,'fictional','fixture-standing-consent')
        permit={'assessment_id':assessment['assessment_id'],'permit_token':assessment['permit_token']}
        store=Store(self.state); brief=assessment['trials'][0]['brief']
        job=store.enqueue(brief,brief['fallback'],assessment=permit)
        resources={**self.resources(),'physical_bytes':48*1024**3,'available_bytes':6*1024**3}
        self.assertEqual(store.admit(job['job_id'],profile,self.loaded(),resources)['status'],'reserved')
        self.assertGreaterEqual(store.job(job['job_id'])['route_data']['request_bytes'],1024**3)

    def test_worker_rechecks_resources_after_authorization_before_post(self):
        from unittest.mock import patch
        from local_model_delegation.worker import run_local_attempt
        store,brief,p=self.setup_queue()
        job=store.enqueue(brief,brief['fallback'])
        reserved=store.admit(job['job_id'],p,self.loaded(),self.resources())
        with patch('local_model_delegation.capacity.pressure_snapshot',return_value={**self.resources(),'pressure':'critical'}):
            self.assertEqual(run_local_attempt(self.state,reserved['attempt_id']),1)
        current=store.job(job['job_id'])
        self.assertEqual(current['reason'],'resources_changed_before_post')
        self.assertEqual(store.attempt(reserved['attempt_id'])['state'],'released')

    def test_distinct_loaded_instances_do_not_share_a_free_memory_estimate(self):
        from tests.test_onboarding import Onboarding
        from local_model_delegation import onboarding
        from local_model_delegation.store import atomic_json
        profile=Onboarding.setup_policy(self)
        store=Store(self.state)
        for index in range(2):
            identifier='model'+str(index)
            current={**profile,'profile_id':identifier}
            atomic_json(self.state/'profiles'/(identifier+'.json'),current)
            assessment=onboarding.begin_assessment(self.state,identifier,'fixture-standing-consent')
            permit={'assessment_id':assessment['assessment_id'],'permit_token':assessment['permit_token']}
            brief=assessment['trials'][0]['brief']
            job=store.enqueue(brief,brief['fallback'],assessment=permit)
            resources={**self.resources(),'physical_bytes':48*1024**3,'available_bytes':5*1024**3}
            result=store.admit(job['job_id'],current,{**self.loaded(),'instance_id':identifier},resources)
            self.assertEqual(result['status'],'reserved')

    def test_capacity_record_refreshes_resources_after_slow_artifact_checks(self):
        from unittest.mock import patch
        from tests.test_onboarding import Onboarding
        from local_model_delegation import onboarding
        from local_model_delegation.contracts import canonical
        profile=Onboarding.setup_policy(self)
        assessment=onboarding.begin_assessment(self.state,'fictional','fixture-standing-consent')
        permit={'assessment_id':assessment['assessment_id'],'permit_token':assessment['permit_token']}
        store=Store(self.state);batches=[]
        for trial in assessment['trials'][:3]:
            job=store.reserve(trial['brief'],profile,self.loaded())
            with store.db(write=True) as db:
                db.execute("UPDATE jobs SET status='accepted',route_data=? WHERE job_id=?",(canonical({'assessment':permit}),job['job_id']))
                db.execute("UPDATE attempts SET state='complete',data=? WHERE attempt_id=?",(canonical({'submitted_at':1,'finished_at':2}),job['attempt_id']))
            batches.append({'job_ids':[job['job_id']],'request_bytes':1024**3,'pressure':'normal','swapout_delta_bytes':0})
        clock=[100]
        resources={**self.resources(),'observed_at':100}
        authorize=onboarding.authorize_assessment
        def slow_authorize(*args):
            result=authorize(*args);clock[0]+=10;return result
        with patch('local_model_delegation.capacity.time.time',side_effect=lambda:clock[0]), \
             patch('local_model_delegation.onboarding.authorize_assessment',side_effect=slow_authorize), \
             patch('local_model_delegation.capacity.machine_snapshot',side_effect=lambda:{**resources,'observed_at':clock[0]}):
            receipt={'context_length':8192,'resources':resources,'batches':batches}
            evidence=onboarding.record_capacity(self.state,assessment['assessment_id'],receipt)
            clock[0]=100
            with patch('local_model_delegation.capacity.machine_snapshot',side_effect=lambda:{**resources,'observed_at':clock[0],'pressure':'warning'}):
                with self.assertRaisesRegex(ValueError,'resources_unqualified'):
                    onboarding.record_capacity(self.state,assessment['assessment_id'],receipt)
            clock[0]=200
            with self.assertRaisesRegex(ValueError,'resources_unqualified'):
                onboarding.record_capacity(self.state,assessment['assessment_id'],receipt)
        self.assertTrue(evidence['qualified'])
        self.assertEqual(evidence['limit'],1)
