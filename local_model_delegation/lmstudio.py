"""Native HTTP/SSE only. Activity observations are independent of observer health."""
import http.client
import math
import os
import re
import socket
from urllib.parse import urlsplit
from .contracts import MAX_ANSWER_BYTES, canonical, load_json, positive


def sse_events(stream):
    event, data, size = "", [], 0
    while True:
        line = stream.readline(1024 * 1024 + 1)
        if not line:
            if data: raise ValueError("incomplete_sse_frame")
            return
        size += len(line)
        if size > 1024 * 1024: raise ValueError("oversized_sse_event")
        line = line.decode("utf-8").rstrip("\r\n")
        if not line:
            if data:
                value = load_json("\n".join(data))
                if not isinstance(value, dict): raise ValueError("invalid_sse_event")
                yield event or value.get("type", ""), value
            event, data, size = "", [], 0
        elif line.startswith("event:"):
            event = line[6:].lstrip(" ")
        elif line.startswith("data:"):
            data.append(line[5:].lstrip(" "))


class Runtime:
    def __init__(self, endpoint, token_env=None):
        url = urlsplit(endpoint)
        if (url.scheme != "http" or url.hostname not in ("127.0.0.1", "::1") or url.username or url.password
                or url.path not in ("", "/") or url.query or url.fragment):
            raise ValueError("unsupported_endpoint")
        self.host, self.port = url.hostname, url.port or 80
        self.connection = self.socket = None
        self.headers = {"Content-Type": "application/json"}
        if token_env is not None:
            if not isinstance(token_env, str) or not re.fullmatch(r"[A-Z][A-Z0-9_]*", token_env): raise ValueError("invalid_token_reference")
            token = os.environ.get(token_env)
            if not token or any(c in token for c in "\r\n"): raise ValueError("runtime_token_unavailable")
            self.headers["Authorization"] = "Bearer " + token

    def abort(self):
        sock = self.socket
        if sock:
            try: sock.shutdown(socket.SHUT_RDWR)
            except OSError: pass

    def _open(self, method, path, body=None, streaming=False, timeout=3):
        conn = http.client.HTTPConnection(self.host, self.port, timeout=timeout)
        self.connection = conn
        try:
            conn.connect()
            self.socket = conn.sock
            if streaming: conn.sock.settimeout(None)
            encoded = canonical(body).encode() if body is not None else None
            conn.request(method, path, body=encoded, headers=self.headers)
            response = conn.getresponse()
        except http.client.HTTPException:
            conn.close()
            raise ValueError("runtime_protocol_error") from None
        except BaseException:
            conn.close()
            raise
        if response.status != 200:
            conn.close()
            raise ValueError("runtime_http_error")
        return conn, response

    def _json(self, method, path, body=None, timeout=3):
        conn = None
        try:
            conn, response = self._open(method, path, body, timeout=timeout)
            raw = response.read(MAX_ANSWER_BYTES + 1)
            if len(raw) > MAX_ANSWER_BYTES: raise ValueError("oversized_runtime_response")
            return load_json(raw.decode())
        finally:
            if conn: conn.close()

    def list_models(self):
        return self._json("GET", "/api/v1/models")

    def load(self, body):
        return self._json("POST", "/api/v1/models/load", body, timeout=120)

    def unload(self, instance_id):
        return self._json("POST", "/api/v1/models/unload", {"instance_id": instance_id}, timeout=120)

    def stream(self, body):
        conn = None
        try:
            conn, response = self._open("POST", "/api/v1/chat", body, streaming=True)
            if "text/event-stream" not in response.getheader("Content-Type", ""):
                raise ValueError("unexpected_content_type")
            yield from sse_events(response)
        finally:
            if conn: conn.close()


class ActivityWatch:
    stages = {"prompt_processing.start": 1, "prompt_processing.end": 2, "reasoning.start": 3,
              "reasoning.end": 4, "message.start": 5, "message.end": 6}

    def __init__(self, stale_tolerance_seconds, started):
        if not positive(stale_tolerance_seconds): raise ValueError("invalid_stale_tolerance")
        self.tolerance, self.last = stale_tolerance_seconds, started
        self.rank, self.percentage, self.done = 0, -1, False

    def observe(self, event, data, now):
        if self.done: return False
        rank = self.stages.get(event, -1)
        advanced = rank > self.rank
        if event == "prompt_processing.progress":
            value = data.get("progress")
            advanced = (type(value) in (float, int) and math.isfinite(value) and 0 <= value <= 1
                        and value > self.percentage and self.rank <= 1)
            if advanced: self.percentage, rank = value, 1
        elif event in ("reasoning.delta", "message.delta"):
            rank = 3 if event == "reasoning.delta" else 5
            advanced = isinstance(data.get("content"), str) and bool(data["content"]) and rank >= self.rank
        if advanced:
            self.rank, self.last = rank, now
        return bool(advanced)

    def is_stale(self, now):
        return not self.done and now - self.last >= self.tolerance


def final_text(result):
    if not isinstance(result, dict) or not isinstance(result.get("output"), list):
        raise ValueError("invalid_final_result")
    if any(not isinstance(item, dict) or item.get("type") not in ("message", "reasoning") or not isinstance(item.get("content"), str) for item in result["output"]):
        raise ValueError("unsupported_completion")
    return "".join(item["content"] for item in result["output"] if item.get("type") == "message")


def select_loaded(snapshot, profile, assessment_identity=None):
    if (not isinstance(snapshot, dict) or not isinstance(snapshot.get("models"), list)
            or any(not isinstance(m, dict) for m in snapshot["models"])):
        raise ValueError("invalid_model_list")
    matches = [m for m in snapshot.get("models", []) if m.get("key") == profile["model_id"] and m.get("type") == "llm"]
    if len(matches) != 1: return None
    from .profiles import verify_runtime_binding, model_identity
    if assessment_identity is None: verify_runtime_binding(profile, matches[0])
    elif (assessment_identity != model_identity(profile)
          or any(matches[0].get(k) != v for k,v in assessment_identity["metadata"].items())):
        raise ValueError("runtime_binding_mismatch")
    instances = matches[0].get("loaded_instances")
    if not isinstance(instances, list): raise ValueError("invalid_model_list")
    if len(instances) != 1: return None
    instance = matches[0]["loaded_instances"][0]
    if not isinstance(instance, dict) or not isinstance(instance.get("config"), dict) or not isinstance(instance.get("id"), str):
        raise ValueError("invalid_model_list")
    capacity = instance.get("config", {}).get("parallel")
    if type(capacity) is not int or capacity <= 0: return None
    return {"endpoint": profile["endpoint"], "model_id": profile["model_id"], "instance_id": instance["id"],
            "capacity": capacity, "config": instance["config"], "binding_verified": profile.get("schema_version") == 2}


class ProgressWatch:
    def __init__(self, policy):
        from collections import deque
        if type(policy.get('max_output_tokens')) is not int or policy['max_output_tokens']<=0: raise ValueError('invalid_progress_policy')
        self.limit=policy['max_output_tokens']
        self.strict=policy.get('require_completion_metadata',True)
        self.buffer='';self.hashes=deque(maxlen=8);self.characters=0;self.reason=None

    def observe(self,event,data):
        from .contracts import text_hash
        if self.reason:return self.reason
        if event=='reasoning.delta':
            content=data.get('content')
            if not isinstance(content,str):raise ValueError('invalid_content')
            self.characters+=len(content);self.buffer+=content
            while len(self.buffer)>=2048:
                self.hashes.append(text_hash(self.buffer[:2048]));self.buffer=self.buffer[2048:]
                if len(self.hashes)==8 and len(set(self.hashes))==1:self.reason='suspected_loop'
        elif event=='chat.end':
            result=data.get('result',{});stats=result.get('stats',{})
            count=stats.get('total_output_tokens')
            if type(count) is not int or count<0:
                if self.strict:raise ValueError('unsupported_completion')
            elif count>=self.limit:self.reason='output_budget_exhausted'
        return self.reason

    def snapshot(self):
        return {'reasoning_characters':self.characters,'reasoning_window_hashes':list(self.hashes),'progress_reason':self.reason}
