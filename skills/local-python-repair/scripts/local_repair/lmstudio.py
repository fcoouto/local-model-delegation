"""Native HTTP/SSE only. Activity observations are independent of observer health."""
import http.client
import math
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
    def __init__(self, endpoint):
        url = urlsplit(endpoint)
        if (url.scheme != "http" or url.hostname not in ("127.0.0.1", "::1") or url.username or url.password
                or url.path not in ("", "/") or url.query or url.fragment):
            raise ValueError("unsupported_endpoint")
        self.host, self.port = url.hostname, url.port or 80
        self.connection = self.socket = None

    def abort(self):
        sock = self.socket
        if sock:
            try: sock.shutdown(socket.SHUT_RDWR)
            except OSError: pass

    def _open(self, method, path, body=None, streaming=False, timeout=3):
        conn = http.client.HTTPConnection(self.host, self.port, timeout=timeout)
        self.connection = conn
        conn.connect()
        self.socket = conn.sock
        if streaming: conn.sock.settimeout(None)
        encoded = canonical(body).encode() if body is not None else None
        conn.request(method, path, body=encoded, headers={"Content-Type": "application/json"})
        response = conn.getresponse()
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
    return "".join(item["content"] for item in result["output"] if item.get("type") == "message")


def select_loaded(snapshot, profile):
    matches = [m for m in snapshot.get("models", []) if m.get("key") == profile["model_id"] and m.get("type") == "llm"]
    if len(matches) != 1 or len(matches[0].get("loaded_instances", [])) != 1: return None
    instance = matches[0]["loaded_instances"][0]
    capacity = instance.get("config", {}).get("parallel")
    if type(capacity) is not int or capacity <= 0: return None
    return {"endpoint": profile["endpoint"], "model_id": profile["model_id"], "instance_id": instance["id"],
            "capacity": capacity, "config": instance["config"], "binding_verified": False}
