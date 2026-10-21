"""Transactional reservations and durable attempts. No network inside transactions."""
from contextlib import contextmanager
import os
from pathlib import Path
import sqlite3
import stat
import time
import uuid
from typing import Any
from .contracts import canonical, digest, envelope, load_json, validate_brief

ACTIVE = ("reserved", "submitting", "streaming", "uncertain")


def private_dir(path: Path) -> Path:
    path = Path(path)
    if path.is_symlink():
        raise ValueError("unsafe_state")
    if not path.parent.exists():
        private_dir(path.parent)
    path.mkdir(mode=0o700, exist_ok=True)
    s = path.stat()
    if s.st_uid != os.getuid() or s.st_mode & 0o077 or not stat.S_ISDIR(s.st_mode):
        raise ValueError("unsafe_state")
    return path.resolve()


def atomic_json(path: Path, value: Any) -> None:
    private_dir(path.parent)
    temp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, "w") as stream:
            stream.write(canonical(value) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try: os.fsync(directory)
        finally: os.close(directory)
    finally:
        temp.unlink(missing_ok=True)


class Store:
    def __init__(self, state_dir: Path):
        self.root = private_dir(Path(state_dir))
        self.path = self.root / "state.sqlite3"
        for suffix in ("", "-wal", "-shm"):
            path = Path(str(self.path) + suffix)
            if path.is_symlink() or (path.exists() and (path.stat().st_uid != os.getuid() or path.stat().st_mode & 0o077 or not path.is_file())):
                raise ValueError("unsafe_database")
        try:
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
        except FileExistsError:
            pass
        else:
            os.close(fd)
        with self.db() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript('''
                CREATE TABLE IF NOT EXISTS profiles (digest TEXT PRIMARY KEY, data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS jobs (
                  job_id TEXT PRIMARY KEY, chat TEXT NOT NULL, task_key TEXT NOT NULL, brief_hash TEXT NOT NULL,
                  brief TEXT NOT NULL, profile TEXT NOT NULL, status TEXT NOT NULL, reason TEXT,
                  attempt_id TEXT, result_path TEXT, native_task_id TEXT, UNIQUE(chat, task_key));
                CREATE TABLE IF NOT EXISTS instances (
                  instance_key TEXT PRIMARY KEY, generation INTEGER NOT NULL, state TEXT NOT NULL, data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS attempts (
                  attempt_id TEXT PRIMARY KEY, job_id TEXT NOT NULL REFERENCES jobs(job_id),
                  instance_key TEXT NOT NULL REFERENCES instances(instance_key), generation INTEGER NOT NULL,
                  state TEXT NOT NULL, data TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS occupied ON attempts(instance_key,state);
                CREATE TABLE IF NOT EXISTS fallback_dispatches (
                  job_id TEXT PRIMARY KEY REFERENCES jobs(job_id), token TEXT NOT NULL, task_name TEXT NOT NULL,
                  native_task_id TEXT, state TEXT NOT NULL);
            ''')

    @contextmanager
    def db(self, write=False):
        db = sqlite3.connect(self.path, timeout=0.25, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            if write: db.execute("BEGIN IMMEDIATE")
            yield db
            if write: db.commit()
        except BaseException:
            if write: db.rollback()
            raise
        finally:
            db.close()

    def _job(self, row):
        if row is None: raise ValueError("unknown_job")
        result = dict(row)
        for key in ("brief", "profile"): result[key] = load_json(result[key])
        result["fallback"] = result["profile"]["fallback"]
        return result

    def job(self, job_id):
        with self.db() as db:
            return self._job(db.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone())

    def lookup(self, chat_id, task_key):
        with self.db() as db:
            row = db.execute("SELECT * FROM jobs WHERE chat=? AND task_key=?", (chat_id, task_key)).fetchone()
            return envelope(self._job(row)) if row else None

    def reserve(self, brief, profile, loaded):
        validate_brief(brief)
        with self.db(write=True) as db:
            row = db.execute("SELECT * FROM jobs WHERE chat=? AND task_key=?", (brief["origin_chat_id"], brief["task_key"])).fetchone()
            if row:
                if row["brief_hash"] != digest(brief): raise ValueError("job_conflict")
                return envelope(self._job(row))
            job_id, attempt_id = uuid.uuid4().hex, None
            status, reason = "fallback_required", "model_unavailable"
            valid = bool(loaded and type(loaded.get("capacity")) is int and loaded["capacity"] > 0
                         and loaded.get("model_id") == profile["model_id"] and loaded.get("endpoint") == profile["endpoint"]
                         and isinstance(loaded.get("instance_id"), str) and loaded["instance_id"])
            if valid:
                key = digest([loaded["endpoint"], loaded["model_id"], loaded["instance_id"]])
                row = db.execute("SELECT * FROM instances WHERE instance_key=?", (key,)).fetchone()
                if row is None:
                    data = {**loaded, "profile": profile, "artifact_digest": profile["artifact"]["digest"]}
                    state = "ready" if loaded.get("binding_verified") else "closed"
                    db.execute("INSERT INTO instances VALUES (?,0,?,?)", (key, state, canonical(data)))
                    generation = 0
                else:
                    generation, state = row["generation"], row["state"]
                    data = load_json(row["data"])
                    if data["artifact_digest"] != profile["artifact"]["digest"]:
                        state = "closed"
                        db.execute("UPDATE instances SET state='closed' WHERE instance_key=?", (key,))
                occupied = db.execute("SELECT count(*) FROM attempts WHERE instance_key=? AND state IN ('reserved','submitting','streaming','uncertain')", (key,)).fetchone()[0]
                if state == "ready" and occupied < loaded["capacity"]:
                    attempt_id, status, reason = uuid.uuid4().hex, "reserved", None
                else:
                    reason = "instance_closed" if state != "ready" else "model_busy"
            db.execute("INSERT OR IGNORE INTO profiles VALUES (?,?)", (digest(profile), canonical(profile)))
            db.execute("INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?,?,?,?)", (job_id, brief["origin_chat_id"], brief["task_key"], digest(brief), canonical(brief), canonical(profile), status, reason, attempt_id, None, None))
            if attempt_id:
                db.execute("INSERT INTO attempts VALUES (?,?,?,?,?,?)", (attempt_id, job_id, key, generation, "reserved", canonical({"created": time.time()})))
            return envelope(self._job(db.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone()))

    def attempt(self, attempt_id):
        with self.db() as db:
            row = db.execute("SELECT * FROM attempts WHERE attempt_id=?", (attempt_id,)).fetchone()
            if row is None: raise ValueError("unknown_attempt")
            return {**dict(row), "data": load_json(row["data"])}

    def instance(self, key):
        with self.db() as db:
            row = db.execute("SELECT * FROM instances WHERE instance_key=?", (key,)).fetchone()
            if row is None: raise ValueError("unknown_instance")
            return {**dict(row), "data": load_json(row["data"])}

    def transition(self, attempt_id, generation, expected, target, fields):
        allowed = {"reserved": {"submitting", "released", "uncertain"}, "submitting": {"streaming", "uncertain"},
                   "streaming": {"complete", "uncertain"}, "complete": {"released"}, "uncertain": {"released"}}
        if target not in allowed.get(expected, set()): return False
        with self.db(write=True) as db:
            row = db.execute("SELECT a.*,i.generation AS current_generation FROM attempts a JOIN instances i USING(instance_key) WHERE attempt_id=?", (attempt_id,)).fetchone()
            if row is None or row["generation"] != generation or row["current_generation"] != generation or row["state"] != expected:
                return False
            data = {**load_json(row["data"]), **fields}
            db.execute("UPDATE attempts SET state=?,data=? WHERE attempt_id=?", (target, canonical(data), attempt_id))
            if target in ("submitting", "streaming"):
                db.execute("UPDATE jobs SET status='running' WHERE job_id=? AND status IN ('reserved','running')", (row["job_id"],))
            return True

    def observe(self, attempt_id, fields):
        with self.db(write=True) as db:
            row = db.execute("SELECT data FROM attempts WHERE attempt_id=?", (attempt_id,)).fetchone()
            if row:
                db.execute("UPDATE attempts SET data=? WHERE attempt_id=?", (canonical({**load_json(row["data"]), **fields}), attempt_id))

    def select_fallback(self, job_id, reason):
        with self.db(write=True) as db:
            row = db.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone()
            job = self._job(row)
            if job["status"] in ("reserved", "running", "candidate_ready", "checking"):
                db.execute("UPDATE jobs SET status='fallback_required',reason=? WHERE job_id=?", (reason, job_id))
            return envelope(self._job(db.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone()))

    def publish_candidate(self, attempt_id, generation, path):
        with self.db(write=True) as db:
            row = db.execute("SELECT a.*,j.status,i.generation AS current_generation FROM attempts a JOIN jobs j USING(job_id) JOIN instances i USING(instance_key) WHERE a.attempt_id=?", (attempt_id,)).fetchone()
            if (row is None or row["generation"] != generation or row["current_generation"] != generation
                    or row["state"] != "streaming" or row["status"] != "running"):
                return False
            db.execute("UPDATE attempts SET state='complete' WHERE attempt_id=?", (attempt_id,))
            db.execute("UPDATE jobs SET status='candidate_ready',result_path=? WHERE job_id=?", (str(path), row["job_id"]))
            return True

    def claim_fallback(self, job_id):
        with self.db(write=True) as db:
            job = self._job(db.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone())
            row = db.execute("SELECT * FROM fallback_dispatches WHERE job_id=?", (job_id,)).fetchone()
            first = row is None
            if first:
                if job["status"] != "fallback_required": raise ValueError("fallback_not_required")
                token, task_name = uuid.uuid4().hex, "local_repair_" + job_id
                db.execute("INSERT INTO fallback_dispatches VALUES (?,?,?,NULL,'dispatching')", (job_id, token, task_name))
                db.execute("UPDATE jobs SET status='fallback_dispatching' WHERE job_id=?", (job_id,))
                row = db.execute("SELECT * FROM fallback_dispatches WHERE job_id=?", (job_id,)).fetchone()
            return {**envelope(job), "dispatch_token": row["token"], "task_name": row["task_name"],
                    "native_task_id": row["native_task_id"], "may_dispatch": first, "brief": job["brief"],
                    "status": "fallback_dispatching" if first else job["status"]}

    def attach_fallback(self, job_id, dispatch_token, native_task_id):
        with self.db(write=True) as db:
            row = db.execute("SELECT * FROM fallback_dispatches WHERE job_id=?", (job_id,)).fetchone()
            if (row is None or row["token"] != dispatch_token or not isinstance(native_task_id, str)
                    or native_task_id.rsplit("/", 1)[-1] != row["task_name"]): return False
            if row["native_task_id"]: return row["native_task_id"] == native_task_id
            if row["state"] not in ("dispatching", "uncertain"): return False
            db.execute("UPDATE fallback_dispatches SET state='running',native_task_id=? WHERE job_id=?", (native_task_id, job_id))
            db.execute("UPDATE jobs SET status='fallback_running',native_task_id=? WHERE job_id=? AND status IN ('fallback_dispatching','dispatch_uncertain')", (native_task_id, job_id))
            return True

    def mark_dispatch_uncertain(self, job_id, dispatch_token):
        with self.db(write=True) as db:
            row = db.execute("SELECT * FROM fallback_dispatches WHERE job_id=?", (job_id,)).fetchone()
            if row is None or row["token"] != dispatch_token: raise ValueError("invalid_dispatch_token")
            if not row["native_task_id"]:
                db.execute("UPDATE fallback_dispatches SET state='uncertain' WHERE job_id=?", (job_id,))
                db.execute("UPDATE jobs SET status='dispatch_uncertain',reason='native_dispatch_uncertain' WHERE job_id=? AND status='fallback_dispatching'", (job_id,))

    def record_fallback_candidate(self, job_id, native_task_id, candidate):
        from .contracts import MAX_ANSWER_BYTES, text_hash
        job = self.job(job_id)
        if job["native_task_id"] != native_task_id: raise ValueError("native_task_mismatch")
        if job["status"] != "fallback_running": return envelope(job)
        candidate = Path(candidate)
        if candidate.is_symlink() or candidate.stat().st_size > MAX_ANSWER_BYTES: raise ValueError("unsafe_candidate")
        text = candidate.read_text()
        from .validation import parse_candidate
        parse_candidate(text, job["brief"])
        path = self.root / "jobs" / job_id / ("native-" + uuid.uuid4().hex) / "candidate.json"
        atomic_json(path, {"text": text, "sha256": text_hash(text), "native_task_id": native_task_id})
        with self.db(write=True) as db:
            db.execute("UPDATE jobs SET status='candidate_ready',result_path=? WHERE job_id=? AND native_task_id=? AND status='fallback_running'", (str(path), job_id, native_task_id))
        return envelope(self.job(job_id))
