"""Explicit disposable qualification. Never approves a real local model."""
import argparse
import json
from pathlib import Path
import shutil
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import tests
from tests.support import Fixture
from local_repair.cli import DEFAULT_STATE
from local_repair.contracts import canonical, load_json
from local_repair.lmstudio import Runtime
from local_repair.store import Store, atomic_json
from local_repair.validation import check_candidate


def validate_temporary_state(path):
    path = Path(path).absolute()
    roots = [Path(tempfile.gettempdir()).resolve(), Path("/private/tmp")]
    if path.resolve() == DEFAULT_STATE.resolve() or not any(path.resolve().is_relative_to(root) for root in roots):
        raise ValueError("temporary_state_required")
    if path.is_symlink(): raise ValueError("unsafe_state")
    return path


def prepare_native(state_dir):
    state_dir = validate_temporary_state(state_dir)
    if state_dir.exists(): raise ValueError("fresh_state_required")
    fixture = Fixture()
    fixture.setUp()
    try:
        profile, brief = fixture.profile(), fixture.brief()
        shutil.copytree(fixture.root, state_dir)
        state_dir.chmod(0o700)
        profile["artifact"]["root"] = str((state_dir / "artifact").resolve())
        catalog = state_dir / "runtime-catalog.json"
        entry = load_json(catalog.read_text())
        entry["models"][0]["concreteModelDirAbsolutePath"] = profile["artifact"]["root"]
        entry["models"][0]["allFiles"] = [{"absPath": str(state_dir / "artifact/weights.bin")}]
        atomic_json(catalog, entry)
        profile["runtime_catalog"] = str(catalog)
        from local_repair.profiles import model_identity
        profile["approval"]["model_identity"] = model_identity(profile)
        brief["source_root"] = str((state_dir / "project").resolve())
        # Only a fictional local profile; no real runtime discovery or local POST.
        config = fixture.config(profile)
        atomic_json(state_dir / "profiles.json", config)
        store = Store(state_dir)
        job = store.reserve(brief, profile, None)
        claim = store.claim_fallback(job["job_id"])
        result = {**claim, "state_dir": str(state_dir), "profile_kind": "fictional-no-local-model",
                  "candidate_path": str(state_dir / "native-candidate.json")}
        atomic_json(state_dir / "native-claim.json", result)
        return result
    finally:
        fixture.doCleanups()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=["inspect", "native-prepare", "native-verify"], required=True)
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--endpoint", default="http://127.0.0.1:1235")
    parser.add_argument("--native-task-id")
    args = parser.parse_args()
    state = validate_temporary_state(args.state_dir)
    if args.case == "native-prepare": result = prepare_native(state)
    elif args.case == "inspect":
        result = {"snapshot": Runtime(args.endpoint).list_models(), "local_mutations": False, "approvals": False}
    else:
        claim = load_json((state / "native-claim.json").read_text())
        store = Store(state)
        if not store.attach_fallback(claim["job_id"], claim["dispatch_token"], args.native_task_id):
            raise ValueError("native_task_mismatch")
        result = store.record_fallback_candidate(claim["job_id"], args.native_task_id, Path(claim["candidate_path"]))
        result = check_candidate(state, claim["job_id"])
        assert result["status"] == "accepted", result
        assert not store.claim_fallback(claim["job_id"])["may_dispatch"]
        assert not store.claim_fallback(claim["job_id"])["may_dispatch"]
        atomic_json(state / "native-verification.json", result)
    print(canonical(result))


if __name__ == "__main__": main()
