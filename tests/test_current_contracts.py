import hashlib
import json
from unittest.mock import patch
from tests.support import Fixture
from local_model_delegation.contracts import digest, validate_brief
from local_model_delegation.profiles import read_config, validate_profile
from local_model_delegation.package import runtime_entrypoint
from local_model_delegation.store import private_dir, atomic_json


class CurrentContracts(Fixture):
    def test_obsolete_capability_is_rejected_without_transferring_approval(self):
        brief=self.brief(); brief['capability']='bounded_python_repair'
        with self.assertRaises(ValueError): validate_brief(brief)

    def test_obsolete_brief_and_profile_are_rejected(self):
        brief=self.brief(); brief['schema_version']=1
        profile=self.profile(); profile['schema_version']=1
        with self.assertRaises(ValueError): validate_brief(brief)
        with self.assertRaises(ValueError): validate_profile(profile,'python_code_change')

    def test_obsolete_configuration_cannot_be_read_or_silently_reinitialized(self):
        self.state.mkdir(mode=0o700)
        path=self.state/'profiles.json'
        original=json.dumps({'schema_version':1,'routing_enabled':False,'profiles':{}})
        path.write_text(original)
        with self.assertRaisesRegex(ValueError,'unsupported_configuration'): read_config(self.state)
        self.assertEqual(path.read_text(),original)
        self.assertFalse((self.state/'config.json').exists())

    def test_only_current_manifest_bound_worker_entrypoint_can_run(self):
        script=b'raise SystemExit(0)\n'
        manifest={'repair.py':hashlib.sha256(script).hexdigest()}
        bundle=private_dir(self.state/'runtimes'/digest(manifest))
        (bundle/'repair.py').write_bytes(script); atomic_json(bundle/'manifest.json',manifest)
        with self.assertRaisesRegex(ValueError,'runtime_entrypoint_missing'): runtime_entrypoint(bundle)

    def test_default_state_does_not_discover_obsolete_directories(self):
        from local_model_delegation import cli
        home=self.root/'home'; old=home/'.local/state/codex-local-repairs'; old.mkdir(parents=True)
        marker=old/'history'; marker.write_text('preserve')
        with patch.object(cli,'DEFAULT_STATE',home/'.local/state/local-model-delegation'):
            if hasattr(cli,'LEGACY_STATE'):
                with patch.object(cli,'LEGACY_STATE',old): result=cli.resolve_state_directory(None)
            else: result=cli.resolve_state_directory(None)
        self.assertEqual(result,home/'.local/state/local-model-delegation')
        self.assertEqual(marker.read_text(),'preserve')

    def test_existing_queue_without_configuration_is_not_reinitialized(self):
        from local_model_delegation.store import Store
        from local_model_delegation.package import initialize_state
        Store(self.state)
        with self.assertRaisesRegex(ValueError,'unsupported_configuration'):initialize_state(self.state)
        self.assertFalse((self.state/'config.json').exists())

    def test_unversioned_existing_database_is_not_upgraded(self):
        import sqlite3
        from local_model_delegation.store import Store
        private_dir(self.state)
        database=self.state/'state.sqlite3'
        with sqlite3.connect(database) as db:
            db.execute('CREATE TABLE old_evidence (value TEXT)')
            db.execute("INSERT INTO old_evidence VALUES ('preserve')")
        database.chmod(0o600)
        before=database.read_bytes()
        with self.assertRaisesRegex(ValueError,'unsupported_state_version'): Store(self.state)
        self.assertEqual(database.read_bytes(),before)

    def test_reservation_uses_brief_fallback_without_profile_alias(self):
        from local_model_delegation.store import Store
        brief=self.brief();brief['fallback']['model']='explicit-native-model'
        store=Store(self.state);job=store.reserve(brief,self.profile(),None)
        self.assertEqual(store.job(job['job_id'])['fallback'],brief['fallback'])

    def test_saved_obsolete_brief_cannot_skip_scope_authorization(self):
        from local_model_delegation.store import Store
        from local_model_delegation.profiles import authorize_job
        profile=self.profile();self.write_config(profile)
        store=Store(self.state);job=store.reserve(self.brief(),profile,None)
        saved=store.job(job['job_id']);saved['brief']['schema_version']=1
        with self.assertRaisesRegex(ValueError,'invalid_brief'):authorize_job(store,saved)
