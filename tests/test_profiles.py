import copy
import json
from local_model_delegation.contracts import validate_brief, load_json
from local_model_delegation.profiles import eligible, fingerprint_artifact, read_legacy_profile
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
        loaded = read_legacy_profile(self.write_config(p), "python_code_change")
        self.assertEqual(loaded["fallback"], p["fallback"])

    def test_same_name_new_bytes_needs_confirmation(self):
        p = self.profile()
        (self.artifact / "weights.bin").write_bytes(b"fictional weights version two")
        identity = fingerprint_artifact(self.artifact, ["weights.bin"])
        self.assertFalse(eligible(p, identity, "python_code_change"))

    def test_disabled_configuration_has_no_side_effects(self):
        path = self.root / "disabled.json"
        path.write_text(json.dumps(self.config(enabled=False)))
        with self.assertRaisesRegex(ValueError, "routing_disabled"):
            read_legacy_profile(path, "python_code_change")
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
                read_legacy_profile(self.write_config({**self.profile(), "stale_tolerance_seconds": value}), "python_code_change")
        p = self.profile()
        p.pop("fallback")
        with self.assertRaises(ValueError): read_legacy_profile(self.write_config(p), "python_code_change")
        p = self.profile()
        p["adapter"] = "unknown"
        with self.assertRaises(ValueError): read_legacy_profile(self.write_config(p), "python_code_change")

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

    def test_migrate_keeps_legacy_bytes_and_disables_routing(self):
        migrate = self.api("migrate_profile_schema")
        old = self.write_config().read_bytes()
        result = migrate(self.state)
        from pathlib import Path
        from local_model_delegation.store import Store
        self.assertEqual((Path(result["backup_dir"]) / "profiles.json").read_bytes(), old)
        self.assertFalse(json.loads((self.state / "config.json").read_text())["routing_enabled"])
        p = json.loads((self.state / "profiles/fictional.json").read_text())
        self.assertEqual(p["qualification_status"], "needs_assessment")
        self.assertEqual(p["approval"], json.loads(old)["profiles"]["fictional"]["approval"])
        with Store(self.state).db() as db:
            self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], 2)
            self.assertTrue({"fallback", "queued_at", "route_data"} <= {r[1] for r in db.execute("PRAGMA table_info(jobs)")})

    def test_old_entrypoint_cannot_submit_after_migration(self):
        migrate = self.api("migrate_profile_schema")
        path = self.write_config()
        migrate(self.state)
        with self.assertRaisesRegex(ValueError, "routing_disabled"):
            read_legacy_profile(path, "python_code_change")
        from local_model_delegation.store import Store
        import sqlite3
        store = Store(self.state)
        with self.assertRaisesRegex(ValueError, "mixed_state_version"):
            store.reserve(self.brief(), self.profile(), self.loaded())
        # The previous executable used a positional 11-column insert.
        with store.db(write=True) as db, self.assertRaises(sqlite3.OperationalError):
            db.execute("INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?,?,?,?)", (None,) * 11)

    def test_migration_admission_race_keeps_database_v1(self):
        migrate = self.api("migrate_profile_schema")
        from local_model_delegation import profiles
        from local_model_delegation.store import Store, atomic_json
        from unittest.mock import patch
        p = self.profile(); self.write_config(p); store = Store(self.state)
        raced = []
        def write(path, value):
            atomic_json(path, value)
            if path.name == "profiles.json" and value.get("routing_enabled") is False:
                raced.append(store.reserve(self.brief(), p, self.loaded()))
        with patch.object(profiles, "atomic_json", side_effect=write):
            with self.assertRaisesRegex(ValueError, "unresolved_work"):
                migrate(self.state)
        self.assertEqual(store.job(raced[0]["job_id"])["status"], "reserved")
        with store.db() as db: self.assertLess(db.execute("PRAGMA user_version").fetchone()[0], 2)
        self.assertTrue(json.loads((self.state / "profiles.json").read_text())["routing_enabled"])

    def test_migrate_refuses_unresolved_work(self):
        migrate = self.api("migrate_profile_schema")
        from local_model_delegation.store import Store
        p = self.profile(); self.write_config(p); store = Store(self.state)
        job = store.reserve(self.brief(), p, self.loaded())
        for status in ("checking", "dispatch_uncertain", "reserved"):
            with store.db(write=True) as db: db.execute("UPDATE jobs SET status=?", (status,))
            with self.subTest(status=status), self.assertRaisesRegex(ValueError, "unresolved_work"):
                migrate(self.state)
        with store.db(write=True) as db:
            db.execute("UPDATE jobs SET status='failed'")
            db.execute("UPDATE attempts SET state='uncertain'")
        with self.assertRaisesRegex(ValueError, "unresolved_work"): migrate(self.state)
        self.assertEqual(store.job(job["job_id"])["status"], "failed")

    def test_migration_interruption_is_recoverable(self):
        migrate = self.api("migrate_profile_schema")
        from local_model_delegation import profiles
        from local_model_delegation.store import atomic_json
        from unittest.mock import patch
        old = self.write_config().read_bytes()
        def interrupt(path, value):
            if path.name == "config.json": raise OSError("fixture interruption")
            return atomic_json(path, value)
        with patch.object(profiles, "atomic_json", side_effect=interrupt):
            with self.assertRaises(OSError): migrate(self.state)
        with self.assertRaisesRegex(ValueError, "routing_disabled"):
            read_legacy_profile(self.state / "profiles.json", "python_code_change")
        result = migrate(self.state)
        from pathlib import Path
        self.assertEqual((Path(result["backup_dir"]) / "profiles.json").read_bytes(), old)
        self.assertFalse(json.loads((self.state / "config.json").read_text())["routing_enabled"])

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
