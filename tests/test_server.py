"""Tests with a fake Meta ASR + fake chat server (no network, no key needed).
Run: .venv/bin/python -m unittest -v tests/test_server.py"""
import asyncio, json, sys, pathlib, unittest
import aiohttp
from aiohttp import web
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import server


class Fake:
    def __init__(self):
        self.handshake, self.audio_bytes, self.ended = None, 0, False

    async def asr(self, request):
        ws = web.WebSocketResponse(); await ws.prepare(request)
        self.handshake = json.loads((await ws.receive()).data)
        await ws.send_json({"sessionId": "fake"})
        async for m in ws:
            if m.type == aiohttp.WSMsgType.BINARY:
                self.audio_bytes += len(m.data)
                if self.audio_bytes >= 3840 and self.audio_bytes - len(m.data) < 3840:
                    await ws.send_json({"type": "transcript", "transcript": "Hola", "final": False})
                    await ws.send_json({"type": "transcript", "transcript": "Hola, buenos días", "final": True})
            elif json.loads(m.data).get("type") == "endStream":
                self.ended = True; await ws.close(); break
        return ws

    async def chat(self, request):
        body = await request.json()
        assert request.headers["Authorization"] == "Bearer test-key"
        assert body["model"] == "muse-spark-1.3"
        return web.json_response({"choices": [{"message": {"content": "你好，早上好"}}]})


class MetaPathTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.fake = Fake()
        fapp = web.Application()
        fapp.router.add_get("/asr", self.fake.asr); fapp.router.add_post("/chat", self.fake.chat)
        self.frun = web.AppRunner(fapp); await self.frun.setup()
        await web.TCPSite(self.frun, "127.0.0.1", 18901).start()
        server.API_KEY = "test-key"; server.PROVIDER = "meta"
        server.ASR_URL = "ws://127.0.0.1:18901/asr"
        server.CHAT_URL = "http://127.0.0.1:18901/chat"
        self.run_ = web.AppRunner(server.make_app()); await self.run_.setup()
        await web.TCPSite(self.run_, "127.0.0.1", 18902).start()

    async def asyncTearDown(self):
        await self.run_.cleanup(); await self.frun.cleanup()

    async def test_live_relay(self):
        got = []
        async with aiohttp.ClientSession() as s, s.ws_connect("http://127.0.0.1:18902/ws") as ws:
            await ws.send_json({"type": "start"})
            for _ in range(3):
                await ws.send_bytes(b"\0" * 3840); await asyncio.sleep(0.05)
            while not any(m["type"] == "translation" for m in got):
                got.append(json.loads((await ws.receive(timeout=5)).data))
        types = [m["type"] for m in got]
        self.assertIn("partial", types); self.assertIn("final", types)
        self.assertEqual(got[-1]["zh"], "你好，早上好")
        h = self.fake.handshake
        self.assertEqual(h["authorization"]["accessToken"], "Bearer test-key")
        self.assertEqual(h["audioEncoding"], "PCM_24KHZ")
        self.assertEqual(h["languageBias"], ["Spanish", "Mandarin Chinese"])
        await asyncio.sleep(1.5)
        self.assertTrue(self.fake.ended)
        self.assertGreaterEqual(self.fake.audio_bytes, 3840 * 3)


class DemoTest(unittest.IsolatedAsyncioTestCase):
    async def test_demo_stream(self):
        server.API_KEY = ""; server.PROVIDER = "demo"
        run = web.AppRunner(server.make_app()); await run.setup()
        await web.TCPSite(run, "127.0.0.1", 18903).start()
        try:
            async with aiohttp.ClientSession() as s, s.ws_connect("http://127.0.0.1:18903/ws") as ws:
                await ws.send_json({"type": "start", "demo": True})
                await ws.send_bytes(b"\0" * 48000)
                seen = []
                while "translation" not in seen:
                    m = json.loads((await ws.receive(timeout=10)).data); seen.append(m["type"])
                self.assertIn("partial", seen); self.assertIn("final", seen)
        finally:
            await run.cleanup()

if __name__ == "__main__":
    unittest.main()


class LocalModeTest(unittest.TestCase):
    def test_segmenter_cuts_on_silence(self):
        import numpy as np
        sr = 24000
        tone = (np.sin(np.arange(sr) * 2 * np.pi * 220 / sr) * 8000).astype("<i2").tobytes()
        quiet = bytes(sr * 2)
        seg = server.Segmenter(rms=400, silence=0.6, max_s=8)
        out = []
        for chunk in [quiet[:9600], tone, quiet, tone[:24000], quiet]:
            for i in range(0, len(chunk), 4800):
                out += seg.feed(chunk[i:i + 4800])
        self.assertEqual(len(out), 2)
        self.assertGreater(len(out[0]) / 48000, 1.0)

    def test_segmenter_max_length(self):
        import numpy as np
        tone = (np.sin(np.arange(24000 * 5) * 0.06) * 8000).astype("<i2").tobytes()
        seg = server.Segmenter(rms=400, silence=0.6, max_s=2)
        self.assertEqual(len(seg.feed(tone)), 2)


class SonioxMappingTest(unittest.IsolatedAsyncioTestCase):
    async def test_tokens_to_captions(self):
        r = server.SonioxRelay.__new__(server.SonioxRelay)
        server.MetaRelay.__init__(r, None, None)
        r.orig, r.orig_lang, r.tr, r.cur_id, r.cur_lang, out = "", None, "", None, None, []
        async def send(o): out.append(o)
        r.send = send
        tok = lambda t, f, tr=False: {"text": t, "is_final": f, "translation_status": "translation" if tr else "original"}
        await r.handle_event({"tokens": [tok("Bue", False)]})
        await r.handle_event({"tokens": [tok("Buenas", True), tok(" tardes", True), tok("下午", False, True)]})
        await r.handle_event({"tokens": [tok("<end>", True), tok("下午好", True, True)]})
        await r.handle_event({"tokens": [tok("。", True, True)]})
        await r.handle_event({"tokens": [tok("Hola", False)]})
        await r.handle_event({"error_code": 401, "error_message": "bad key"})
        self.assertEqual(out[0], {"type": "partial", "es": "Bue"})
        self.assertIn("→  下午", out[1]["es"])
        self.assertIn({"type": "final", "id": 1, "es": "Buenas tardes", "lang": "es"}, out)
        trs = [o for o in out if o["type"] == "translation"]
        self.assertEqual(trs[-1], {"type": "translation", "id": 1, "zh": "下午好。", "lang": "zh", "done": True})
        self.assertEqual([o for o in out if o["type"] == "partial"][-1]["es"], "Hola")
        self.assertEqual(out[-1]["type"], "error")

    async def test_chinese_speech_to_spanish(self):
        r = server.SonioxRelay.__new__(server.SonioxRelay)
        server.MetaRelay.__init__(r, None, None)
        r.orig, r.orig_lang, r.tr, r.cur_id, r.cur_lang, out = "", None, "", None, None, []
        async def send(o): out.append(o)
        r.send = send
        await r.handle_event({"tokens": [{"text": "多少钱", "is_final": True, "language": "zh", "translation_status": "original"},
                                         {"text": "<end>", "is_final": True}]})
        await r.handle_event({"tokens": [{"text": "¿Cuánto cuesta?", "is_final": True, "language": "es", "translation_status": "translation"}]})
        self.assertIn({"type": "final", "id": 1, "es": "多少钱", "lang": "zh"}, out)
        self.assertEqual(out[-1], {"type": "translation", "id": 1, "zh": "¿Cuánto cuesta?", "lang": "es", "done": True})

    def test_config(self):
        c = server.soniox_config()
        self.assertEqual(c["translation"], {"type": "two_way", "language_a": "es", "language_b": "zh"})
        self.assertEqual((c["sample_rate"], c["audio_format"]), (24000, "pcm_s16le"))


class SonioxTtsTest(unittest.TestCase):
    def test_start_messages(self):
        cfg, txt = server.tts_start_msg("Hola", "Lucia", "s1")
        self.assertEqual((cfg["model"], cfg["language"], cfg["voice"], cfg["audio_format"], cfg["sample_rate"]),
                         ("tts-rt-v2", "es", "Lucia", "pcm_s16le", 24000))
        self.assertEqual(txt, {"stream_id": "s1", "text": "Hola", "text_end": True})

    def test_voice_list(self):
        names = [v for v, _ in server.TTS_VOICES]
        self.assertEqual(set(names), {"Lucia", "Carmen", "Mateo", "Rafael", "Javier", "Santiago"})


class PasscodeTest(unittest.IsolatedAsyncioTestCase):
    async def test_ws_rejects_wrong_code(self):
        from aiohttp.test_utils import TestServer, TestClient
        old = server.PASSCODE
        server.PASSCODE = "1234"
        try:
            async with TestClient(TestServer(server.make_app())) as c:
                ws = await c.ws_connect("/ws?code=0000"); await ws.receive()
                self.assertEqual(ws.close_code, 4401)
                ws = await c.ws_connect("/ws?code=1234")
                await ws.send_str('{"type":"ping"}')
                self.assertEqual((await ws.receive_json())["type"], "mic")
                await ws.close()
                self.assertTrue((await (await c.get("/config")).json())["needCode"])
        finally:
            server.PASSCODE = old
