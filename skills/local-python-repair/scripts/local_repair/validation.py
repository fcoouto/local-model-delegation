"""Independent pure-Python checks in a restrictive, qualified macOS sandbox."""
import ast
from functools import lru_cache
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
from .contracts import MAX_ANSWER_BYTES, canonical, envelope, load_json, safe_path, text_hash, validate_brief
from .profiles import read_profile
from .store import Store, atomic_json

PURE_IMPORTS = {"re", "hashlib", "math", "string", "collections", "itertools", "functools", "decimal", "fractions"}
DENIED = {"open", "exec", "eval", "compile", "input", "getattr", "setattr", "delattr", "vars", "globals", "locals",
          "type", "object", "dir", "help", "breakpoint", "memoryview", "classmethod", "staticmethod", "property"}


def guard(text, name, modules):
    tree = ast.parse(text, name)
    tests = Path(name).name.startswith("test_")
    allowed = PURE_IMPORTS | (set(modules) | {"unittest"} if tests else set())
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(a.name not in allowed or (a.asname or "").startswith("_") for a in node.names): raise ValueError("unsupported_import")
        if isinstance(node, ast.ImportFrom):
            if node.level or node.module not in allowed or any(a.name.startswith("_") or a.name == "*" for a in node.names): raise ValueError("unsupported_import")
        if isinstance(node, ast.Name) and (node.id in DENIED or node.id.startswith("__") and node.id != "__name__"):
            raise ValueError("unsupported_execution")
        if isinstance(node, ast.Attribute) and node.attr.startswith("_"):
            raise ValueError("unsupported_introspection")
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and (node.name.startswith("__") or node.decorator_list):
            raise ValueError("unsupported_function")
        if isinstance(node, ast.ClassDef) and (not tests or node.decorator_list or node.keywords
                or len(node.bases) != 1 or ast.unparse(node.bases[0]) not in ("unittest.TestCase", "TestCase")):
            raise ValueError("unsupported_class")
        if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Attribute) and not (isinstance(target.value, ast.Name) and target.value.id == "self"):
                    raise ValueError("unsupported_mutation")
    return tree


def methods(tree):
    return {cls.name + "." + method.name: ast.dump(method, include_attributes=False)
            for cls in tree.body if isinstance(cls, ast.ClassDef)
            for method in cls.body if isinstance(method, ast.FunctionDef) and method.name.startswith("test")}


def parse_candidate(text, brief):
    if len(text.encode()) > MAX_ANSWER_BYTES: raise ValueError("oversized_answer")
    value = load_json(text)
    if not isinstance(value, dict) or set(value) != {"files", "summary"} or not isinstance(value["summary"], str) or not isinstance(value["files"], dict) or not value["files"]:
        raise ValueError("invalid_candidate")
    files = value["files"]
    if not files.keys() <= set(brief["editable_paths"]): raise ValueError("candidate_path_not_allowed")
    modules = [Path(name).stem for name in brief["files"]]
    for name, source in files.items():
        safe_path(Path(brief["source_root"]), name)
        if not isinstance(source, str): raise ValueError("invalid_candidate")
        guard(source, name, modules)
    for name in brief["supplied_tests"]:
        source = files.get(name, brief["files"][name]["content"])
        original = ast.parse(brief["files"][name]["content"])
        candidate = guard(source, name, modules)
        supplied = methods(original)
        if any(methods(candidate).get(key) != method for key, method in supplied.items()):
            raise ValueError("supplied_test_changed")
        original_imports = [ast.dump(n) for n in original.body if isinstance(n, (ast.Import, ast.ImportFrom))]
        candidate_imports = [ast.dump(n) for n in candidate.body if isinstance(n, (ast.Import, ast.ImportFrom))]
        if not set(original_imports) <= set(candidate_imports): raise ValueError("supplied_test_import_changed")
    return files


def source_matches(brief):
    try:
        return all(text_hash(safe_path(Path(brief["source_root"]), name).read_text()) == item["sha256"] for name, item in brief["files"].items())
    except (OSError, ValueError): return False


def sandbox_profile(root):
    python_root = str(Path(sys.base_prefix).resolve())
    read_roots = [str(root.resolve()), python_root, "/usr", "/System", "/Library/Apple"]
    return ('(version 1)(deny default)(allow process*)(allow sysctl-read)(allow mach-lookup)(allow file-read-metadata)'
            + ''.join('(allow file-read* (subpath ' + json.dumps(p) + '))' for p in read_roots)
            + '(allow file-read* (literal "/") (literal "/dev/null") (literal "/dev/urandom") (literal "/private/etc/localtime"))'
            + '(allow file-write* (subpath ' + json.dumps(str(root.resolve())) + ') (literal "/dev/null"))(deny network*)')


def run_isolated(root, code, timeout=60):
    sandbox = shutil.which("sandbox-exec")
    if sys.platform != "darwin" or not sandbox: raise ValueError("isolation_unsupported")
    root = Path(root).resolve()
    driver = ('import resource\nresource.setrlimit(resource.RLIMIT_CPU,(10,10))\n'
              'resource.setrlimit(resource.RLIMIT_FSIZE,(1048576,1048576))\n' + code)
    with tempfile.TemporaryFile(dir=root) as out, tempfile.TemporaryFile(dir=root) as err:
        child = subprocess.Popen([sandbox, "-p", sandbox_profile(root), str(Path(sys.executable).resolve()), "-I", "-B", "-c", driver],
                                 cwd=root, env={"PATH": "/usr/bin:/bin", "HOME": str(root), "TMPDIR": str(root)},
                                 stdin=subprocess.DEVNULL, stdout=out, stderr=err, start_new_session=True, close_fds=True)
        reason = None
        try: child.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(child.pid, signal.SIGKILL)
            child.wait()
            reason = "check_timeout"
        out.seek(0)
        err.seek(0)
        return {"returncode": child.returncode, "stdout": out.read(MAX_ANSWER_BYTES).decode(errors="replace"),
                "stderr": err.read(MAX_ANSWER_BYTES).decode(errors="replace"), "reason": reason}


@lru_cache(maxsize=1)
def _qualified_isolation():
    if sys.platform != "darwin" or not shutil.which("sandbox-exec"): return False
    with tempfile.TemporaryDirectory() as folder:
        parent = Path(folder).resolve()
        root = parent / "work"
        root.mkdir()
        canary = parent / "private-canary"
        canary.write_text("ISOLATION_CANARY")
        code = f'''import json, pathlib, socket
ok = []
try:
    open({str(canary)!r}).read()
except PermissionError:
    ok.append("read_denied")
try:
    socket.socket().connect(("127.0.0.1", 9))
except PermissionError:
    ok.append("network_denied")
pathlib.Path("allowed.txt").write_text("ok")
print(json.dumps(ok))
'''
        result = run_isolated(root, code)
        return result["returncode"] == 0 and result["stdout"].strip() == '["read_denied", "network_denied"]'


def isolation_supported(brief):
    try:
        modules = [Path(name).stem for name in brief["files"]]
        for name, item in brief["files"].items(): guard(item["content"], name, modules)
        return _qualified_isolation()
    except (OSError, SyntaxError, ValueError): return False


def run_tests(files, module_names, names=None):
    with tempfile.TemporaryDirectory(prefix="bounded-repair-") as folder:
        root = Path(folder).resolve()
        for name, source in files.items():
            path = safe_path(root, name)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(source)
        driver = f'''import io, json, sys, unittest
sys.path.insert(0, {str(root)!r})
suite = unittest.TestSuite()
for module in {module_names!r}:
    if {names!r} is None:
        suite.addTests(unittest.defaultTestLoader.loadTestsFromName(module))
    else:
        for name in {names!r}:
            suite.addTests(unittest.defaultTestLoader.loadTestsFromName(module + "." + name))
output = io.StringIO()
result = unittest.TextTestRunner(stream=output).run(suite)
print("CHECK_RESULT=" + json.dumps({{"ok": result.wasSuccessful() and result.testsRun > 0 and not result.skipped,
      "run": result.testsRun, "failures": len(result.failures), "errors": len(result.errors), "skipped": len(result.skipped)}}))
'''
        result = run_isolated(root, driver)
        lines = [line for line in result["stdout"].splitlines() if line.startswith("CHECK_RESULT=")]
        if result["returncode"] or len(lines) != 1: return {"ok": False, "reason": result["reason"] or "check_runner_failed"}
        return load_json(lines[0].split("=", 1)[1])


def check_candidate(state_dir, job_id):
    store = Store(state_dir)
    job = store.job(job_id)
    if job["status"] != "candidate_ready": return envelope(job)
    brief = job["brief"]
    if not source_matches(brief):
        with store.db(write=True) as db:
            db.execute("UPDATE jobs SET status='needs_reassessment',reason='source_changed' WHERE job_id=? AND status='candidate_ready'", (job_id,))
        return envelope(store.job(job_id))
    with store.db(write=True) as db:
        if not db.execute("UPDATE jobs SET status='checking' WHERE job_id=? AND status='candidate_ready'", (job_id,)).rowcount:
            return envelope(store.job(job_id))
    receipt = {}
    try:
        current = read_profile(store.root / "profiles.json", brief["capability"])
        if current["approval"] != job["profile"]["approval"]: raise ValueError("approval_changed")
        path = Path(job["result_path"])
        if path.is_symlink() or not path.resolve().is_relative_to(store.root / "jobs" / job_id): raise ValueError("unsafe_result")
        artifact = load_json(path.read_text())
        if text_hash(artifact["text"]) != artifact["sha256"]: raise ValueError("candidate_hash_mismatch")
        candidate = parse_candidate(artifact["text"], brief)
        if not isolation_supported(brief): raise ValueError("isolation_unsupported")
        original = {name: item["content"] for name, item in brief["files"].items()}
        changed = {**original, **candidate}
        oracle_modules = [argv[1] for argv in brief["checks"]]
        # Model tests never share an interpreter with the independent oracles.
        source_only = {n: t for n, t in original.items() if n not in brief["supplied_tests"]}
        changed_source = {n: t for n, t in changed.items() if not Path(n).name.startswith("test_")}
        receipt["baseline"] = run_tests({**source_only, **brief["independent_tests"]}, oracle_modules)
        receipt["independent"] = run_tests({**changed_source, **brief["independent_tests"]}, oracle_modules)
        receipt["submitted"] = run_tests(changed, [Path(n).with_suffix("").as_posix().replace("/", ".") for n in brief["supplied_tests"]])
        effective = False
        added_count = 0
        for name in brief["supplied_tests"]:
            added = sorted(set(methods(ast.parse(changed[name]))) - set(methods(ast.parse(original[name]))))
            added_count += len(added)
            if added:
                result = run_tests({**original, name: changed[name]}, [Path(name).stem], added)
                effective |= result.get("failures", 0) > 0 and result.get("errors", 0) == 0
        if (receipt["baseline"].get("failures", 0) < 1 or receipt["baseline"].get("errors", 0)
                or not receipt["independent"].get("ok") or not receipt["submitted"].get("ok") or not added_count or not effective):
            raise ValueError("independent_checks_failed")
        if not source_matches(brief): raise ValueError("source_changed")
        if job["attempt_id"] and not job["native_task_id"]:
            attempt = store.attempt(job["attempt_id"])
            if attempt["state"] != "complete" or attempt["generation"] != store.instance(attempt["instance_key"])["generation"]:
                raise ValueError("attempt_fenced")
        receipt["accepted"] = True
        atomic_json(path.parent / "checks.json", receipt)
        with store.db(write=True) as db:
            db.execute("UPDATE jobs SET status='accepted',reason=NULL WHERE job_id=? AND status='checking'", (job_id,))
    except (OSError, SyntaxError, ValueError, KeyError, TypeError) as error:
        receipt.update(accepted=False, reason=str(error) if isinstance(error, ValueError) else type(error).__name__)
        atomic_json(store.root / "jobs" / job_id / "check-failure.json", receipt)
        if str(error) == "source_changed":
            with store.db(write=True) as db: db.execute("UPDATE jobs SET status='needs_reassessment',reason='source_changed' WHERE job_id=? AND status='checking'", (job_id,))
        elif job["native_task_id"]:
            with store.db(write=True) as db: db.execute("UPDATE jobs SET status='failed',reason='fallback_checks_failed' WHERE job_id=? AND status='checking'", (job_id,))
        else: store.select_fallback(job_id, "candidate_checks_failed")
    return envelope(store.job(job_id))
