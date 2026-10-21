import copy
import importlib.util
import time
from unittest.mock import patch
from local_repair.store import Store, atomic_json
from tests.support import Fixture
from tests import test_delegation


class Scheduler(Fixture):
    generic = test_delegation.Delegation.generic

    def setup_queue(self):
        self.assertTrue(hasattr(Store, 'enqueue'), 'enqueue must exist')
        brief = self.generic()
        p = self.profile(); p.update(schema_version=2, qualification_status='qualified', capabilities=['code_change'],
            scope=[{'capability':'code_change','language':'javascript','complexity':'simple','context_bucket':'small','max_input_bytes':100000}],
            benefit_evidence={'credible':True,'native_overhead':10})
        from local_repair.contracts import digest
        p['capacity_evidence']={'qualified':True,'limit':1,'machine_fingerprint':'fixture-machine','settings_digest':digest(p['request_settings']),'artifact_digest':p['artifact']['digest'],'context_length':8192,'request_bytes':1024**3,'batches':3,'median_slowdown':1}
        p['benefit_evidence']['scope']=copy.deepcopy(p['scope'])
        p['approval'].update(scope=copy.deepcopy(p['scope']),capabilities=p['capabilities'])
        atomic_json(self.state / 'config.json', {'schema_version':2,'routing_enabled':True,'visibility_enabled':True})
        atomic_json(self.state / 'profiles/fictional.json', p)
        return Store(self.state), brief, p

    def resources(self):
        return {'physical_bytes':32*1024**3,'available_bytes':20*1024**3,'pressure':'normal','swapout_delta_bytes':0,
                'observed_at':time.time(),'machine_fingerprint':'fixture-machine'}

    def test_two_projects_wait_without_extra_post(self):
        store, brief, p = self.setup_queue()
        first = store.enqueue(brief, brief['fallback'])
        second_brief = {**brief,'origin_chat_id':'other-project'}
        second = store.enqueue(second_brief, second_brief['fallback'])
        self.assertEqual(store.admit(first['job_id'],p,self.loaded(),self.resources())['status'],'reserved')
        self.assertEqual(store.admit(second['job_id'],p,self.loaded(),self.resources())['status'],'waiting')
        self.assertIsNone(store.job(second['job_id'])['attempt_id'])

    def test_repeated_enqueue_reuses_id(self):
        store, brief, p = self.setup_queue()
        first = store.enqueue(brief, brief['fallback'])
        self.assertEqual(store.enqueue(brief, brief['fallback'])['job_id'],first['job_id'])
        with self.assertRaisesRegex(ValueError,'job_conflict'):
            store.enqueue({**brief,'behavior_contract':'changed'},brief['fallback'])

    def test_profile_revoked_while_queued_cannot_submit(self):
        store, brief, p = self.setup_queue(); job = store.enqueue(brief,brief['fallback'])
        revoked = copy.deepcopy(p); revoked['approval']=None
        atomic_json(self.state / 'profiles/fictional.json',revoked)
        with self.assertRaises(ValueError): store.admit(job['job_id'],p,self.loaded(),self.resources())
        self.assertIsNone(store.job(job['job_id'])['attempt_id'])

    def test_queue_deadline_does_not_reset_on_progress(self):
        store, brief, p = self.setup_queue()
        with patch('local_repair.store.time.time',return_value=100): job=store.enqueue(brief,brief['fallback'])
        with patch('local_repair.store.time.time',return_value=131):
            self.assertEqual(store.admit(job['job_id'],p,self.loaded(),self.resources())['reason'],'route_decision_required')
        self.assertEqual(store.job(job['job_id'])['queued_at'],100)
        self.assertEqual(store.job(job['job_id'])['route_data']['wait_until'],130)

    def test_later_arrivals_cannot_starve_waiter(self):
        store, brief, p = self.setup_queue()
        with patch('local_repair.store.time.time',return_value=100): first=store.enqueue(brief,brief['fallback'])
        urgent=copy.deepcopy(brief); urgent['task_key']='urgent';urgent['task_requirements']['urgency']='urgent'
        with patch('local_repair.store.time.time',return_value=401): second=store.enqueue(urgent,urgent['fallback'])
        self.assertEqual(store.waiting_jobs(now=401)[0]['job_id'],first['job_id'])

    def test_queue_fallback_leaves_running_peer_untouched(self):
        store, brief, p = self.setup_queue(); first=store.enqueue(brief,brief['fallback'])
        store.admit(first['job_id'],p,self.loaded(),self.resources())
        second=store.enqueue({**brief,'task_key':'second'},brief['fallback'])
        result=store.decide_wait(second['job_id'],{'action':'fallback','reason':'waiting_cost_exceeds_benefit'})
        self.assertEqual(result['status'],'fallback_required')
        self.assertEqual(store.job(first['job_id'])['status'],'reserved')
        self.assertEqual(result['fallback'],brief['fallback'])

    def test_scheduler_restart_does_not_duplicate_attempt(self):
        store, brief, p = self.setup_queue(); job=store.enqueue(brief,brief['fallback'])
        first=store.admit(job['job_id'],p,self.loaded(),self.resources())
        second=store.admit(job['job_id'],p,self.loaded(),self.resources())
        self.assertEqual(first['attempt_id'],second['attempt_id'])
        with store.db() as db: self.assertEqual(db.execute('SELECT count(*) FROM attempts').fetchone()[0],1)

    def test_source_change_while_waiting_requires_reassessment(self):
        store, brief, p=self.setup_queue(); job=store.enqueue(brief,brief['fallback'])
        (self.project/'helper.js').write_text('unrelated change')
        self.assertEqual(store.admit(job['job_id'],p,self.loaded(),self.resources())['status'],'needs_reassessment')

    def test_unknown_benefit_keeps_native(self):
        self.assertIsNotNone(importlib.util.find_spec('local_repair.scheduler'))
        from local_repair.scheduler import rank_profiles
        store, brief, p=self.setup_queue()
        self.assertEqual(rank_profiles(brief,[p]),['fictional'])
        p.pop('benefit_evidence')
        self.assertEqual(rank_profiles(brief,[p]),[])
