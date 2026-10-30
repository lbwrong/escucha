"""说话人区分（Meta 并行）+ 打字翻译走 Meta 的单元测试。Run: .venv/bin/python -m unittest tests/test_diarize.py"""
import asyncio, json, os, sys, pathlib, unittest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import aiohttp
from aiohttp import web
import server, assist as A


class FakeMetaASR:
    """假 Meta 实时转写 WebSocket：握手回 sessionId，收到约 0.5 s 音频后发 speechStart/speaker 事件。"""
    async def start(self, fail=False):
        self.got_handshake, self.bytes, self.fail = None, 0, fail
        async def ws(req):
            w = web.WebSocketResponse(); await w.prepare(req)
            first = await w.receive(); self.got_handshake = json.loads(first.data)
            if self.fail:
                await w.send_json({"type": "error", "message": "nope"}); await w.close(); return w
            await w.send_json({"sessionId": "fake"})
            sent = False
            async for m in w:
                if m.type == aiohttp.WSMsgType.BINARY:
                    self.bytes += len(m.data)
                    if self.bytes >= 24000 and not sent:
                        sent = True
                        await w.send_json({"type": "speechStart", "turnId": 1, "audioProcessedMs": 100})
                        await w.send_json({"type": "speaker", "label": "A", "audioProcessedMs": 400})
                        await w.send_json({"type": "speaker", "label": "B", "audioProcessedMs": 500})
                elif m.type == aiohttp.WSMsgType.TEXT and json.loads(m.data).get("type") == "endStream":
                    break
            return w
        app = web.Application(); app.router.add_get("/v1/asr/realtime", ws)
        self.runner = web.AppRunner(app); await self.runner.setup()
        site = web.TCPSite(self.runner, "127.0.0.1", 0); await site.start()
        return f"ws://127.0.0.1:{site._server.sockets[0].getsockname()[1]}/v1/asr/realtime"


class DiarizeTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.saved = {k: os.environ.get(k) for k in ("META_API_KEY", "DIARIZE")}
        os.environ["META_API_KEY"] = "test-key"; os.environ.pop("DIARIZE", None)
        self.http = aiohttp.ClientSession(); self.fake = FakeMetaASR()

    async def asyncTearDown(self):
        await self.http.close()
        if getattr(self.fake, "runner", None): await self.fake.runner.cleanup()
        for k, v in self.saved.items():
            if v is None: os.environ.pop(k, None)
            else: os.environ[k] = v

    def test_enabled_rules(self):
        self.assertTrue(server.diarize_enabled("zh", "es"))
        self.assertFalse(server.diarize_enabled("zh", "ru")); self.assertFalse(server.diarize_enabled("uk", "en"))
        os.environ["DIARIZE"] = "0"; self.assertFalse(server.diarize_enabled("zh", "es"))
        os.environ.pop("DIARIZE"); os.environ["META_API_KEY"] = ""; self.assertFalse(server.diarize_enabled("zh", "es"))

    async def test_spans_with_base_offset_and_handshake(self):
        server.META_ASR_URL = await self.fake.start()
        out, ms = [], {"v": 2000}
        async def send(o): out.append(o)
        d = server.Diarizer(send, self.http, "zh", "es", lambda: ms["v"])
        await d.start()
        self.assertEqual(out[0], {"type": "speakerStatus", "ok": True})
        h = self.fake.got_handshake
        self.assertEqual((h["mode"], h["audioEncoding"], h["model"]), ("DIARIZATION", "PCM_24KHZ", "muse-voice-transcribe-1.0"))
        self.assertEqual(h["languageBias"], ["Spanish", "Mandarin Chinese"]); self.assertEqual(h["authorization"]["accessToken"], "Bearer test-key")
        for _ in range(10): d.feed(b"\0" * 3840)   # 0.8 s audio
        for _ in range(50):
            await asyncio.sleep(0.02)
            if len(out) >= 3: break
        await d.close()
        self.assertEqual(out[1], {"type": "speaker", "label": "A", "startMs": 2100, "endMs": 2400})
        self.assertEqual(out[2], {"type": "speaker", "label": "B", "startMs": 2400, "endMs": 2500})

    async def test_meta_failure_is_silent(self):
        server.META_ASR_URL = await self.fake.start(fail=True)
        out = []
        async def send(o): out.append(o)
        d = server.Diarizer(send, self.http, "zh", "es", lambda: 0)
        await d.start()
        self.assertEqual(out, [{"type": "speakerStatus", "ok": False}]); self.assertTrue(d.closed)
        d.feed(b"\0" * 10)   # no error, nothing queued
        self.assertEqual(d.q.qsize(), 0)

    def test_feed_never_blocks(self):
        d = server.Diarizer(None, None, "zh", "es", lambda: 0); d.ready = True
        for _ in range(1000): d.feed(b"x")
        self.assertEqual(d.q.qsize(), 400)

    async def test_soniox_final_has_times_on_shared_timeline(self):
        r = server.SonioxRelay.__new__(server.SonioxRelay); server.MetaRelay.__init__(r, None, None)
        r.orig, r.orig_lang, r.tr, r.cur_id, r.cur_lang, out = "", None, "", None, None, []
        r.base_ms = 5000
        async def send(o): out.append(o)
        r.send = send
        await r.handle_event({"tokens": [{"text": "Hola", "is_final": True, "language": "es", "start_ms": 120, "end_ms": 400},
                                          {"text": " amigo", "is_final": True, "language": "es", "start_ms": 420, "end_ms": 900}, {"text": "<end>", "is_final": True}]})
        f = [o for o in out if o["type"] == "final"][0]
        self.assertEqual((f["startMs"], f["endMs"]), (5120, 5900))


class TypedTranslateMeta(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.saved = {k: os.environ.get(k) for k in ("LLM_BASE_URL", "LLM_API_KEY", "LLM_FAST_MODEL", "LLM_TRANSLATE_MODEL", "LLM_FALLBACK_MODEL", "LLM_TRANSLATE_FALLBACK", "META_BASE_URL", "META_API_KEY", "TRANSLATE_TIMEOUT")}
        self.calls = []
        async def meta(req):
            b = await req.json(); self.calls.append(("meta", b["model"])); await asyncio.sleep(0.5)
            return web.json_response({"choices": [{"message": {"content": "meta"}}]})
        async def newapi(req):
            b = await req.json(); self.calls.append(("newapi", b["model"]))
            return web.json_response({"choices": [{"message": {"content": "newapi" if "翻译成" in b["messages"][0]["content"] else '{"suggestions":[]}'}}]})
        self.runners, ports = [], []
        for h in (meta, newapi):
            app = web.Application(); app.router.add_post("/v1/chat/completions", h)
            r = web.AppRunner(app); await r.setup(); s = web.TCPSite(r, "127.0.0.1", 0); await s.start()
            self.runners.append(r); ports.append(s._server.sockets[0].getsockname()[1])
        os.environ.update(META_BASE_URL=f"http://127.0.0.1:{ports[0]}/v1", META_API_KEY="k", LLM_BASE_URL=f"http://127.0.0.1:{ports[1]}/v1", LLM_API_KEY="k",
                          LLM_FAST_MODEL="groq-qwen-27b", LLM_TRANSLATE_MODEL="muse-spark-1.3", LLM_FALLBACK_MODEL="gpt-6-luna", LLM_TRANSLATE_FALLBACK="gpt-6-luna")
        self.http = aiohttp.ClientSession()

    async def asyncTearDown(self):
        await self.http.close()
        for r in self.runners: await r.cleanup()
        for k, v in self.saved.items():
            if v is None: os.environ.pop(k, None)
            else: os.environ[k] = v

    async def test_typing_uses_translate_model(self):
        os.environ["TRANSLATE_TIMEOUT"] = "3"
        self.assertEqual(await A.translate_typed(self.http, "好", "zh", "es"), "meta")
        self.assertEqual(self.calls, [("meta", "muse-spark-1.3")])

    async def test_typing_meta_timeout_falls_back(self):
        os.environ["TRANSLATE_TIMEOUT"] = "0.2"
        self.assertEqual(await A.translate_typed(self.http, "好", "zh", "es"), "newapi")
        self.assertEqual(self.calls[-1], ("newapi", "gpt-6-luna"))

    async def test_suggestions_stay_on_fast_model(self):
        await A.assist(self.http, [{"me": False, "orig": "Hola", "tr": "你好"}], "daily", {})
        self.assertEqual(self.calls[0], ("newapi", "groq-qwen-27b"))


if __name__ == "__main__":
    unittest.main()
