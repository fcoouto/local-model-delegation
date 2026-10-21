import json
import os
from pathlib import Path
import subprocess
import sys

from tests.support import Fixture, FIXED, SUPPLIED, ADDED


ROOT = Path(__file__).resolve().parents[1]


class Terminology(Fixture):
    def invoke(self, *args):
        home = self.root/'home'; home.mkdir(exist_ok=True)
        return subprocess.run([sys.executable, '-B', str(ROOT/'delegate.py'), *args],
                              cwd=self.project, env={**os.environ, 'HOME':str(home)},
                              capture_output=True, text=True)

    def test_generic_cli_doctor_is_read_only_from_another_project(self):
        result = self.invoke('doctor')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(json.loads(result.stdout)['routing_enabled'])
        self.assertFalse((self.root/'home/.local/state').exists())

    def test_setup_uses_generic_shared_state(self):
        result = self.invoke('setup')
        self.assertEqual(result.returncode, 0, result.stderr)
        state = self.root/'home/.local/state/local-model-delegation'
        self.assertFalse(json.loads((state/'config.json').read_text())['routing_enabled'])
        self.assertTrue((state/'state.sqlite3').is_file())
        self.assertFalse((state.parent/'codex-local-repairs').exists())

    def test_legacy_state_requires_explicit_selection_without_moving_history(self):
        legacy = self.root/'home/.local/state/codex-local-repairs'
        legacy.mkdir(parents=True, mode=0o700)
        config = b'{"schema_version":2,"routing_enabled":false,"visibility_enabled":false}\n'
        (legacy/'config.json').write_bytes(config)
        (legacy/'history.txt').write_bytes(b'existing records')
        result = self.invoke('setup')
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(result.stdout)['reason'], 'explicit_state_directory_required')
        self.assertFalse((legacy.parent/'local-model-delegation').exists())
        explicit = self.invoke('--state-dir', str(legacy), 'doctor')
        self.assertEqual(explicit.returncode, 0, explicit.stderr)
        self.assertFalse(json.loads(explicit.stdout)['visibility_enabled'])
        self.assertEqual((legacy/'config.json').read_bytes(), config)
        self.assertEqual((legacy/'history.txt').read_bytes(), b'existing records')

    def test_saved_python_capability_remains_verifiable_without_widening_approval(self):
        from local_model_delegation.contracts import validate_brief
        from local_model_delegation.profiles import eligible, fingerprint_artifact
        from local_model_delegation.store import Store
        from local_model_delegation.validation import verify_candidate
        profile = self.profile(); profile['capabilities'] = ['bounded_python_repair']
        profile['approval']['capabilities'] = ['bounded_python_repair']
        self.write_config(profile)
        brief = self.brief(); brief['capability'] = 'bounded_python_repair'
        before = json.dumps(brief, sort_keys=True)
        validate_brief(brief)
        identity = fingerprint_artifact(self.artifact, ['weights.bin'])
        self.assertFalse(eligible(profile, identity, 'python_code_change'))
        store = Store(self.state); job = store.reserve(brief, profile, None)
        claim = store.claim_fallback(job['job_id'])
        native = '/root/'+claim['task_name']
        store.attach_fallback(job['job_id'], claim['dispatch_token'], native)
        candidate = self.root/'saved.json'
        candidate.write_text(json.dumps({'files':{'helper.py':FIXED,'test_helper.py':SUPPLIED+ADDED},'summary':'Trim both ends'}))
        store.record_fallback_candidate(job['job_id'], native, candidate)
        self.assertEqual(verify_candidate(self.state, job['job_id'])['status'], 'accepted')
        self.assertEqual(json.dumps(store.job(job['job_id'])['brief'], sort_keys=True), before)

    def test_legacy_worker_resumes_only_the_manifest_bound_entrypoint(self):
        import hashlib
        from local_model_delegation.contracts import canonical, digest
        from local_model_delegation.store import Store, atomic_json, private_dir
        from local_model_delegation import worker
        self.write_config(); store = Store(self.state)
        for injected in (False, True):
            with self.subTest(injected=injected):
                job = store.reserve(self.brief(str(injected)), self.profile(), self.loaded(2))
                script = "import sys\nfrom pathlib import Path\nPath(sys.argv[sys.argv.index('--state-dir')+1], 'resumed.txt').write_text('legacy')\n"
                manifest = {'repair.py':hashlib.sha256(script.encode()).hexdigest()}
                bundle = private_dir(self.state/'runtimes'/digest(manifest))
                (bundle/'repair.py').write_text(script)
                atomic_json(bundle/'manifest.json', manifest)
                if injected: (bundle/'delegate.py').write_text("raise SystemExit('unverified entrypoint')\n")
                key = store.attempt(job['attempt_id'])['instance_key']
                instance = store.instance(key)
                with store.db(write=True) as db:
                    db.execute('UPDATE instances SET data=? WHERE instance_key=?',
                               (canonical({**instance['data'],'runtime_bundle':bundle.name}),key))
                worker.start_worker(self.state, job['attempt_id'])
                self.assertEqual(worker._children[-1].wait(timeout=5), 0)
                self.assertEqual((self.state/'resumed.txt').read_text(), 'legacy')
                (self.state/'resumed.txt').unlink()
                with store.db(write=True) as db:
                    db.execute("UPDATE attempts SET state='released' WHERE attempt_id=?",(job['attempt_id'],))

    def test_migrated_legacy_profile_can_assess_without_transferring_approval(self):
        from local_model_delegation.profiles import migrate_profile_schema, read_profiles
        from local_model_delegation.onboarding import begin_assessment
        from local_model_delegation.store import atomic_json
        profile = self.profile(); profile['capabilities'] = ['bounded_python_repair']
        profile['approval']['capabilities'] = ['bounded_python_repair']
        self.write_config(profile)
        migrate_profile_schema(self.state)
        config = json.loads((self.state/'config.json').read_text())
        config['assessment_policy'] = {'enabled':True,'owner_reference':'fixture-consent'}
        atomic_json(self.state/'config.json', config)
        assessment = begin_assessment(self.state, 'fictional', 'fixture-consent')
        self.assertEqual(len(assessment['trials']), 6)
        self.assertTrue(all(t['brief']['capability']=='bounded_python_repair' for t in assessment['trials']))
        migrated = read_profiles(self.state)[0]
        self.assertEqual(migrated['approval'], profile['approval'])
        self.assertEqual(migrated['qualification_status'], 'needs_assessment')
        self.assertFalse(json.loads((self.state/'config.json').read_text())['routing_enabled'])

    def test_saved_native_dispatch_name_is_reconciled_without_another_claim(self):
        from local_model_delegation.cli import reconcile_native
        from local_model_delegation.store import Store
        store = Store(self.state); job = store.reserve(self.brief(), self.profile(), None)
        claim = store.claim_fallback(job['job_id'])
        self.assertTrue(claim['task_name'].startswith('local_delegation_'))
        legacy_name = 'local_repair_'+job['job_id']
        with store.db(write=True) as db:
            db.execute('UPDATE fallback_dispatches SET task_name=? WHERE job_id=?',(legacy_name,job['job_id']))
        native = '/root/'+legacy_name
        self.assertEqual(reconcile_native(store,job['job_id'],[{'task_name':native}])['native_task_id'], native)
        resumed = store.claim_fallback(job['job_id'])
        self.assertFalse(resumed['may_dispatch'])
        self.assertEqual(resumed['dispatch_token'], claim['dispatch_token'])
        self.assertEqual(resumed['task_name'], legacy_name)
