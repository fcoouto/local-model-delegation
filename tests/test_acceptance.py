from local_repair.cli import DEFAULT_STATE
from tests.live_acceptance import prepare_native, validate_temporary_state
from tests.support import Fixture


class Acceptance(Fixture):
    def test_refuse_default_state(self):
        with self.assertRaises(ValueError): validate_temporary_state(DEFAULT_STATE)

    def test_preparation_uses_only_fictional_profile(self):
        result = prepare_native(self.root / "native-case")
        self.assertEqual(result["fallback"], {"model": "gpt-6.1-sol", "reasoning_effort": "medium"})
        self.assertTrue(result["may_dispatch"])
        self.assertEqual(result["profile_kind"], "fictional-no-local-model")


class BroadAcceptance(Fixture):
    def test_two_projects_visibility_modes_and_native_reconciliation(self):
        import threading
        import json
        from contextlib import nullcontext
        from unittest.mock import patch
        from tests import test_scheduler,test_delegation
        from local_repair.scheduler import schedule_once
        from local_repair.profiles import model_identity
        from local_repair.worker import run_attempt
        from local_repair.visibility import set_visibility
        from local_repair.validation import prepare_verification,record_verification
        from local_repair.cli import reconcile_native
        from local_repair.store import atomic_json
        from tests.support import FakeRuntime
        for mode in ('enabled','disabled','disconnected','failed'):
            with self.subTest(mode=mode):
                fixture=test_scheduler.Scheduler();fixture.setUp()
                try:
                    store,brief,p=fixture.setup_queue();candidate=test_delegation.Delegation.proposal(fixture,brief)
                    server=FakeRuntime(answer=json.dumps(candidate),delay=.1)
                    try:
                        p['endpoint']=server.endpoint;p['approval']['model_identity']=model_identity(p)
                        atomic_json(fixture.state/'profiles/fictional.json',p)
                        if mode=='disabled':set_visibility(fixture.state,False)
                        before=(fixture.project/'helper.js').read_bytes()
                        one=store.enqueue(brief,brief['fallback']);two=store.enqueue({**brief,'task_key':'second','origin_chat_id':'second-project'},brief['fallback'])
                        threads=[]
                        def start(state,attempt):
                            thread=threading.Thread(target=run_attempt,args=(state,attempt));threads.append(thread);thread.start()
                        with patch('local_repair.worker.start_worker',side_effect=start),patch('local_repair.visibility.atomic_json',side_effect=OSError('fixture')) if mode=='failed' else nullcontext():
                            schedule_once(fixture.state,fixture.resources())
                            self.assertEqual(store.job(two['job_id'])['status'],'waiting')
                            for thread in threads:thread.join(3);self.assertFalse(thread.is_alive())
                            for item in (one,two):
                                if item==two:
                                    schedule_once(fixture.state,fixture.resources())
                                    for thread in threads:thread.join(3)
                                session=prepare_verification(fixture.state,item['job_id'])
                                receipt=test_delegation.Delegation.receipt(fixture,session)
                                self.assertEqual(record_verification(fixture.state,item['job_id'],receipt)['status'],'accepted')
                        self.assertEqual(sum(method=='POST' and path=='/api/v1/chat' for method,path in server.calls),2)
                        self.assertEqual((fixture.project/'helper.js').read_bytes(),before)
                        self.assertEqual(store.enqueue(brief,brief['fallback'])['job_id'],one['job_id'])
                        p['approval']=None;atomic_json(fixture.state/'profiles/fictional.json',p)
                        third=store.enqueue({**brief,'task_key':'native'},brief['fallback']);schedule_once(fixture.state,fixture.resources())
                        claim=store.claim_fallback(third['job_id']);native='/root/'+claim['task_name']
                        reconcile_native(store,third['job_id'],[{'task_name':native}])
                        self.assertFalse(store.claim_fallback(third['job_id'])['may_dispatch'])
                        path=fixture.root/'native.json';path.write_text(json.dumps(candidate))
                        store.record_fallback_candidate(third['job_id'],native,path)
                        session=prepare_verification(fixture.state,third['job_id']);receipt=test_delegation.Delegation.receipt(fixture,session)
                        self.assertEqual(record_verification(fixture.state,third['job_id'],receipt)['status'],'accepted')
                    finally:server.close()
                finally:fixture.doCleanups()
