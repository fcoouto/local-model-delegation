import io
import json
from local_model_delegation.lmstudio import ActivityWatch, Runtime, sse_events
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


class Progress(Fixture):
    def watch(self, **policy):
        from local_model_delegation import lmstudio
        self.assertTrue(hasattr(lmstudio,'ProgressWatch'),'ProgressWatch must exist')
        return lmstudio.ProgressWatch({'max_output_tokens':100,**policy})

    def test_repetition_detection_ignores_chunk_boundaries(self):
        text=('a'*2048)*8
        for size in (1,17,2048,len(text)):
            watch=self.watch(); reason=None
            for start in range(0,len(text),size): reason=watch.observe('reasoning.delta',{'content':text[start:start+size]}) or reason
            self.assertEqual(reason,'suspected_loop')
            self.assertNotIn('aaaa',str(watch.snapshot()))

    def test_repeated_code_text_is_not_a_reasoning_loop(self):
        watch=self.watch()
        self.assertIsNone(watch.observe('message.delta',{'content':'a'*2048*8}))

    def test_unique_reasoning_can_exceed_120_seconds(self):
        watch=self.watch(); activity=ActivityWatch(120,0)
        for i in range(300):
            text=str(i).ljust(2048,'x');activity.observe('reasoning.delta',{'content':text},i*10)
            self.assertIsNone(watch.observe('reasoning.delta',{'content':text}))
            self.assertFalse(activity.is_stale(i*10+1))

    def test_budget_exhaustion_cannot_accept_truncated_candidate(self):
        self.assertEqual(self.watch().observe('chat.end',{'result':{'stats':{'total_output_tokens':100}}}),'output_budget_exhausted')
        with self.assertRaisesRegex(ValueError,'unsupported_completion'):
            self.watch().observe('chat.end',{'result':{}})

    def test_nonreasoning_model_omits_unsupported_setting(self):
        from local_model_delegation.worker import build_model_request
        result=build_model_request({'capability':'file_summary','behavior_contract':'summary','files':{},'editable_paths':[]},
                             {'request_settings':{'temperature':0,'max_output_tokens':100}},'fixture')
        self.assertNotIn('reasoning',result)
