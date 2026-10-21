import copy
import json
from local_repair.contracts import validate_brief, load_json
from local_repair.profiles import eligible, fingerprint_artifact, read_profile
from tests.support import Fixture


class Profiles(Fixture):
    def test_approval_is_not_evaluation(self):
        p = self.profile()
        identity = fingerprint_artifact(self.artifact, ["weights.bin"])
        self.assertTrue(eligible(p, identity, "bounded_python_repair"))
        p["approval"] = None
        p["evaluation_evidence"] = ["a-test-is-not-approval"]
        self.assertFalse(eligible(p, identity, "bounded_python_repair"))

    def test_fallback_is_per_profile(self):
        p = self.profile()
        p["fallback"] = {"model": "another-owner-selected-model", "reasoning_effort": "high"}
        loaded = read_profile(self.write_config(p), "bounded_python_repair")
        self.assertEqual(loaded["fallback"], p["fallback"])

    def test_same_name_new_bytes_needs_confirmation(self):
        p = self.profile()
        (self.artifact / "weights.bin").write_bytes(b"fictional weights version two")
        identity = fingerprint_artifact(self.artifact, ["weights.bin"])
        self.assertFalse(eligible(p, identity, "bounded_python_repair"))

    def test_disabled_configuration_has_no_side_effects(self):
        path = self.root / "disabled.json"
        path.write_text(json.dumps(self.config(enabled=False)))
        with self.assertRaisesRegex(ValueError, "routing_disabled"):
            read_profile(path, "bounded_python_repair")
        self.assertFalse(self.state.exists())

    def test_invalid_brief(self):
        original = self.brief()
        self.assertEqual(validate_brief(original), original)
        for update in [{"editable_paths": ["../escape.py"]}, {"shell": "bad"}, {"capability": "trade"}]:
            with self.subTest(update=update), self.assertRaises(ValueError):
                validate_brief({**original, **update})
        broken = copy.deepcopy(original)
        broken["files"]["helper.py"]["sha256"] = "0" * 64
        with self.assertRaises(ValueError): validate_brief(broken)
        (self.project / "helper.py").unlink()
        (self.project / "helper.py").symlink_to(self.artifact / "weights.bin")
        with self.assertRaises(ValueError): validate_brief(original)

    def test_duplicate_json_keys_rejected(self):
        with self.assertRaises(ValueError): load_json('{"a":1,"a":2}')

    def test_invalid_profile_settings(self):
        for value in [0, -1, float("nan"), True, "120"]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                read_profile(self.write_config({**self.profile(), "stale_tolerance_seconds": value}), "bounded_python_repair")
        p = self.profile()
        p.pop("fallback")
        with self.assertRaises(ValueError): read_profile(self.write_config(p), "bounded_python_repair")
        p = self.profile()
        p["adapter"] = "unknown"
        with self.assertRaises(ValueError): read_profile(self.write_config(p), "bounded_python_repair")

    def test_artifact_symlink_escape(self):
        (self.artifact / "evil.bin").symlink_to(self.project / "helper.py")
        with self.assertRaises(ValueError): fingerprint_artifact(self.artifact, ["evil.bin"])

    def test_manifest_checksums_and_file_coverage(self):
        manifest = self.artifact / "manifest.json"
        manifest.write_text(json.dumps({"artifacts": [{"path": "weights.bin", "sha256": "0" * 64, "size": 29}]}))
        with self.assertRaises(ValueError): fingerprint_artifact(self.artifact, ["weights.bin", "manifest.json"])
        with self.assertRaises(ValueError): fingerprint_artifact(self.artifact, ["manifest.json"])

