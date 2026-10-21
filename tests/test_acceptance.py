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
