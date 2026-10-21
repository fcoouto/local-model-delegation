import importlib.util
import json
from pathlib import Path
from unittest.mock import patch
from tests.support import Fixture,SCRIPTS
from local_repair.store import Store,atomic_json


class Plugin(Fixture):
    def module(self):
        self.assertIsNotNone(importlib.util.find_spec('local_repair.package'),'package module must exist')
        from local_repair import package
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
        self.module();root=SCRIPTS.parents[2];manifest=json.loads((root/'plugin.json').read_text())
        self.assertEqual(manifest['name'],'local-model-delegation')
        self.assertTrue((root/manifest['extensions']['com.openai']['onboardingSkill']).is_file())
        for name in ('setup','local-delegation','local-python-repair'):self.assertTrue((root/'skills'/name/'SKILL.md').is_file())

    def test_cache_refresh_keeps_running_job_bundle(self):
        module=self.module();module.initialize_state(self.state)
        first=module.pin_runtime_bundle(self.state);second=module.pin_runtime_bundle(self.state)
        self.assertEqual(first,second);self.assertTrue((first/'repair.py').is_file())
        self.assertTrue((first/'local_repair/visibility.py').is_file())
        self.assertNotIn(str(SCRIPTS),(first/'repair.py').read_text())

    def test_incompatible_upgrade_refuses_active_state(self):
        module=self.module();self.write_config();store=Store(self.state);store.reserve(self.brief(),self.profile(),self.loaded())
        with self.assertRaisesRegex(ValueError,'unresolved_work'):module.prepare_update(self.state)

    def test_unsupported_host_is_explicit(self):
        module=self.module()
        with patch('local_repair.package.platform.system',return_value='Linux'):
            report=module.doctor(self.state)
        self.assertFalse(report['supported']);self.assertIn('macos_required',report['limitations'])
        self.assertFalse(self.state.exists())

    def test_uninstall_preserves_models_and_private_state(self):
        module=self.module();module.initialize_state(self.state)
        before=(self.artifact/'weights.bin').read_bytes()
        module.prepare_uninstall(self.state)
        self.assertTrue((self.state/'state.sqlite3').exists())
        self.assertEqual((self.artifact/'weights.bin').read_bytes(),before)
