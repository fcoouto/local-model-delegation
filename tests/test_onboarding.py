import copy
import importlib.util
import json
from pathlib import Path
from local_model_delegation.store import atomic_json
from tests.support import Fixture, FakeRuntime


class Onboarding(Fixture):
    def module(self):
        self.assertIsNotNone(importlib.util.find_spec('local_model_delegation.onboarding'), 'onboarding module must exist')
        from local_model_delegation import onboarding
        return onboarding

    def setup_policy(self):
        profile = self.profile(); profile.update(schema_version=2, approval=None, qualification_status='needs_assessment', scope=[])
        atomic_json(self.state / 'profiles/fictional.json', profile)
        atomic_json(self.state / 'config.json', {'schema_version': 2, 'routing_enabled': False, 'visibility_enabled': True,
                    'assessment_policy': {'enabled': True, 'owner_reference': 'fixture-standing-consent'}})
        return profile

    def test_discovery_has_no_lifecycle_side_effect(self):
        module = self.module()
        from local_model_delegation.lmstudio import Runtime
        server = FakeRuntime(); self.addCleanup(server.close)
        result = module.discover_models(Runtime(server.endpoint))
        self.assertEqual(len(result), 1)
        self.assertFalse(any(method == 'POST' for method, _ in server.calls))

    def test_discovery_filters_nontext_and_reports_unknown_format(self):
        module = self.module()
        class Runtime:
            def list_models(self):
                return {'models': [{'type':'embedding','key':'embed'}, {'type':'llm','key':'a','format':'gguf'},
                                   {'type':'llm','key':'b','format':'unknown'}]}
        result = module.discover_models(Runtime())
        self.assertEqual([p['model_id'] for p in result], ['a','b'])
        self.assertEqual(result[1]['status'], 'unsupported')

    def test_splash_discovery_can_be_assessed_without_granting_approval(self):
        from unittest.mock import Mock
        module = self.module(); profile = self.setup_policy()
        catalog = json.loads(Path(profile['runtime_catalog']).read_text())
        catalog['models'][0]['format'] = 'splash'
        atomic_json(Path(profile['runtime_catalog']), catalog)
        runtime = Mock()
        runtime.list_models.return_value = {'models': [{'type':'llm','key':profile['model_id'],
            'format':'splash','loaded_instances':[]}]}
        result = module.discover_models(runtime)
        self.assertEqual(result[0]['status'], 'needs_assessment')
        assessment = module.begin_assessment(self.state, 'fictional', 'fixture-standing-consent')
        self.assertEqual(assessment['binding']['runtime']['metadata']['format'], 'splash')
        self.assertIsNone(module._profile(self.state, 'fictional')['approval'])
        self.assertFalse(json.loads((self.state/'config.json').read_text())['routing_enabled'])
        self.assertEqual(module.assessment_report(self.state, assessment['assessment_id'])['recommendation'], 'do_not_approve_yet')

    def test_assessment_cannot_access_project_or_activate_route(self):
        module = self.module(); self.setup_policy()
        assessment = module.begin_assessment(self.state, 'fictional', 'fixture-standing-consent')
        self.assertFalse(json.loads((self.state / 'config.json').read_text())['routing_enabled'])
        self.assertIsNone(json.loads((self.state / 'profiles/fictional.json').read_text())['approval'])
        permit = {'assessment_id': assessment['assessment_id'], 'permit_token': assessment['permit_token']}
        with self.assertRaisesRegex(ValueError, 'assessment_scope_mismatch'):
            module.authorize_assessment(self.state, self.brief(), permit)

    def test_assessment_permit_cannot_submit_normal_task(self):
        module = self.module(); self.setup_policy()
        assessment = module.begin_assessment(self.state, 'fictional', 'fixture-standing-consent')
        self.assertGreaterEqual(len(assessment['trials']), 6)
        trial = assessment['trials'][0]
        permit = {'assessment_id': assessment['assessment_id'], 'permit_token': assessment['permit_token']}
        self.assertEqual(module.authorize_assessment(self.state, trial['brief'], permit)['profile_id'], 'fictional')
        changed = copy.deepcopy(trial['brief']); changed['source_root'] = str(self.project)
        with self.assertRaisesRegex(ValueError, 'assessment_scope_mismatch'): module.authorize_assessment(self.state, changed, permit)

    def test_changed_artifact_invalidates_assessment(self):
        module = self.module(); self.setup_policy()
        assessment = module.begin_assessment(self.state, 'fictional', 'fixture-standing-consent')
        (self.artifact / 'weights.bin').write_bytes(b'changed fixture')
        with self.assertRaisesRegex(ValueError, 'assessment_identity_changed'):
            module.authorize_assessment(self.state, assessment['trials'][0]['brief'],
                {'assessment_id': assessment['assessment_id'], 'permit_token': assessment['permit_token']})

    def test_incomplete_evidence_is_unknown(self):
        module = self.module(); self.setup_policy()
        assessment = module.begin_assessment(self.state, 'fictional', 'fixture-standing-consent')
        report = module.assessment_report(self.state, assessment['assessment_id'])
        self.assertEqual(report['recommendation'], 'do_not_approve_yet')
        self.assertEqual(report['expected_savings'], 'unknown')
        self.assertEqual(report['completed_trials'], 0)

    def test_imported_report_is_not_local_approval(self):
        module = self.module(); profile = self.setup_policy()
        profile['assessment'] = {'recommendation': 'approve', 'passed': True}
        atomic_json(self.state / 'profiles/fictional.json', profile)
        from local_model_delegation.profiles import read_profile_by_id
        with self.assertRaises(ValueError): read_profile_by_id(self.state, 'fictional', 'python_code_change')
        with self.assertRaisesRegex(ValueError, 'assessment_consent_required'):
            module.begin_assessment(self.state, 'fictional', 'unrelated-consent')

    def test_verified_scope_can_be_approved_before_savings_are_known(self):
        module = self.module(); profile = self.setup_policy()
        assessment = module.begin_assessment(self.state, 'fictional', 'fixture-standing-consent')
        assessment['receipts'] = {t['trial_id']: {'passed': True} for t in assessment['trials']}
        atomic_json(self.state/'assessments'/assessment['assessment_id']/'assessment.json', assessment)
        profile['capacity_evidence'] = {'qualified': True}
        atomic_json(self.state/'profiles/fictional.json', profile)
        report = module.assessment_report(self.state, assessment['assessment_id'])
        self.assertEqual(report['recommendation'], 'approve_provisional_scope')
        self.assertEqual(report['expected_savings'], 'unknown')
        self.assertIsNone(module._profile(self.state, 'fictional')['approval'])
        with self.assertRaisesRegex(ValueError, 'owner_confirmation_required'):
            module.approve_assessment(self.state, assessment['assessment_id'], '', report['tested_scope'])
        result = module.approve_assessment(self.state, assessment['assessment_id'],
                                           'fictional-owner-approval', report['tested_scope'])
        self.assertEqual(result, {'status': 'approval_recorded', 'routing_enabled': False})
        approved = module._profile(self.state, 'fictional')
        self.assertEqual(approved['approval']['scope'], report['tested_scope'])
        self.assertNotIn('benefit_evidence', approved)

    def test_unknown_savings_does_not_bypass_quality_capacity_or_identity(self):
        module = self.module(); profile = self.setup_policy()
        assessment = module.begin_assessment(self.state, 'fictional', 'fixture-standing-consent')
        assessment['receipts'] = {t['trial_id']: {'passed': True} for t in assessment['trials']}
        path = self.state/'assessments'/assessment['assessment_id']/'assessment.json'
        atomic_json(path, assessment)
        self.assertEqual(module.assessment_report(self.state, assessment['assessment_id'])['recommendation'], 'do_not_approve_yet')
        profile['capacity_evidence'] = {'qualified': True}
        atomic_json(self.state/'profiles/fictional.json', profile)
        for receipt in assessment['receipts'].values(): receipt['passed'] = False
        atomic_json(path, assessment)
        with self.assertRaisesRegex(ValueError, 'assessment_incomplete'):
            module.approve_assessment(self.state, assessment['assessment_id'], 'fictional-owner-approval', [])
        for receipt in assessment['receipts'].values(): receipt['passed'] = True
        atomic_json(path, assessment)
        (self.artifact/'weights.bin').write_bytes(b'replaced fixture')
        self.assertEqual(module.assessment_report(self.state, assessment['assessment_id'])['tested_scope'], [])
        self.assertIsNone(module._profile(self.state, 'fictional')['approval'])

    def test_trial_receipt_requires_durable_verified_job(self):
        module = self.module(); profile = self.setup_policy()
        assessment = module.begin_assessment(self.state, 'fictional', 'fixture-standing-consent')
        trial = assessment['trials'][0]
        from local_model_delegation.store import Store
        from local_model_delegation.contracts import canonical
        from local_model_delegation.profiles import authorize_job
        store = Store(self.state)
        saved = store.reserve(trial['brief'], profile, self.loaded())
        permit = {'assessment_id':assessment['assessment_id'], 'permit_token':assessment['permit_token']}
        with store.db(write=True) as db:
            db.execute('UPDATE jobs SET route_data=? WHERE job_id=?', (canonical({'assessment':permit}), saved['job_id']))
        self.assertEqual(authorize_job(store, store.job(saved['job_id']))['profile_id'], 'fictional')
        with self.assertRaisesRegex(ValueError, 'trial_not_complete'):
            module.record_trial(self.state, assessment['assessment_id'], {'trial_id':trial['trial_id'], 'job_id':saved['job_id']})
        with self.assertRaisesRegex(ValueError, 'invalid_trial_receipt'):
            module.record_trial(self.state, assessment['assessment_id'], {'trial_id':trial['trial_id'], 'job_id':saved['job_id'], 'passed':True})

    def test_synthetic_fake_runtime_candidate_is_independently_checked(self):
        module = self.module(); profile = self.setup_policy()
        server = FakeRuntime(); self.addCleanup(server.close)
        profile['endpoint'] = server.endpoint
        atomic_json(self.state / 'profiles/fictional.json', profile)
        assessment = module.begin_assessment(self.state, 'fictional', 'fixture-standing-consent')
        trial = assessment['trials'][0]; brief = trial['brief']
        server.answer = json.dumps({'files': {'helper.py':'def transform(text):\n    return text.strip()\n',
            'test_helper.py':brief['files']['test_helper.py']['content']+'    def test_both(self):\n        self.assertEqual(transform(" x "), "x")\n'}, 'summary':'Trim both ends'})
        from local_model_delegation.store import Store
        from local_model_delegation.contracts import canonical
        from local_model_delegation.worker import run_local_attempt
        from local_model_delegation.validation import verify_candidate
        store = Store(self.state)
        saved = store.reserve(brief, profile, {**self.loaded(),'endpoint':server.endpoint})
        permit = {'assessment_id':assessment['assessment_id'], 'permit_token':assessment['permit_token']}
        with store.db(write=True) as db:
            db.execute('UPDATE jobs SET route_data=? WHERE job_id=?', (canonical({'assessment':permit}), saved['job_id']))
        self.assertEqual(run_local_attempt(self.state, saved['attempt_id']), 0)
        self.assertEqual(verify_candidate(self.state, saved['job_id'])['status'], 'accepted')
        from tests.test_scheduler import Scheduler
        from local_model_delegation.capacity import assessment_request_bytes
        timing=store.attempt(saved['attempt_id'])['data']
        baseline={**Scheduler.resources(self),'process_bytes':20*1024**3,'process_identity':'fixture-process','observed_at':timing['submitted_at']-.1}
        samples=[baseline,{**baseline,'observed_at':timing['submitted_at'],'process_bytes':22*1024**3},
                 {**baseline,'observed_at':timing['finished_at']+.1}]
        report = module.record_trial(self.state, assessment['assessment_id'], {'trial_id':trial['trial_id'], 'job_id':saved['job_id'],'memory_samples':samples})
        self.assertEqual(assessment_request_bytes(module._assessment(self.state,assessment['assessment_id'])),3*1024**3)
        with self.assertRaisesRegex(ValueError,'memory_samples_incomplete'):
            module.record_trial(self.state,assessment['assessment_id'],{'trial_id':trial['trial_id'],'job_id':saved['job_id'],
                                'memory_samples':[{**sample,'observed_at':sample['observed_at']+1000} for sample in samples]})
        self.assertEqual(report['completed_trials'], 1)
        self.assertEqual(report['recommendation'], 'do_not_approve_yet')
        module.record_outcome(self.state,saved['job_id'],{'native_usage':{'kind':'tokens','value':10},'coordination_tokens':3,'checking_tokens':7,'fallback_tokens':0,'native_baseline_tokens':100,'onboarding_tokens':0,'latency_seconds':5,'provenance':'fictional comparable trial'})
        self.assertTrue(module._profile(self.state,'fictional')['benefit_evidence']['scope'])
        self.assertFalse(json.loads((self.state / 'config.json').read_text())['routing_enabled'])

    def test_optional_token_uses_named_environment_only(self):
        import os
        from unittest.mock import patch
        from local_model_delegation.lmstudio import Runtime
        with patch.dict(os.environ, {'FIXTURE_RUNTIME_TOKEN':'synthetic-secret'}):
            runtime = Runtime('http://127.0.0.1:1', token_env='FIXTURE_RUNTIME_TOKEN')
            self.assertEqual(runtime.headers['Authorization'], 'Bearer synthetic-secret')
        with self.assertRaisesRegex(ValueError, 'runtime_token_unavailable'):
            Runtime('http://127.0.0.1:1', token_env='FIXTURE_MISSING_TOKEN')

    def test_usage_proxy_is_not_subscription_savings(self):
        module=self.module();self.assertTrue(hasattr(module,'record_outcome'),'record_outcome must exist')
        self.setup_policy()
        from local_model_delegation.store import Store
        profile=module._profile(self.state,'fictional');store=Store(self.state)
        job=store.reserve(self.brief(),profile,None)
        with store.db(write=True) as db:db.execute("UPDATE jobs SET status='accepted'")
        receipt={'native_usage':{'kind':'tokens','value':10},'coordination_tokens':3,'checking_tokens':7,'fallback_tokens':0,
                 'native_baseline_tokens':100,'onboarding_tokens':0,'latency_seconds':5,'provenance':'fictional paired measurement'}
        first=module.record_outcome(self.state,job['job_id'],receipt)
        second=module.record_outcome(self.state,job['job_id'],receipt)
        self.assertEqual(first,second)
        self.assertEqual(first['subscription_savings'],'unknown')
        self.assertEqual(first['usage_proxy_saved_tokens'],90)
        self.assertEqual(first['accepted_tasks'],1)

    def test_failed_outcomes_reduce_routing_scope(self):
        module=self.module();self.assertTrue(hasattr(module,'record_outcome'),'record_outcome must exist')
        from tests import test_scheduler
        fixture=test_scheduler.Scheduler(methodName='test_unknown_benefit_allows_approved_scope');fixture.setUp();self.addCleanup(fixture.doCleanups)
        store,brief,p=fixture.setup_queue();job=store.reserve(brief,p,None)
        with store.db(write=True) as db:db.execute("UPDATE jobs SET status='failed'")
        receipt={'native_usage':{'kind':'unknown','value':None},'coordination_tokens':None,'checking_tokens':None,'fallback_tokens':None,
                 'native_baseline_tokens':None,'onboarding_tokens':None,'latency_seconds':5,'provenance':'fixture failure'}
        module.record_outcome(fixture.state,job['job_id'],receipt)
        from local_model_delegation.profiles import read_profiles
        from local_model_delegation.scheduler import rank_profiles
        self.assertEqual(rank_profiles(brief,read_profiles(fixture.state)),[])

    def test_capacity_record_requires_accepted_local_trial_jobs(self):
        module=self.module();self.assertTrue(hasattr(module,'record_capacity'),'record_capacity must exist')
        self.setup_policy();assessment=module.begin_assessment(self.state,'fictional','fixture-standing-consent')
        from local_model_delegation.store import Store
        trial=assessment['trials'][0];store=Store(self.state);job=store.reserve(trial['brief'],module._profile(self.state,'fictional'),self.loaded())
        receipt={'context_length':8192,'resources':{},'batches':[{'job_ids':[job['job_id']],'request_bytes':1024,'pressure':'normal','swapout_delta_bytes':0}]}
        with self.assertRaisesRegex(ValueError,'capacity_trial_not_accepted'):
            module.record_capacity(self.state,assessment['assessment_id'],receipt)

    def test_onboarding_overhead_is_amortized_before_claiming_benefit(self):
        module=self.module();self.setup_policy()
        from local_model_delegation.store import Store
        store=Store(self.state);job=store.reserve(self.brief(),module._profile(self.state,'fictional'),None)
        with store.db(write=True) as db:db.execute("UPDATE jobs SET status='accepted'")
        receipt={'native_usage':{'kind':'tokens','value':10},'coordination_tokens':3,'checking_tokens':7,'fallback_tokens':0,
                 'native_baseline_tokens':100,'onboarding_tokens':1000,'latency_seconds':5,'provenance':'fictional paired measurement'}
        result=module.record_outcome(self.state,job['job_id'],receipt)
        self.assertEqual(result['usage_proxy_saved_tokens'],-910)
        self.assertFalse(module._profile(self.state,'fictional').get('benefit_evidence',{}).get('credible',False))

    def test_native_fallback_success_does_not_qualify_local_model(self):
        module=self.module();profile=self.setup_policy();assessment=module.begin_assessment(self.state,'fictional','fixture-standing-consent')
        from local_model_delegation.store import Store
        from local_model_delegation.contracts import canonical
        trial=assessment['trials'][0];store=Store(self.state);job=store.reserve(trial['brief'],profile,None)
        permit={'assessment_id':assessment['assessment_id'],'permit_token':assessment['permit_token']}
        with store.db(write=True) as db:
            db.execute("UPDATE jobs SET status='accepted',native_task_id='fictional-native-result',route_data=?",(canonical({'assessment':permit}),))
        module.record_trial(self.state,assessment['assessment_id'],{'trial_id':trial['trial_id'],'job_id':job['job_id']})
        saved=module._assessment(self.state,assessment['assessment_id'])
        self.assertFalse(saved['receipts'][trial['trial_id']]['passed'])

    def test_assessment_failure_cannot_dispatch_native_fallback(self):
        module=self.module();profile=self.setup_policy();assessment=module.begin_assessment(self.state,'fictional','fixture-standing-consent')
        from local_model_delegation.store import Store
        from local_model_delegation.contracts import canonical
        store=Store(self.state);job=store.reserve(assessment['trials'][0]['brief'],profile,None)
        with store.db(write=True) as db:
            db.execute('UPDATE jobs SET route_data=?',(canonical({'assessment':{'assessment_id':assessment['assessment_id'],'permit_token':assessment['permit_token']}}),))
        with self.assertRaisesRegex(ValueError,'assessment_has_no_native_fallback'):store.claim_fallback(job['job_id'])
