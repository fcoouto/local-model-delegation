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
    if path.is_symlink() or any(parent.is_symlink() for parent in path.absolute().parents):
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
            try: stamp = path.lstat()
            except FileNotFoundError: continue
            if stamp.st_uid != os.getuid() or stamp.st_mode & 0o077 or not stat.S_ISREG(stamp.st_mode):
                raise ValueError("unsafe_database")
        try:
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
        except FileExistsError:
            pass
        else:
            os.close(fd)
        with self.db() as db:
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 2): raise ValueError("unsupported_state_version")
            if version == 0 and db.execute("SELECT 1 FROM sqlite_master WHERE type='table'").fetchone():
                raise ValueError("unsupported_state_version")
            db.execute("PRAGMA journal_mode=WAL")
            if version == 0:
                db.executescript('''
                    CREATE TABLE IF NOT EXISTS profiles (digest TEXT PRIMARY KEY, data TEXT NOT NULL);
                    CREATE TABLE IF NOT EXISTS jobs (
                      job_id TEXT PRIMARY KEY, chat TEXT NOT NULL, task_key TEXT NOT NULL, brief_hash TEXT NOT NULL,
                      brief TEXT NOT NULL, profile TEXT NOT NULL, status TEXT NOT NULL, reason TEXT,
                      attempt_id TEXT, result_path TEXT, native_task_id TEXT,
                      fallback TEXT, queued_at REAL, route_data TEXT NOT NULL DEFAULT '{}', UNIQUE(chat, task_key));
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
                    CREATE TRIGGER IF NOT EXISTS finish_native_dispatch AFTER UPDATE OF status ON jobs
                      WHEN NEW.status IN ('accepted','failed')
                      BEGIN UPDATE fallback_dispatches SET state=CASE WHEN NEW.status='accepted' THEN 'complete' ELSE 'failed' END
                      WHERE job_id=NEW.job_id; END;
                ''')
                self.initialize_schema(db)

    @staticmethod
    def initialize_schema(db):
        db.execute("CREATE TABLE IF NOT EXISTS model_operations (operation_id TEXT PRIMARY KEY, model_key TEXT NOT NULL, state TEXT NOT NULL, data TEXT NOT NULL)")
        db.execute("PRAGMA user_version=2")
        db.execute("""CREATE TRIGGER IF NOT EXISTS job_observation AFTER UPDATE OF status,reason,result_path,native_task_id ON jobs
          WHEN OLD.status IS NOT NEW.status OR OLD.reason IS NOT NEW.reason OR OLD.result_path IS NOT NEW.result_path OR OLD.native_task_id IS NOT NEW.native_task_id
          BEGIN UPDATE jobs SET route_data=json_set(route_data,'$.observed_at',CAST(strftime('%s','now') AS REAL)) WHERE job_id=NEW.job_id; END""")

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
        if write:
            try:
                from .visibility import publish_visibility
                publish_visibility(self.root)
            except Exception: pass  # Observability never changes a committed task outcome.

    def _job(self, row):
        if row is None: raise ValueError("unknown_job")
        result = dict(row)
        for key in ("brief", "profile"): result[key] = load_json(result[key])
        result["fallback"] = load_json(result["fallback"]) if result["fallback"] else None
        if "route_data" in result: result["route_data"] = load_json(result["route_data"])
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
            if db.execute("PRAGMA user_version").fetchone()[0] != profile.get("schema_version"):
                raise ValueError("mixed_state_version")
            row = db.execute("SELECT * FROM jobs WHERE chat=? AND task_key=?", (brief["origin_chat_id"], brief["task_key"])).fetchone()
            if row:
                if row["brief_hash"] != digest(brief): raise ValueError("job_conflict")
                return envelope(self._job(row))
            job_id, attempt_id = uuid.uuid4().hex, None
            status, reason = "fallback_required", "model_unavailable"
            attempt_id, status, reason, key, generation = self._slot(db, profile, loaded)
            db.execute("INSERT OR IGNORE INTO profiles VALUES (?,?)", (digest(profile), canonical(profile)))
            db.execute("INSERT INTO jobs (job_id,chat,task_key,brief_hash,brief,profile,status,reason,attempt_id,result_path,native_task_id,fallback) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", (job_id, brief["origin_chat_id"], brief["task_key"], digest(brief), canonical(brief), canonical(profile), status, reason, attempt_id, None, None, canonical(brief['fallback'])))
            if attempt_id:
                db.execute("INSERT INTO attempts VALUES (?,?,?,?,?,?)", (attempt_id, job_id, key, generation, "reserved", canonical({"created": time.time()})))
            return envelope(self._job(db.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone()))

    def _slot(self, db, profile, loaded):
        attempt_id, status, reason, key, generation = None, "fallback_required", "model_unavailable", None, None
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
                if (data["artifact_digest"] != profile["artifact"]["digest"]
                        or data["profile"]["approval"] != profile["approval"]):
                    state = "closed"
                    db.execute("UPDATE instances SET state='closed' WHERE instance_key=?", (key,))
            occupied = db.execute("SELECT count(*) FROM attempts WHERE instance_key=? AND state IN ('reserved','submitting','streaming','uncertain')", (key,)).fetchone()[0]
            if state == "ready" and occupied < loaded["capacity"]:
                attempt_id, status, reason = uuid.uuid4().hex, "reserved", None
            else:
                reason = "instance_closed" if state != "ready" else "model_busy"
        return attempt_id, status, reason, key, generation

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
            if target == "submitting":
                job = db.execute("SELECT status FROM jobs WHERE job_id=?", (row["job_id"],)).fetchone()
                instance = db.execute("SELECT state FROM instances WHERE instance_key=?", (row["instance_key"],)).fetchone()
                if job["status"] != "reserved" or instance["state"] != "ready": return False
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
            if job["status"] in ("waiting", "reserved", "running", "candidate_ready", "checking"):
                if job.get("attempt_id") and "route_data" in job:
                    route = {**job["route_data"], "local_failure": reason}
                    db.execute("UPDATE jobs SET route_data=? WHERE job_id=?", (canonical(route), job_id))
                db.execute("UPDATE jobs SET status='fallback_required',reason=? WHERE job_id=?", (reason, job_id))
            return envelope(self._job(db.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone()))

    def publish_candidate(self, attempt_id, generation, path):
        with self.db(write=True) as db:
            row = db.execute("SELECT a.*,j.status,i.generation AS current_generation FROM attempts a JOIN jobs j USING(job_id) JOIN instances i USING(instance_key) WHERE a.attempt_id=?", (attempt_id,)).fetchone()
            if (row is None or row["generation"] != generation or row["current_generation"] != generation
                    or row["state"] != "streaming" or row["status"] != "running"):
                return False
            data = {**load_json(row["data"]), "finished_at": time.time()}
            db.execute("UPDATE attempts SET state='complete',data=? WHERE attempt_id=?", (canonical(data), attempt_id))
            db.execute("UPDATE jobs SET status='candidate_ready',result_path=? WHERE job_id=?", (str(path), row["job_id"]))
            return True

    def claim_fallback(self, job_id):
        with self.db(write=True) as db:
            job = self._job(db.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone())
            if job.get("route_data", {}).get("assessment"): raise ValueError("assessment_has_no_native_fallback")
            row = db.execute("SELECT * FROM fallback_dispatches WHERE job_id=?", (job_id,)).fetchone()
            first = row is None
            if first:
                if job["status"] != "fallback_required": raise ValueError("fallback_not_required")
                token, task_name = uuid.uuid4().hex, "local_delegation_" + job_id
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
        path = self.root / "jobs" / job_id / ("native-" + uuid.uuid4().hex) / "candidate.json"
        atomic_json(path, {"text": text, "sha256": text_hash(text), "native_task_id": native_task_id})
        with self.db(write=True) as db:
            db.execute("UPDATE jobs SET status='candidate_ready',result_path=? WHERE job_id=? AND native_task_id=? AND status='fallback_running'", (str(path), job_id, native_task_id))
        return envelope(self.job(job_id))

    def enqueue(self, brief, fallback, assessment=None, measurement=None):
        from .contracts import validate_fallback
        from .profiles import read_config
        from .measurements import bind_enqueued, validate_context
        if measurement is not None: validate_context(measurement)
        validate_brief(brief); validate_fallback(fallback)
        if brief['schema_version'] != 2 or brief['fallback'] != fallback: raise ValueError('invalid_brief')
        if assessment:
            from .onboarding import authorize_assessment
            authorize_assessment(self.root, brief, assessment)
        elif read_config(self.root).get('routing_enabled') is not True: raise ValueError('routing_disabled')
        with self.db(write=True) as db:
            if db.execute('PRAGMA user_version').fetchone()[0] != 2: raise ValueError('mixed_state_version')
            row=db.execute('SELECT * FROM jobs WHERE chat=? AND task_key=?',(brief['origin_chat_id'],brief['task_key'])).fetchone()
            if row:
                if row['brief_hash'] != digest(brief): raise ValueError('job_conflict')
                bind_enqueued(db,row['job_id'],measurement)
                return envelope(self._job(row))
            identifier, now=uuid.uuid4().hex,time.time()
            route={'wait_until':now+brief['task_requirements']['wait_budget_seconds'],'observed_at':now}
            if assessment: route['assessment']=assessment
            db.execute("INSERT INTO jobs (job_id,chat,task_key,brief_hash,brief,profile,status,reason,fallback,queued_at,route_data) VALUES (?,?,?,?,?,'{}','waiting','waiting_for_slot',?,?,?)",
                       (identifier,brief['origin_chat_id'],brief['task_key'],digest(brief),canonical(brief),canonical(fallback),now,canonical(route)))
            bind_enqueued(db,identifier,measurement)
            return envelope(self._job(db.execute('SELECT * FROM jobs WHERE job_id=?',(identifier,)).fetchone()))

    def waiting_jobs(self, now=None):
        now=time.time() if now is None else now
        with self.db() as db: jobs=[self._job(r) for r in db.execute("SELECT * FROM jobs WHERE status='waiting'")]
        return sorted(jobs,key=lambda j:(0 if j['brief']['task_requirements']['urgency']=='urgent' or now-j['queued_at']>=300 else 1,j['queued_at'],j['job_id']))

    def admit(self, job_id, profile, loaded, resource_snapshot=None):
        from .profiles import authorize_job
        from .validation import source_matches
        with self.db(write=True) as db:
            job=self._job(db.execute('SELECT * FROM jobs WHERE job_id=?',(job_id,)).fetchone())
            if job['status']!='waiting': return envelope(job)
            route=job['route_data']
            if not source_matches(job['brief']):
                db.execute("UPDATE jobs SET status='needs_reassessment',reason='source_changed' WHERE job_id=?",(job_id,))
            elif time.time()>=route['wait_until']:
                db.execute("UPDATE jobs SET reason='route_decision_required' WHERE job_id=?",(job_id,))
            else:
                current=authorize_job(self,{**job,'profile':profile})
                from .worker import context_fits
                if loaded and not context_fits(job['brief'],current,loaded):
                    db.execute("UPDATE jobs SET status='fallback_required',reason='context_budget_exceeded' WHERE job_id=?",(job_id,))
                    return envelope(self._job(db.execute('SELECT * FROM jobs WHERE job_id=?',(job_id,)).fetchone()))
                from .capacity import pressure_snapshot
                # Hashing can outlast an observation; sample after authorization.
                if resource_snapshot is None: resource_snapshot=pressure_snapshot()
                if time.time()>=route['wait_until']:
                    db.execute("UPDATE jobs SET reason='route_decision_required' WHERE job_id=?",(job_id,))
                    return envelope(self._job(db.execute('SELECT * FROM jobs WHERE job_id=?',(job_id,)).fetchone()))
                from .scheduler import admission_limit
                resources=dict(resource_snapshot)
                limit=admission_limit(current,loaded,resources)
                if db.execute("SELECT 1 FROM sqlite_master WHERE name='measurement_tasks'").fetchone():
                    if db.execute('SELECT 1 FROM measurement_tasks WHERE job_id=?',(job_id,)).fetchone():
                        route['measurement_resource_sample'] = {k:resource_snapshot.get(k) for k in ('observed_at','pressure','swapout_delta_bytes','available_bytes')}
                        db.execute('UPDATE jobs SET route_data=? WHERE job_id=?',(canonical(route),job_id))
                request_bytes=current.get('capacity_evidence',{}).get('request_bytes',0)
                if route.get('assessment'):
                    from .capacity import inference_available,assessment_request_bytes
                    from .onboarding import _assessment
                    assessment=_assessment(self.root,route['assessment']['assessment_id'])
                    target=assessment.get('capacity_target',1)
                    request_bytes=assessment_request_bytes(assessment)
                    limit=min(target,loaded['capacity']) if loaded and type(loaded.get('capacity')) is int and loaded['capacity']>0 and inference_available(resources) else 0
                if limit:
                    attempt,status,reason,key,generation=self._slot(db,current,{**loaded,'capacity':limit})
                    if attempt:
                        route.update(observed_at=time.time(),approval_digest=digest(current['approval']),evidence_revision=digest(current.get('assessment',{})),request_bytes=request_bytes)
                        if db.execute("SELECT 1 FROM sqlite_master WHERE name='measurement_tasks'").fetchone():
                            if db.execute('SELECT 1 FROM measurement_tasks WHERE job_id=?',(job_id,)).fetchone():
                                from .measurements import model_binding
                                route['measurement_binding'] = model_binding(current,executed=True)
                        db.execute('UPDATE jobs SET profile=?,status=?,reason=NULL,attempt_id=?,route_data=? WHERE job_id=?',
                                   (canonical(current),status,attempt,canonical(route),job_id))
                        db.execute('INSERT INTO attempts VALUES (?,?,?,?,?,?)',(attempt,job_id,key,generation,'reserved',canonical({'created':time.time()})))
                    else: db.execute('UPDATE jobs SET reason=? WHERE job_id=?',(reason,job_id))
                else: db.execute("UPDATE jobs SET reason='capacity_unqualified' WHERE job_id=?",(job_id,))
            return envelope(self._job(db.execute('SELECT * FROM jobs WHERE job_id=?',(job_id,)).fetchone()))

    def submission_resources_available(self, job):
        from .capacity import pressure_snapshot, inference_available
        return inference_available(pressure_snapshot())

    def decide_wait(self, job_id, decision):
        from .contracts import positive
        if not isinstance(decision,dict) or not isinstance(decision.get('reason'),str) or not decision['reason'].strip(): raise ValueError('invalid_wait_decision')
        with self.db(write=True) as db:
            job=self._job(db.execute('SELECT * FROM jobs WHERE job_id=?',(job_id,)).fetchone())
            if job['status']!='waiting': return envelope(job)
            route=job['route_data']
            if decision.get('action')=='fallback' and set(decision)=={'action','reason'}:
                db.execute("UPDATE jobs SET status='fallback_required',reason=? WHERE job_id=?",(decision['reason'],job_id))
            elif decision.get('action')=='extend' and set(decision)=={'action','until','reason'} and positive(decision['until']) and decision['until']>max(time.time(),route['wait_until']):
                route.update(wait_until=decision['until'],wait_decision=decision,observed_at=time.time())
                db.execute("UPDATE jobs SET reason='waiting_for_slot',route_data=? WHERE job_id=?",(canonical(route),job_id))
            else: raise ValueError('invalid_wait_decision')
            return envelope(self._job(db.execute('SELECT * FROM jobs WHERE job_id=?',(job_id,)).fetchone()))

    def reserve_load(self, profile, estimate, resources):
        from .capacity import available_budget
        from .contracts import positive
        if not isinstance(estimate,dict) or estimate.get('non_evicting') is not True or not positive(estimate.get('bytes')):
            raise ValueError('lifecycle_unqualified')
        model_key=digest([profile['endpoint'],profile['model_id']])
        with self.db(write=True) as db:
            existing=db.execute("SELECT * FROM model_operations WHERE model_key=? AND state IN ('reserved','submitting','uncertain')",(model_key,)).fetchone()
            if existing:
                data=load_json(existing['data'])
                if data['artifact_digest']!=profile['artifact']['digest'] or data['settings_digest']!=digest(profile['request_settings']):
                    raise ValueError('operation_identity_changed')
                return {**dict(existing),'data':data}
            held=sum(load_json(r['data']).get('reserved_bytes',0) for r in db.execute("SELECT data FROM model_operations WHERE state IN ('reserved','submitting','uncertain')"))
            if estimate['bytes']>available_budget(resources)-held:raise ValueError('insufficient_resources')
            operation=uuid.uuid4().hex
            data={'kind':'load','reserved_bytes':estimate['bytes'],'profile_id':profile['profile_id'],
                  'artifact_digest':profile['artifact']['digest'],'settings_digest':digest(profile['request_settings']),
                  'observed_at':time.time(),'machine_fingerprint':resources['machine_fingerprint']}
            db.execute("INSERT INTO model_operations VALUES (?,?,'reserved',?)",(operation,model_key,canonical(data)))
            return {'operation_id':operation,'model_key':model_key,'state':'reserved','data':data}

    def visibility_rows(self):
        from .visibility import read_rows
        return read_rows(self.path)
