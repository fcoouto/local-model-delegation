import io
import json
from local_repair.lmstudio import ActivityWatch, Runtime, sse_events
from tests.support import FakeRuntime, Fixture


class Stream(Fixture):
    def test_active_for_600_seconds(self):
        watch = ActivityWatch(120, 0)
        for now in range(1, 601):
            watch.observe("reasoning.delta", {"content": "thinking"}, now)
            self.assertFalse(watch.is_stale(now))

    def test_silence_boundary(self):
        watch = ActivityWatch(120, 0)
        self.assertFalse(watch.is_stale(119.999))
        self.assertTrue(watch.is_stale(120))

    def test_observer_is_not_model_activity(self):
        watch = ActivityWatch(120, 0)
        watch.observe("prompt_processing.progress", {"progress": .2}, 10)
        for event, data in [("heartbeat", {}), ("prompt_processing.progress", {"progress": .2}),
                            ("reasoning.delta", {"content": ""}), ("prompt_processing.progress", {"progress": float("nan")})]:
            self.assertFalse(watch.observe(event, data, 50))
        self.assertTrue(watch.is_stale(130))
        watch.observe("reasoning.start", {}, 140)
        self.assertFalse(watch.observe("prompt_processing.start", {}, 160))

    def test_split_sse_unicode_and_final_result(self):
        raw = 'event: message.delta\r\ndata: {"content":"\u00e9"}\r\n\r\n'.encode()
        self.assertEqual(list(sse_events(io.BytesIO(raw))), [("message.delta", {"content": "\u00e9"})])
        server = FakeRuntime()
        self.addCleanup(server.close)
        events = list(Runtime(server.endpoint).stream({"model": "fixture-instance", "input": "hi", "stream": True}))
        self.assertEqual(events[-1][0], "chat.end")
        self.assertEqual(events[-1][1]["result"]["output"][0]["content"], server.answer)

    def test_invalid_transport_and_oversized_event(self):
        for endpoint in ["https://127.0.0.1:1", "http://example.com", "http://user:secret@127.0.0.1", "http://127.0.0.1/other"]:
            with self.assertRaises(ValueError): Runtime(endpoint)
        with self.assertRaises(ValueError): list(sse_events(io.BytesIO(b"data:" + b"x" * 1100000 + b"\n\n")))
