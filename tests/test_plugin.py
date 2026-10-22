import importlib.util
import json
from pathlib import Path
from unittest.mock import patch
from tests.support import Fixture,REPO_ROOT
from local_model_delegation.store import Store,atomic_json


class Plugin(Fixture):
    def module(self):
        self.assertIsNotNone(importlib.util.find_spec('local_model_delegation.package'),'package module must exist')
        from local_model_delegation import package
        return package

    def test_fresh_setup_remains_disabled(self):
        module=self.module();result=module.initialize_state(self.state)
        self.assertFalse(result['routing_enabled']);self.assertTrue(result['visibility_enabled'])
        self.assertEqual(json.loads((self.state/'config.json').read_text()),result)

    def test_setup_preserves_native_auth_and_settings(self):
        module=self.module();home=self.root/'home';home.mkdir();auth=home/'auth.json';auth.write_text('fixture-auth')
        with patch.dict('os.environ',{'HOME':str(home)}):module.initialize_state(self.state)
        self.assertEqual(auth.read_text(),'fixture-auth')
        config=json.loads((self.state/'config.json').read_text());config['visibility_enabled']=False;atomic_json(self.state/'config.json',config)
        self.assertFalse(module.initialize_state(self.state)['visibility_enabled'])

    def test_package_is_relocatable_and_contains_all_skill_paths(self):
        self.module();root=REPO_ROOT;manifest=json.loads((root/'plugin.json').read_text())
        self.assertEqual(manifest['name'],'local-model-delegation')
        self.assertTrue((root/manifest['extensions']['com.openai']['onboardingSkill']).is_file())
        for name in ('setup','local-delegation'):self.assertTrue((root/'skills'/name/'SKILL.md').is_file())

    def test_cache_refresh_keeps_running_job_bundle(self):
        module=self.module();module.initialize_state(self.state)
        first=module.pin_runtime_bundle(self.state);second=module.pin_runtime_bundle(self.state)
        self.assertEqual(first,second);self.assertTrue((first/'delegate.py').is_file())
        self.assertTrue((first/'local_model_delegation/visibility.py').is_file())
        self.assertNotIn(str(REPO_ROOT),(first/'delegate.py').read_text())

    def test_incompatible_upgrade_refuses_active_state(self):
        module=self.module();self.write_config(enabled=False);store=Store(self.state);store.reserve(self.brief(),self.profile(),self.loaded())
        with self.assertRaisesRegex(ValueError,'unresolved_work'):module.prepare_update(self.state)

    def test_unsupported_host_is_explicit(self):
        module=self.module()
        with patch('local_model_delegation.package.platform.system',return_value='Linux'):
            report=module.doctor(self.state)
        self.assertFalse(report['supported']);self.assertIn('macos_required',report['limitations'])
        self.assertFalse(self.state.exists())

    def test_uninstall_preserves_models_and_private_state(self):
        module=self.module();module.initialize_state(self.state)
        before=(self.artifact/'weights.bin').read_bytes()
        module.prepare_uninstall(self.state)
        self.assertTrue((self.state/'state.sqlite3').exists())
        self.assertEqual((self.artifact/'weights.bin').read_bytes(),before)

    def test_completed_native_dispatch_does_not_block_update(self):
        module=self.module();module.initialize_state(self.state)
        from tests import test_delegation
        brief=test_delegation.Delegation.generic(self,'file_summary')
        config=json.loads((self.state/'config.json').read_text());config['routing_enabled']=True;atomic_json(self.state/'config.json',config)
        store=Store(self.state);job=store.enqueue(brief,brief['fallback']);store.decide_wait(job['job_id'],{'action':'fallback','reason':'no_qualified_model'})
        claim=store.claim_fallback(job['job_id']);store.attach_fallback(job['job_id'],claim['dispatch_token'],'/root/'+claim['task_name'])
        with store.db(write=True) as db:db.execute("UPDATE jobs SET status='accepted' WHERE job_id=?",(job['job_id'],))
        config['routing_enabled']=False;atomic_json(self.state/'config.json',config)
        self.assertEqual(module.prepare_update(self.state)['status'],'ready')

    def test_release_contains_no_machine_local_evidence(self):
        root=REPO_ROOT
        markers=['/Us'+'ers/','/var/fol'+'ders/','_docs/'+'work/','BEGIN '+'PRIVATE KEY']
        for directory in ('local_model_delegation','skills','tests'):
            for path in (root/directory).rglob('*'):
                if path.suffix not in ('.py','.md','.json'):continue
                text=path.read_text()
                self.assertFalse(any(marker in text for marker in markers),str(path.relative_to(root)))
        for path in (root/'README.md',root/'plugin.json',root/'delegate.py'):
            self.assertFalse(any(marker in path.read_text() for marker in markers),path.name)

    def test_pinned_runtime_can_launch_children_without_repackaging(self):
        module = self.module(); module.initialize_state(self.state)
        bundle = module.pin_runtime_bundle(self.state)
        self.assertEqual(module.pin_runtime_bundle(self.state, bundle), bundle)
        self.assertEqual(list((self.state/'runtimes').iterdir()), [bundle])
