import copy
import json
from local_model_delegation.contracts import validate_brief, load_json
from local_model_delegation.profiles import eligible, fingerprint_artifact, read_profile_by_id
from tests.support import Fixture


class Profiles(Fixture):
    def test_approval_is_not_evaluation(self):
        p = self.profile()
        identity = fingerprint_artifact(self.artifact, ["weights.bin"])
        self.assertTrue(eligible(p, identity, "python_code_change"))
        p["approval"] = None
        p["evaluation_evidence"] = ["a-test-is-not-approval"]
        self.assertFalse(eligible(p, identity, "python_code_change"))

    def test_fallback_is_per_profile(self):
        p = self.profile()
        p["fallback"] = {"model": "another-owner-selected-model", "reasoning_effort": "high"}
        loaded = read_profile_by_id(self.write_config(p).parent, p["profile_id"], "python_code_change")
        self.assertEqual(loaded["fallback"], p["fallback"])

    def test_same_name_new_bytes_needs_confirmation(self):
        p = self.profile()
        (self.artifact / "weights.bin").write_bytes(b"fictional weights version two")
        identity = fingerprint_artifact(self.artifact, ["weights.bin"])
        self.assertFalse(eligible(p, identity, "python_code_change"))

    def test_disabled_configuration_has_no_side_effects(self):
        path = self.root / "config.json"
        path.write_text(json.dumps(self.config(enabled=False)))
        with self.assertRaisesRegex(ValueError, "routing_disabled"):
            read_profile_by_id(self.root, "fictional", "python_code_change")
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
                read_profile_by_id(self.write_config({**self.profile(), "stale_tolerance_seconds": value}).parent, "fictional", "python_code_change")
        p = self.profile()
        p.pop("fallback")
        with self.assertRaises(ValueError): read_profile_by_id(self.write_config(p).parent, p["profile_id"], "python_code_change")
        p = self.profile()
        p["adapter"] = "unknown"
        with self.assertRaises(ValueError): read_profile_by_id(self.write_config(p).parent, p["profile_id"], "python_code_change")

    def test_artifact_symlink_escape(self):
        (self.artifact / "evil.bin").symlink_to(self.project / "helper.py")
        with self.assertRaises(ValueError): fingerprint_artifact(self.artifact, ["evil.bin"])

    def test_manifest_checksums_and_file_coverage(self):
        manifest = self.artifact / "manifest.json"
        manifest.write_text(json.dumps({"artifacts": [{"path": "weights.bin", "sha256": "0" * 64, "size": 29}]}))
        with self.assertRaises(ValueError): fingerprint_artifact(self.artifact, ["weights.bin", "manifest.json"])
        with self.assertRaises(ValueError): fingerprint_artifact(self.artifact, ["manifest.json"])

    def test_review_approval_binds_model_identity(self):
        profile = self.profile()
        identity = fingerprint_artifact(self.artifact, ["weights.bin"])
        profile["model_id"] = "a-remapped-model-key"
        self.assertFalse(eligible(profile, identity, "python_code_change"))

    def test_catalog_remapping_invalidates_approval(self):
        profile = self.profile()
        identity = fingerprint_artifact(self.artifact, ["weights.bin"])
        path = self.root / "runtime-catalog.json"
        catalog = json.loads(path.read_text())
        catalog["models"][0]["indexedModelIdentifier"] = "other/same-key"
        path.write_text(json.dumps(catalog))
        self.assertFalse(eligible(profile, identity, "python_code_change"))

    def test_catalog_must_cover_exact_approved_files(self):
        from local_model_delegation.profiles import model_identity
        profile = self.profile()
        path = self.root / "runtime-catalog.json"
        original = json.loads(path.read_text())
        for update in [{"concreteModelDirAbsolutePath": str(self.project)}, {"allFiles": []},
                       {"allFiles": [{"absPath": str(self.project / "helper.py")}]}]:
            catalog = copy.deepcopy(original)
            catalog["models"][0].update(update)
            path.write_text(json.dumps(catalog))
            with self.subTest(update=update), self.assertRaises(ValueError): model_identity(profile)

    def test_catalog_ambiguity_and_permissions_fail_closed(self):
        from local_model_delegation.profiles import model_identity
        profile = self.profile()
        path = self.root / "runtime-catalog.json"
        catalog = json.loads(path.read_text())
        path.chmod(0o666)
        with self.assertRaises(ValueError): model_identity(profile)

        path.chmod(0o600)
        catalog["models"] *= 2
        path.write_text(json.dumps(catalog))
        with self.assertRaises(ValueError): model_identity(profile)


class VersionedProfiles(Fixture):
    def api(self, name):
        from local_model_delegation import profiles
        function = getattr(profiles, name, None)
        self.assertTrue(callable(function), name + " must implement the versioned profile contract")
        return function

    def write_v2(self):
        from local_model_delegation.store import atomic_json
        p = self.profile()
        p.update(schema_version=2, qualification_status="qualified", scope=[{"capability": "python_code_change",
                 "language": "python", "complexity": "simple", "context_bucket": "small", "max_input_bytes": 100000}])
        p["approval"]["scope"] = copy.deepcopy(p["scope"])
        atomic_json(self.state / "config.json", {"schema_version": 2, "routing_enabled": True, "visibility_enabled": True})
        atomic_json(self.state / "profiles" / "fictional.json", p)
        return p

    def test_profile_id_cannot_escape_state(self):
        read = self.api("read_profile_by_id")
        self.write_v2()
        with self.assertRaisesRegex(ValueError, "invalid_profile_id"):
            read(self.state, "../outside", "python_code_change")

    def test_evidence_edit_cannot_expand_approval(self):
        read = self.api("read_profile_by_id")
        p = self.write_v2()
        self.assertEqual(read(self.state, "fictional", "python_code_change")["model_id"], "fictional-model")
        p["scope"][0]["complexity"] = "complex"
        p["assessment"] = {"passed": True}
        from local_model_delegation.store import atomic_json
        atomic_json(self.state / "profiles/fictional.json", p)
        with self.assertRaisesRegex(ValueError, "model_not_approved"):
            read(self.state, "fictional", "python_code_change")

    def test_authorize_job_uses_exact_profile_and_rechecks_revocation(self):
        authorize = self.api("authorize_job")
        from local_model_delegation.store import Store, atomic_json
        p = self.write_v2(); store = Store(self.state)
        job = {"profile": p, "brief": self.brief()}
        self.assertEqual(authorize(store, job)["profile_id"], "fictional")
        p["approval"] = None
        atomic_json(self.state / "profiles/fictional.json", p)
        with self.assertRaisesRegex(ValueError, "model_not_approved"): authorize(store, job)

    def test_evidence_revision_does_not_invalidate_same_approval(self):
        authorize = self.api("authorize_job")
        from local_model_delegation.store import Store, atomic_json
        p = self.write_v2(); job = {"profile": copy.deepcopy(p), "brief": self.brief()}
        p["assessment"] = {"revision": 2, "scope": []}
        atomic_json(self.state / "profiles/fictional.json", p)
        self.assertEqual(authorize(Store(self.state), job)["assessment"]["revision"], 2)
