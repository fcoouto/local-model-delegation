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

    def test_saved_native_dispatch_name_is_reconciled_without_another_claim(self):
        from local_model_delegation.cli import reconcile_native
        from local_model_delegation.store import Store
        store = Store(self.state); job = store.reserve(self.brief(), self.profile(), None)
        claim = store.claim_fallback(job['job_id'])
        saved_name = 'local_delegation_'+job['job_id']
        with store.db(write=True) as db:
            db.execute('UPDATE fallback_dispatches SET task_name=? WHERE job_id=?',(saved_name,job['job_id']))
        native = '/root/'+saved_name
        self.assertEqual(reconcile_native(store,job['job_id'],[{'task_name':native}])['native_task_id'], native)
        resumed = store.claim_fallback(job['job_id'])
        self.assertFalse(resumed['may_dispatch'])
        self.assertEqual(resumed['dispatch_token'], claim['dispatch_token'])
        self.assertEqual(resumed['task_name'], saved_name)
