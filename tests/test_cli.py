import json
import subprocess
import sys
from unittest.mock import patch
from pathlib import Path
from local_model_delegation.cli import reconcile_native
from local_model_delegation.store import Store
from tests.support import Fixture, FakeRuntime, REPO_ROOT, FIXED, SUPPLIED, ADDED


class CLI(Fixture):
    def invoke(self, *args):
        result = subprocess.run([sys.executable, "-B", str(REPO_ROOT / "delegate.py"), "--state-dir", str(self.state), *args], capture_output=True, text=True)
        self.assertIn(result.returncode, (0, 2), result.stderr)
        return json.loads(result.stdout)

    def test_assessment_choices_are_offline_and_do_not_create_state(self):
        result = self.invoke('assessment', 'choices')
        self.assertEqual(result['total_trials'], 36)
        self.assertFalse(self.state.exists())

    def test_assessment_arguments_reject_missing_and_unrelated_flags(self):
        cases = [('prepare', '--profile-id', 'fictional'),
                 ('consent', '--assessment-id', 'a' * 32),
                 ('pause', '--assessment-id', 'a' * 32, '--profile-id', 'fictional'),
                 ('choices', '--check-current'), ('report',)]
        for args in cases:
            with self.subTest(args=args):
                self.assertEqual(self.invoke('assessment', *args)['reason'], 'invalid_assessment_arguments')
                self.assertFalse(self.state.exists())

    def test_assessment_projects_is_offline_and_accepts_repeated_repository_selection(self):
        for name in ('backend', 'frontend'):
            subprocess.run(['git', 'init', str(self.project/name)], check=True, capture_output=True)
        result = self.invoke('assessment', 'projects', '--project', str(self.project),
                             '--owner-reference', 'owner', '--repository', 'backend', '--repository', 'frontend')
        self.assertEqual(len(result['selected']), 2)
        self.assertFalse(self.state.exists())
        for args in [('projects', '--project', str(self.project)),
                     ('choices', '--repository', 'backend')]:
            self.assertEqual(self.invoke('assessment', *args)['reason'], 'invalid_assessment_arguments')
            self.assertFalse(self.state.exists())

    def busy(self, fallback=None):
        server = FakeRuntime()
        self.addCleanup(server.close)
        p = self.profile()
        p["endpoint"] = server.endpoint
        p['qualification_status'] = 'needs_assessment'
        if fallback: p["fallback"] = fallback
        self.write_config(p)
        store = Store(self.state)
        store.reserve(self.brief("occupier"), p, {**self.loaded(), "endpoint": server.endpoint})
        path = self.root / "brief.json"
        brief=self.brief("request"); brief["fallback"]=p["fallback"]
        path.write_text(json.dumps(brief))
        return server, store, path

    def test_unqualified_model_emits_fallback_without_local_post(self):
        server, store, path = self.busy()
        result = self.invoke("submit", "--brief", str(path))
        self.assertEqual(result["status"], "fallback_required")
        self.assertEqual(result["reason"], "no_qualified_model")
        self.assertEqual(result["fallback"], {"model": "gpt-6.1-sol", "reasoning_effort": "medium"})
        self.assertFalse(any(method == "POST" for method, _ in server.calls))

    def test_native_fallback_is_not_qwen_default(self):
        fallback = {"model": "owner-other-model", "reasoning_effort": "high"}
        server, store, path = self.busy(fallback)
        result = self.invoke("submit", "--brief", str(path))
        self.assertEqual(result["fallback"], fallback)

    def test_claim_attach_is_idempotent(self):
        store = Store(self.state)
        job = store.reserve(self.brief(), self.profile(), None)
        first, second = store.claim_fallback(job["job_id"]), store.claim_fallback(job["job_id"])
        self.assertEqual(first["dispatch_token"], second["dispatch_token"])
        self.assertTrue(first["may_dispatch"])
        self.assertFalse(second["may_dispatch"])
        native_id = "/root/" + first["task_name"]
        self.assertTrue(store.attach_fallback(job["job_id"], first["dispatch_token"], native_id))
        self.assertTrue(store.attach_fallback(job["job_id"], first["dispatch_token"], native_id))
        self.assertFalse(store.attach_fallback(job["job_id"], "wrong-token", native_id))

    def test_readable_dispatch_names_are_unique_and_survive_resume(self):
        store=Store(self.state)
        first=store.reserve(self.brief('one'),self.profile(),None)
        second=store.reserve(self.brief('two'),self.profile(),None)
        a=self.invoke('fallback','claim','--job',first['job_id'],'--task-name','representation_verification')
        b=self.invoke('fallback','claim','--job',second['job_id'],'--task-name','representation_verification')
        self.assertEqual(a['task_name'],'representation_verification_'+first['job_id'][:8])
        self.assertEqual(b['task_name'],'representation_verification_'+second['job_id'][:8])
        resumed=self.invoke('fallback','claim','--job',first['job_id'],'--task-name','different_label')
        self.assertEqual(resumed['task_name'],a['task_name'])
        self.assertFalse(resumed['may_dispatch'])
        self.assertEqual(resumed['dispatch_token'],a['dispatch_token'])
        native='/root/'+a['task_name']
        self.assertEqual(reconcile_native(store,first['job_id'],[{'task_name':native}])['native_task_id'],native)

    def test_dispatch_name_rejects_invalid_names_before_claiming(self):
        store=Store(self.state); job=store.reserve(self.brief(),self.profile(),None)
        for name in ('', '../escape', 'Title · Model', 'a'*65):
            with self.subTest(name=name):
                result=self.invoke('fallback','claim','--job',job['job_id'],'--task-name',name)
                self.assertEqual(result['reason'],'invalid_task_name')
                self.assertEqual(store.job(job['job_id'])['status'],'fallback_required')

    def test_default_dispatch_name_describes_work_without_exposing_job_id(self):
        store=Store(self.state); job=store.reserve(self.brief(),self.profile(),None)
        claim=store.claim_fallback(job['job_id'])
        self.assertEqual(claim['task_name'],'python_code_change_'+job['job_id'][:8])
        self.assertNotIn(job['job_id'],claim['task_name'])

    def test_colliding_maximum_length_dispatch_names_stay_within_limit(self):
        store=Store(self.state)
        first=store.reserve(self.brief('one'),self.profile(),None)
        second=store.reserve(self.brief('two'),self.profile(),None)
        self.assertEqual(store.claim_fallback(first['job_id'],'a'*64)['task_name'],'a'*55+'_'+first['job_id'][:8])
        with store.db(write=True) as db:
            db.execute('UPDATE fallback_dispatches SET task_name=? WHERE job_id=?',
                       ('a'*55+'_'+second['job_id'][:8],first['job_id']))
        name=store.claim_fallback(second['job_id'],'a'*64)['task_name']
        self.assertEqual(name,'a'*53+'_'+second['job_id'][:8]+'_2')

    def test_foreign_readable_task_is_not_attached_during_recovery(self):
        store=Store(self.state); job=store.reserve(self.brief(),self.profile(),None)
        claim=store.claim_fallback(job['job_id'],'representation_verification')
        result=reconcile_native(store,job['job_id'],[{'task_name':'/root/representation_verification'}])
        self.assertIsNone(result['native_task_id'])
        self.assertFalse(store.attach_fallback(job['job_id'],claim['dispatch_token'],'/root/representation_verification'))

    def test_spawn_ack_lost_does_not_respawn(self):
        store = Store(self.state)
        job = store.reserve(self.brief(), self.profile(), None)
        first = store.claim_fallback(job["job_id"])
        listing = [{"task_name": "/root/" + first["task_name"]}]
        result = reconcile_native(store, job["job_id"], listing)
        self.assertEqual(result["native_task_id"], listing[0]["task_name"])
        self.assertFalse(store.claim_fallback(job["job_id"])["may_dispatch"])
        other = store.reserve(self.brief("uncertain"), self.profile(), None)
        store.claim_fallback(other["job_id"])
        result = reconcile_native(store, other["job_id"], [])
        self.assertEqual(result["status"], "dispatch_uncertain")

    def test_compaction_resume_uses_lookup(self):
        server, store, path = self.busy()
        first = self.invoke("submit", "--brief", str(path))
        recovered = self.invoke("lookup", "--chat", "fixture-chat", "--task-key", "request")
        self.assertEqual(first["job_id"], recovered["job_id"])
        self.assertEqual(first["attempt_id"], recovered["attempt_id"])
        self.assertFalse(any(method == "POST" for method, _ in server.calls))

    def test_disabled_does_not_create_state(self):
        path = self.root / "brief.json"
        path.write_text(json.dumps(self.brief()))
        result = self.invoke("submit", "--brief", str(path))
        self.assertEqual(result["reason"], "routing_disabled")
        self.assertFalse(self.state.exists())

    def test_fallback_candidate_uses_independent_checks(self):
        self.write_config()
        store = Store(self.state)
        job = store.reserve(self.brief(), self.profile(), None)
        claim = store.claim_fallback(job["job_id"])
        native_id = "/root/" + claim["task_name"]
        store.attach_fallback(job["job_id"], claim["dispatch_token"], native_id)
        candidate = self.root / "cloud-result.json"
        candidate.write_text(json.dumps({"files": {"helper.py": FIXED, "test_helper.py": SUPPLIED + ADDED}, "summary": "fix"}))
        result = store.record_fallback_candidate(job["job_id"], native_id, candidate)
        self.assertEqual(result["status"], "candidate_ready")
        self.assertEqual(self.invoke("check", "--job", job["job_id"])["status"], "accepted")

    def test_invalid_native_output_is_terminal(self):
        self.write_config()
        store = Store(self.state)
        job = store.reserve(self.brief(), self.profile(), None)
        claim = store.claim_fallback(job["job_id"])
        native_id = "/root/" + claim["task_name"]
        store.attach_fallback(job["job_id"], claim["dispatch_token"], native_id)
        candidate = self.root / "invalid.json"
        candidate.write_text("not valid output")
        store.record_fallback_candidate(job["job_id"], native_id, candidate)
        self.assertEqual(self.invoke("check", "--job", job["job_id"])["status"], "failed")

    def test_invalid_model_list_is_unavailable(self):
        from local_model_delegation.cli import submit_task
        server, store, path = self.busy()
        profile = self.profile(); profile['endpoint'] = server.endpoint
        self.write_config(profile)
        with patch("local_model_delegation.cli.Runtime.list_models", return_value={"models": [None]}):
            result = submit_task(self.state, path)
        self.assertEqual(result['status'], 'fallback_required')
        self.assertEqual(result['reason'], 'model_unavailable')
        self.assertFalse(any(method == 'POST' for method, _ in server.calls))
