import importlib.util
import json
from unittest.mock import patch
from local_model_delegation.store import Store,atomic_json
from tests import test_scheduler
from tests.support import Fixture


class Visibility(Fixture):
    generic=test_scheduler.Scheduler.generic
    setup_queue=test_scheduler.Scheduler.setup_queue
    resources=test_scheduler.Scheduler.resources

    def module(self):
        self.assertIsNotNone(importlib.util.find_spec('local_model_delegation.visibility'),'visibility module must exist')
        from local_model_delegation import visibility
        return visibility

    def test_visibility_defaults_on_while_routing_stays_off(self):
        module=self.module()
        self.assertTrue(module.visibility_status(self.state)['enabled'])
        self.assertFalse(self.state.exists())
        module.set_visibility(self.state,False)
        self.assertFalse(json.loads((self.state/'config.json').read_text())['routing_enabled'])

    def test_visibility_toggle_preserves_routing_and_jobs(self):
        module=self.module();store,brief,p=self.setup_queue();job=store.enqueue(brief,brief['fallback']);before=store.job(job['job_id'])
        module.publish_visibility(self.state)
        self.assertTrue((self.state/'visibility/status.json').exists())
        module.set_visibility(self.state,False);module.publish_visibility(self.state)
        self.assertFalse((self.state/'visibility/status.json').exists())
        self.assertEqual(store.job(job['job_id']),before)
        self.assertTrue(json.loads((self.state/'config.json').read_text())['routing_enabled'])

    def test_visibility_redacts_payloads_and_raw_errors(self):
        module=self.module();store,brief,p=self.setup_queue();brief['behavior_contract']='SECRET_CANARY';job=store.enqueue(brief,brief['fallback'])
        store.decide_wait(job['job_id'],{'action':'fallback','reason':'SECRET_CANARY'})
        module.publish_visibility(self.state)
        text=(self.state/'visibility/status.json').read_text()
        self.assertNotIn('SECRET_CANARY',text);self.assertNotIn(str(self.project),text);self.assertNotIn('trimStart',text)
        self.assertNotIn('fallback_native_task_id',json.loads(text)['jobs'][0])

    def test_snapshot_rewrite_does_not_refresh_job_evidence(self):
        module=self.module();store,brief,p=self.setup_queue();store.enqueue(brief,brief['fallback'])
        module.publish_visibility(self.state);first=json.loads((self.state/'visibility/status.json').read_text())
        module.publish_visibility(self.state);second=json.loads((self.state/'visibility/status.json').read_text())
        self.assertEqual(first['jobs'][0]['observed_at'],second['jobs'][0]['observed_at'])
        self.assertEqual(first['jobs'][0]['job_id'],second['jobs'][0]['job_id'])

    def test_candidate_label_is_awaiting_verification(self):
        module=self.module()
        value=module.build_visibility_snapshot([{'job_id':'x','status':'candidate_ready','profile':{},'brief':{'origin_chat_id':'chat','source_root':'/fixture','capability':'file_summary'},'route_data':{}}],100)
        self.assertEqual(value['jobs'][0]['label'],'Awaiting verification')

    def test_export_failure_does_not_change_task_outcome(self):
        module=self.module();store,brief,p=self.setup_queue();job=store.enqueue(brief,brief['fallback'])
        with patch.object(module,'atomic_json',side_effect=OSError('fixture export failure')):
            self.assertEqual(store.decide_wait(job['job_id'],{'action':'fallback','reason':'model_unavailable'})['status'],'fallback_required')

    def test_visibility_cannot_follow_symlink_outside_state(self):
        module=self.module();store,brief,p=self.setup_queue();store.enqueue(brief,brief['fallback'])
        outside=self.root/'outside';outside.mkdir()
        import shutil
        shutil.rmtree(self.state/'visibility',ignore_errors=True)
        (self.state/'visibility').symlink_to(outside)
        self.assertEqual(module.publish_visibility(self.state)['export_state'],'error')
        self.assertFalse((outside/'status.json').exists())

    def test_disable_wins_over_racing_publisher(self):
        import threading
        module=self.module();store,brief,p=self.setup_queue();store.enqueue(brief,brief['fallback'])
        ready=threading.Event();results=[]
        def publish():ready.set();results.append(module.publish_visibility(self.state))
        with module._lock(self.state):
            worker=threading.Thread(target=publish);worker.start();ready.wait(2)
            config=json.loads((self.state/'config.json').read_text());config['visibility_enabled']=False
            atomic_json(self.state/'config.json',config)
            (self.state/'visibility/status.json').unlink(missing_ok=True)
        worker.join(2)
        self.assertFalse(worker.is_alive());self.assertFalse(results[0]['enabled'])
        self.assertFalse((self.state/'visibility/status.json').exists())

    def test_forged_export_cannot_change_control_state(self):
        module=self.module();store,brief,p=self.setup_queue();job=store.enqueue(brief,brief['fallback'])
        atomic_json(self.state/'visibility/status.json',{'schema_version':1,'generated_at':0,'jobs':[{'state':'accepted'}]})
        module.visibility_status(self.state)
        self.assertEqual(store.job(job['job_id'])['status'],'waiting')
