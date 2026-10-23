"""Candidate verification, protected Python checks and trusted native receipts."""
import ast
from functools import lru_cache
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import uuid
from .contracts import PYTHON_CHANGE_CAPABILITIES, MAX_ANSWER_BYTES, canonical, envelope, load_json, safe_path, text_hash, validate_brief
from .profiles import authorize_job
from .store import Store, atomic_json

# Explicit members keep public module aliases from exposing sys or builtins.
IMPORT_MEMBERS = {
    "re": set("compile escape findall finditer fullmatch match search split sub subn Pattern Match ASCII IGNORECASE MULTILINE DOTALL VERBOSE".split()),
    "hashlib": set("md5 sha1 sha224 sha256 sha384 sha512 sha3_224 sha3_256 sha3_384 sha3_512 blake2b blake2s".split()),
    "math": set("ceil floor trunc fabs factorial gcd lcm isqrt comb perm sqrt exp expm1 log log1p log2 log10 pow sin cos tan asin acos atan atan2 hypot degrees radians isclose isfinite isinf isnan copysign fmod remainder frexp ldexp modf fsum prod pi e tau inf nan".split()),
    "string": set("ascii_letters ascii_lowercase ascii_uppercase digits hexdigits octdigits punctuation whitespace capwords".split()),
    "collections": set("Counter defaultdict deque namedtuple OrderedDict ChainMap".split()),
    "itertools": set("accumulate chain combinations combinations_with_replacement compress count cycle dropwhile filterfalse groupby islice pairwise permutations product repeat starmap takewhile tee zip_longest".split()),
    "functools": {"reduce", "partial", "cmp_to_key"},
    "decimal": {"Decimal", "Context", "InvalidOperation", "ROUND_HALF_UP", "ROUND_HALF_EVEN"},
    "fractions": {"Fraction"},
    "unittest": {"TestCase", "main"},
}
PURE_IMPORTS = set(IMPORT_MEMBERS) - {"unittest"}
SAFE_ATTRIBUTES = set("strip lstrip rstrip lower upper casefold title capitalize swapcase replace split rsplit splitlines join startswith endswith find rfind index rindex count isalpha isalnum isdigit isdecimal isnumeric isspace islower isupper istitle isascii encode decode format format_map zfill center ljust rjust removeprefix removesuffix partition rpartition expandtabs translate maketrans append extend insert pop remove clear copy reverse sort get items keys values update setdefault add discard union intersection difference symmetric_difference issubset issuperset isdisjoint digest hexdigest group groups groupdict start end span numerator denominator real imag conjugate as_integer_ratio bit_length bit_count quantize normalize to_integral_value elements most_common subtract rotate appendleft popleft extendleft maxlen".split())
SAFE_ATTRIBUTES |= set().union(*IMPORT_MEMBERS.values())
SAFE_ATTRIBUTES |= set("assertEqual assertNotEqual assertTrue assertFalse assertIs assertIsNot assertIsNone assertIsNotNone assertIn assertNotIn assertRaises assertRaisesRegex assertAlmostEqual assertNotAlmostEqual assertGreater assertGreaterEqual assertLess assertLessEqual assertCountEqual assertRegex assertNotRegex subTest fail".split())
DENIED = {"open", "exec", "eval", "compile", "input", "getattr", "setattr", "delattr", "vars", "globals", "locals",
          "type", "object", "dir", "help", "breakpoint", "memoryview", "classmethod", "staticmethod", "property"}


def validate_python_source(text, name, modules):
    tree = ast.parse(text, name)
    tests = Path(name).name.startswith("test_")
    allowed = PURE_IMPORTS | (set(modules) | {"unittest"} if tests else set())
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(a.name not in allowed or (a.asname or "").startswith("_") for a in node.names): raise ValueError("unsupported_import")
        if isinstance(node, ast.ImportFrom):
            if (node.level or node.module not in allowed
                    or any(a.name.startswith("_") or a.name == "*" or (a.asname or "").startswith("_")
                           or node.module in IMPORT_MEMBERS and a.name not in IMPORT_MEMBERS[node.module]
                           for a in node.names)):
                raise ValueError("unsupported_import")
        if isinstance(node, ast.Name) and (node.id in DENIED or node.id.startswith("__") and node.id != "__name__"):
            raise ValueError("unsupported_execution")
        if isinstance(node, ast.Attribute) and node.attr not in SAFE_ATTRIBUTES and not (tests and isinstance(node.value, ast.Name) and node.value.id == "self" and not node.attr.startswith("_")):
            raise ValueError("unsupported_introspection")
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and (node.name.startswith("__") or node.decorator_list):
            raise ValueError("unsupported_function")
        if isinstance(node, ast.ClassDef) and (not tests or node.decorator_list or node.keywords
                or len(node.bases) != 1 or ast.unparse(node.bases[0]) not in ("unittest.TestCase", "TestCase")):
            raise ValueError("unsupported_class")
        if isinstance(node, ast.Attribute) and isinstance(node.ctx, (ast.Store, ast.Del)) and not (
                tests and isinstance(node.value, ast.Name) and node.value.id == "self"):
            raise ValueError("unsupported_mutation")
    return tree


def python_test_methods(tree):
    return {cls.name + "." + method.name: ast.dump(method, include_attributes=False)
            for cls in tree.body if isinstance(cls, ast.ClassDef)
            for method in cls.body if isinstance(method, ast.FunctionDef) and method.name.startswith("test")}


def _candidate_json(text):
    """Allow one whole JSON fence only at the model-output boundary."""
    if len(text.encode()) > MAX_ANSWER_BYTES: raise ValueError("oversized_answer")
    fenced = re.fullmatch(r"```(?:json)?[ \t]*\r?\n(.*)\r?\n```[ \t]*", text.strip(), re.DOTALL)
    return load_json(fenced.group(1) if fenced else text)


def parse_python_proposal(text, brief):
    value = _candidate_json(text)
    if not isinstance(value, dict) or set(value) != {"files", "summary"} or not isinstance(value["summary"], str) or not isinstance(value["files"], dict) or not value["files"]:
        raise ValueError("invalid_candidate")
    files = value["files"]
    if not files.keys() <= set(brief["editable_paths"]): raise ValueError("candidate_path_not_allowed")
    modules = [Path(name).stem for name in brief["files"]]
    for name, source in files.items():
        safe_path(Path(brief["source_root"]), name)
        if not isinstance(source, str): raise ValueError("invalid_candidate")
        validate_python_source(source, name, modules)
    for name in brief["supplied_tests"]:
        source = files.get(name, brief["files"][name]["content"])
        original = ast.parse(brief["files"][name]["content"])
        candidate = validate_python_source(source, name, modules)
        supplied = python_test_methods(original)
        if any(python_test_methods(candidate).get(key) != method for key, method in supplied.items()):
            raise ValueError("supplied_test_changed")
        original_imports = [ast.dump(n) for n in original.body if isinstance(n, (ast.Import, ast.ImportFrom))]
        candidate_imports = [ast.dump(n) for n in candidate.body if isinstance(n, (ast.Import, ast.ImportFrom))]
        if not set(original_imports) <= set(candidate_imports): raise ValueError("supplied_test_import_changed")
    return files


def source_matches(brief):
    try:
        return (all(text_hash(safe_path(Path(brief["source_root"]), name).read_text()) == item["sha256"] for name, item in brief["files"].items())
                and all(not safe_path(Path(brief["source_root"]), name).exists() for name in brief["editable_paths"] if name not in brief["files"]))
    except (OSError, ValueError): return False


def sandbox_profile(root, executable_roots=()):
    python_root = str(Path(sys.base_prefix).resolve())
    read_roots = [str(root.resolve()), python_root, "/usr", "/System", "/Library/Apple", *executable_roots]
    return ('(version 1)(deny default)(allow process*)(allow sysctl-read)(allow mach-lookup)(allow file-read-metadata)'
            + ''.join('(allow file-read* (subpath ' + json.dumps(p) + '))' for p in read_roots)
            + '(allow file-read* (literal "/") (literal "/dev/null") (literal "/dev/urandom") (literal "/private/etc/localtime"))'
            + '(allow file-write* (subpath ' + json.dumps(str(root.resolve())) + ') (literal "/dev/null"))(deny network*)')


def run_isolated(root, code, timeout=60, executable_roots=()):
    sandbox = shutil.which("sandbox-exec")
    if sys.platform != "darwin" or not sandbox: raise ValueError("isolation_unsupported")
    root = Path(root).resolve()
    driver = ('import resource\nresource.setrlimit(resource.RLIMIT_CPU,(10,10))\n'
              'resource.setrlimit(resource.RLIMIT_FSIZE,(1048576,1048576))\n' + code)
    with tempfile.TemporaryFile(dir=root) as out, tempfile.TemporaryFile(dir=root) as err:
        child = subprocess.Popen([sandbox, "-p", sandbox_profile(root, executable_roots), str(Path(sys.executable).resolve()), "-I", "-B", "-c", driver],
                                 cwd=root, env={"PATH": "/usr/bin:/bin", "HOME": str(root), "TMPDIR": str(root)},
                                 stdin=subprocess.DEVNULL, stdout=out, stderr=err, start_new_session=True, close_fds=True)
        reason = None
        try: child.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(child.pid, signal.SIGKILL)
            child.wait()
            reason = "check_timeout"
        except BaseException:
            if child.poll() is None:
                os.killpg(child.pid, signal.SIGKILL)
            child.wait()
            raise
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


def python_isolation_supported(brief):
    try:
        modules = [Path(name).stem for name in brief["files"]]
        for name, item in brief["files"].items(): validate_python_source(item["content"], name, modules)
        return _qualified_isolation()
    except (OSError, SyntaxError, ValueError): return False


def run_python_tests(files, module_names, names=None):
    with tempfile.TemporaryDirectory(prefix="python-checks-") as folder:
        root = Path(folder).resolve()
        for name, source in files.items():
            path = safe_path(root, name)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(source)
        marker = "CHECK_RESULT_" + uuid.uuid4().hex + "="
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
print({marker!r} + json.dumps({{"ok": result.wasSuccessful() and result.testsRun > 0 and not result.skipped,
      "run": result.testsRun, "failures": len(result.failures), "errors": len(result.errors), "skipped": len(result.skipped)}}))
'''
        result = run_isolated(root, driver)
        lines = [line for line in result["stdout"].splitlines() if line.startswith(marker)]
        if result["returncode"] or len(lines) != 1: return {"ok": False, "reason": result["reason"] or "check_runner_failed"}
        return load_json(lines[0][len(marker):])


def reclaim_python_verification(store, job_id):
    if store.job(job_id)["brief"]["capability"] not in PYTHON_CHANGE_CAPABILITIES: return
    with store.db(write=True) as db:
        db.execute("UPDATE jobs SET status='candidate_ready' WHERE job_id=? AND status='checking'", (job_id,))


def verify_candidate(state_dir, job_id):
    from .worker import ownership
    store = Store(state_dir)
    if store.job(job_id)["brief"]["capability"] not in PYTHON_CHANGE_CAPABILITIES:
        return prepare_verification(state_dir, job_id)
    with ownership(store, "check-" + job_id) as owned:
        if not owned: return envelope(store.job(job_id))
        # Only a lost checker can leave this state while its ownership lock is free.
        reclaim_python_verification(store, job_id)
        return _verify_python_candidate(store, job_id)


def _verify_python_candidate(store, job_id):
    job = store.job(job_id)
    if job["status"] != "candidate_ready": return envelope(job)
    brief = job["brief"]
    if not source_matches(brief):
        with store.db(write=True) as db:
            db.execute("UPDATE jobs SET status=?,reason='source_changed' WHERE job_id=? AND status='candidate_ready'",
                       ('failed' if job['native_task_id'] else 'needs_reassessment', job_id))
        return envelope(store.job(job_id))
    with store.db(write=True) as db:
        if not db.execute("UPDATE jobs SET status='checking' WHERE job_id=? AND status='candidate_ready'", (job_id,)).rowcount:
            return envelope(store.job(job_id))
    receipt = {}
    category = 'verification'
    try:
        current = authorize_job(store, job, purpose='verify')
        if current.get("approval") != job["profile"].get("approval"): raise ValueError("approval_changed")
        path = Path(job["result_path"])
        if path.is_symlink() or not path.resolve().is_relative_to(store.root / "jobs" / job_id): raise ValueError("unsafe_result")
        artifact = load_json(path.read_text())
        if text_hash(artifact["text"]) != artifact["sha256"]: raise ValueError("candidate_hash_mismatch")
        try: candidate = parse_python_proposal(artifact["text"], brief)
        except (SyntaxError, ValueError, TypeError):
            category = 'format'
            raise
        if not python_isolation_supported(brief): raise ValueError("isolation_unsupported")
        original = {name: item["content"] for name, item in brief["files"].items()}
        changed = {**original, **candidate}
        oracle_modules = [argv[1] for argv in brief["checks"]]
        # Model tests never share an interpreter with the independent oracles.
        source_only = {n: t for n, t in original.items() if n not in brief["supplied_tests"]}
        changed_source = {n: t for n, t in changed.items() if not Path(n).name.startswith("test_")}
        receipt["baseline"] = run_python_tests({**source_only, **brief["independent_tests"]}, oracle_modules)
        if (receipt["baseline"].get("reason") or receipt["baseline"].get("failures", 0) < 1
                or receipt["baseline"].get("errors", 0) or receipt["baseline"].get("skipped", 0)):
            raise ValueError("baseline_verification_unavailable")
        receipt["independent"] = run_python_tests({**changed_source, **brief["independent_tests"]}, oracle_modules)
        test_modules = [Path(n).with_suffix("").as_posix().replace("/", ".") for n in brief["supplied_tests"]]
        # Unchanged methods can still be weakened by added setup code or global rebinding.
        receipt["protected"] = run_python_tests({**changed_source, **{n: original[n] for n in brief["supplied_tests"]}}, test_modules)
        receipt["submitted"] = run_python_tests(changed, test_modules)
        if any(receipt[name].get("reason") for name in ("independent", "protected", "submitted")):
            raise ValueError("candidate_verification_unavailable")
        effective = False
        added_count = 0
        for name in brief["supplied_tests"]:
            added = sorted(set(python_test_methods(ast.parse(changed[name]))) - set(python_test_methods(ast.parse(original[name]))))
            added_count += len(added)
            if added:
                result = run_python_tests({**original, name: changed[name]}, [Path(name).stem], added)
                if result.get("reason"): raise ValueError("regression_verification_unavailable")
                effective |= result.get("failures", 0) > 0 and result.get("errors", 0) == 0
        if (not receipt["independent"].get("ok") or not receipt["protected"].get("ok")
                or not receipt["submitted"].get("ok") or not added_count or not effective):
            category = "semantic"
            raise ValueError("independent_checks_failed")
        if not source_matches(brief): raise ValueError("source_changed")
        current = authorize_job(store, job, purpose='verify')
        if current.get("approval") != job["profile"].get("approval"): raise ValueError("approval_changed")
        if job["attempt_id"] and not job["native_task_id"]:
            attempt = store.attempt(job["attempt_id"])
            if attempt["state"] != "complete" or attempt["generation"] != store.instance(attempt["instance_key"])["generation"]:
                raise ValueError("attempt_fenced")
        receipt["accepted"] = True
        atomic_json(path.parent / "checks.json", receipt)
        from .measurements import collect_verdict
        collect_verdict(store.root,job_id,receipt,True)
        with store.db(write=True) as db:
            db.execute("UPDATE jobs SET status='accepted',reason=NULL WHERE job_id=? AND status='checking'", (job_id,))
    except (OSError, SyntaxError, ValueError, KeyError, TypeError) as error:
        receipt.update(accepted=False, category=category, reason=str(error) if isinstance(error, ValueError) else type(error).__name__)
        atomic_json(store.root / "jobs" / job_id / "check-failure.json", receipt)
        from .measurements import collect_verdict
        collect_verdict(store.root,job_id,receipt,False,'source_changed' if str(error)=='source_changed' else category)
        if str(error) == "source_changed":
            with store.db(write=True) as db:
                db.execute("UPDATE jobs SET status=?,reason='source_changed' WHERE job_id=? AND status='checking'",
                           ('failed' if job['native_task_id'] else 'needs_reassessment', job_id))
        elif job["native_task_id"]:
            with store.db(write=True) as db: db.execute("UPDATE jobs SET status='failed',reason='fallback_checks_failed' WHERE job_id=? AND status='checking'", (job_id,))
        else: store.select_fallback(job_id, "candidate_checks_failed")
    return envelope(store.job(job_id))


def parse_proposal(text, brief):
    """Structural checks only. Semantic acceptance belongs to the native coordinator."""
    value = _candidate_json(text)
    summary = brief['capability'] == 'file_summary'
    expected = {'summary', 'claims' if summary else 'files'}
    if not isinstance(value, dict) or set(value) != expected or not isinstance(value['summary'], str):
        raise ValueError('invalid_candidate')
    if summary:
        if not isinstance(value['claims'], list) or not value['claims']: raise ValueError('invalid_candidate')
        for claim in value['claims']:
            if not isinstance(claim, dict) or set(claim) != {'text','path','sha256','start_line','end_line'}:
                raise ValueError('invalid_citation')
            if not isinstance(claim['path'], str) or not isinstance(claim['sha256'], str): raise ValueError('invalid_citation')
            item = brief['files'].get(claim['path'])
            if (not item or claim['sha256'] != item['sha256'] or not isinstance(claim['text'], str)
                    or not claim['text'] or type(claim['start_line']) is not int or type(claim['end_line']) is not int
                    or not 1 <= claim['start_line'] <= claim['end_line'] <= len(item['content'].splitlines())):
                raise ValueError('invalid_citation')
    else:
        files = value['files']
        if not isinstance(files, dict) or not files: raise ValueError('invalid_candidate')
        if not files.keys() <= set(brief['editable_paths']) or files.keys() & set(brief['acceptance']['protected_paths']):
            raise ValueError('candidate_path_not_allowed')
        for name, content in files.items():
            safe_path(Path(brief['source_root']), name)
            if not isinstance(content, str) or '\0' in content: raise ValueError('invalid_candidate')
    return value


class InvalidProposal(ValueError):
    """Invalid model output, distinct from corrupted state or unavailable verification."""


def _proposal(store, job):
    path = Path(job['result_path'])
    if path.is_symlink() or not path.resolve().is_relative_to(store.root / 'jobs' / job['job_id']): raise ValueError('unsafe_result')
    artifact = load_json(path.read_text())
    if text_hash(artifact['text']) != artifact['sha256']: raise ValueError('candidate_hash_mismatch')
    try: proposal = parse_proposal(artifact['text'], job['brief'])
    except ValueError as error: raise InvalidProposal(str(error)) from error
    return proposal, artifact['sha256']


def _verification_binding(job, candidate_hash):
    from .contracts import digest
    return {'job_id': job['job_id'], 'attempt_id': job['attempt_id'], 'native_task_id': job['native_task_id'],
            'candidate_hash': candidate_hash, 'source_hash': digest(job['brief']['files']),
            'acceptance_hash': digest(job['brief']['acceptance'])}


def prepare_verification(state_dir, job_id):
    try: return _prepare_verification(state_dir, job_id)
    except (ValueError, OSError) as error:
        store = Store(state_dir)
        job = store.job(job_id)
        if job['status'] in ('candidate_ready', 'checking') and str(error) != 'verification_busy':
            from .measurements import collect_verdict
            category = 'format' if isinstance(error, InvalidProposal) else 'verification'
            if str(error)=='source_changed': category='source_changed'
            receipt = {'accepted': False, 'error': type(error).__name__, 'category': category, 'reason': str(error)}
            atomic_json(store.root / 'jobs' / job_id / 'check-failure.json', receipt)
            collect_verdict(store.root,job_id,receipt,False,category)
            if str(error) == 'source_changed' or job['native_task_id']:
                with store.db(write=True) as db:
                    db.execute('UPDATE jobs SET status=?,reason=? WHERE job_id=?',
                               ('failed' if job['native_task_id'] else 'needs_reassessment',
                                'source_changed' if str(error) == 'source_changed' else 'native_verification_failed', job_id))
            else: store.select_fallback(job_id, 'verification_unsupported' if str(error) == 'verification_unsupported' else 'candidate_checks_failed')
        raise


def _prepare_verification(state_dir, job_id):
    from .store import private_dir
    from .worker import ownership
    store = Store(state_dir)
    with ownership(store, 'check-' + job_id) as owned:
        if not owned: raise ValueError('verification_busy')
        job = store.job(job_id)
        if job['status'] not in ('candidate_ready', 'checking'): raise ValueError('candidate_not_ready')
        validate_brief(job['brief'])
        if job['brief']['capability'] in PYTHON_CHANGE_CAPABILITIES: raise ValueError('use_python_checker')
        authorize_job(store, job, purpose='verify')
        if not source_matches(job['brief']): raise ValueError('source_changed')
        proposal, candidate_hash = _proposal(store, job)
        if job['brief']['capability'] != 'file_summary' and not _qualified_isolation():
            raise ValueError('verification_unsupported')
        binding = _verification_binding(job, candidate_hash)
        path = store.root / 'jobs' / job_id / 'verification.json'
        if path.exists():
            saved = load_json(path.read_text())
            if all(saved.get(k) == v for k, v in binding.items()):
                with store.db(write=True) as db: db.execute("UPDATE jobs SET status='checking' WHERE job_id=?", (job_id,))
                return saved
        stage = private_dir(store.root / 'jobs' / job_id / ('stage-' + uuid.uuid4().hex))
        files = {n: item['content'] for n, item in job['brief']['files'].items()}
        files.update(proposal.get('files', {}))
        for name, content in files.items():
            target = safe_path(stage, name)
            target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            target.write_text(content)
            target.chmod(0o600)
        session = {**binding, 'session_token': uuid.uuid4().hex + uuid.uuid4().hex,
                   'stage': str(stage), 'acceptance': job['brief']['acceptance'], 'claims': proposal.get('claims', [])}
        atomic_json(path, session)
        with store.db(write=True) as db:
            db.execute("UPDATE jobs SET status='checking' WHERE job_id=? AND status IN ('candidate_ready','checking')", (job_id,))
        return session


def record_verification(state_dir, job_id, receipt):
    from .worker import ownership
    store = Store(state_dir)
    with ownership(store, 'check-' + job_id) as owned:
        if not owned: raise ValueError('verification_busy')
        job = store.job(job_id)
        if job['status'] not in ('checking', 'accepted'): raise ValueError('candidate_not_ready')
        session = load_json((store.root / 'jobs' / job_id / 'verification.json').read_text())
        proposal, candidate_hash = _proposal(store, job)
        binding = _verification_binding(job, candidate_hash)
        required = set(binding) | {'session_token', 'criteria', 'checks', 'claims'}
        if (not isinstance(receipt, dict) or set(receipt) != required
                or any(session.get(k) != v or receipt.get(k) != v for k, v in binding.items())
                or receipt['session_token'] != session['session_token']): raise ValueError('verification_mismatch')
        if job['status'] == 'accepted':
            if receipt != load_json((store.root / 'jobs' / job_id / 'native-checks.json').read_text()):
                raise ValueError('verification_mismatch')
            return envelope(job)
        authorize_job(store, job, purpose='verify')
        if not source_matches(job['brief']):
            with store.db(write=True) as db:
                db.execute("UPDATE jobs SET status=?,reason='source_changed' WHERE job_id=? AND status='checking'",
                           ('failed' if job['native_task_id'] else 'needs_reassessment', job_id))
            raise ValueError('source_changed')
        if job['attempt_id'] and not job['native_task_id']:
            attempt = store.attempt(job['attempt_id'])
            if attempt['state'] != 'complete' or attempt['generation'] != store.instance(attempt['instance_key'])['generation']:
                raise ValueError('attempt_fenced')
        checks = {c['id'] for c in job['brief']['acceptance']['checks']}
        if (not isinstance(receipt['checks'], dict) or set(receipt['checks']) != checks
                or not isinstance(receipt['criteria'], list) or len(receipt['criteria']) != len(job['brief']['acceptance']['criteria'])
                or not isinstance(receipt['claims'], list) or len(receipt['claims']) != len(proposal.get('claims', []))):
            raise ValueError('incomplete_verification')
        passed = all(v is True for v in [*receipt['criteria'], *receipt['checks'].values(), *receipt['claims']])
        atomic_json(store.root / 'jobs' / job_id / 'native-checks.json', receipt)
        from .measurements import collect_verdict
        collect_verdict(store.root,job_id,receipt,passed,'semantic')
        if not passed and not job['native_task_id']:
            return store.select_fallback(job_id, 'native_verification_failed')
        with store.db(write=True) as db:
            state = 'accepted' if passed else ('failed' if job['native_task_id'] else 'fallback_required')
            db.execute("UPDATE jobs SET status=?,reason=? WHERE job_id=?", (state, None if passed else 'native_verification_failed', job_id))
        return envelope(store.job(job_id))


def run_native_checks(state_dir, job_id):
    """Run only predeclared native commands, inside the qualified sandbox, with no credentials."""
    session = prepare_verification(state_dir, job_id)
    root = Path(session['stage'])
    outcomes = {}
    for check in session['acceptance']['checks']:
        executable = Path(check['argv'][0])
        if not executable.is_file(): raise ValueError('verification_unsupported')
        # The sandbox denies the private receipt directory, even to candidate subprocesses.
        cwd = root if check['cwd'] == '.' else safe_path(root, check['cwd'])
        code = 'import os\nos.chdir(' + repr(str(cwd)) + ')\nos.execv(' + repr(str(executable)) + ',' + repr(check['argv']) + ')\n'
        result = run_isolated(root, code, check['timeout_seconds'], (str(executable.resolve().parent),))
        outcomes[check['id']] = result['returncode'] == 0 and result['reason'] is None
    return {'job_id': job_id, 'checks': outcomes}
