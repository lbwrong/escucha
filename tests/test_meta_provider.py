"""muse-* 模型走 Meta（META_BASE_URL + META_API_KEY），出错回落 NewAPI。Run: .venv/bin/python -m unittest tests/test_meta_provider.py"""
import json, os, sys, pathlib, unittest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import aiohttp
from aiohttp import web
import assist as A

KEYS = ("LLM_BASE_URL", "LLM_API_KEY", "LLM_FAST_MODEL", "LLM_SUMMARY_MODEL", "LLM_FALLBACK_MODEL", "LLM_TRANSLATE_FALLBACK", "META_BASE_URL", "META_API_KEY", "META_REASONING_EFFORT")

class MetaProvider(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.saved = {k: os.environ.get(k) for k in KEYS}
        self.meta_calls, self.newapi_calls, self.meta_fail = [], [], False
        async def meta(req):
            self.meta_calls.append((req.headers.get("Authorization"), await req.json()))
            if self.meta_fail: return web.json_response({"error": {"message": "boom"}}, status=500)
            return web.json_response({"choices": [{"message": {"content": "Vale, gracias."}}], "usage": {"prompt_tokens": 1, "completion_tokens": 1}})
        async def newapi(req):
            self.newapi_calls.append((req.headers.get("Authorization"), await req.json()))
            return web.json_response({"choices": [{"message": {"content": "Vale (newapi)."}}]})
        self.runners = []
        ports = []
        for h in (meta, newapi):
            app = web.Application(); app.router.add_post("/v1/chat/completions", h)
            r = web.AppRunner(app); await r.setup(); s = web.TCPSite(r, "127.0.0.1", 0); await s.start()
            self.runners.append(r); ports.append(s._server.sockets[0].getsockname()[1])
        os.environ.update(META_BASE_URL=f"http://127.0.0.1:{ports[0]}/v1", META_API_KEY="meta-test", LLM_BASE_URL=f"http://127.0.0.1:{ports[1]}/v1",
                          LLM_API_KEY="newapi-test", LLM_FAST_MODEL="muse-spark-1.3", LLM_SUMMARY_MODEL="gpt-6-luna", META_REASONING_EFFORT="minimal")
        os.environ.pop("LLM_FALLBACK_MODEL", None); os.environ["LLM_TRANSLATE_FALLBACK"] = "gpt-6-luna"
        self.http = aiohttp.ClientSession()

    async def asyncTearDown(self):
        await self.http.close()
        for r in self.runners: await r.cleanup()
        for k, v in self.saved.items():
            if v is None: os.environ.pop(k, None)
            else: os.environ[k] = v

    async def test_routes_to_meta(self):
        out = await A.translate_typed(self.http, "好的", "zh", "es")
        self.assertEqual(out, "Vale, gracias.")
        auth, body = self.meta_calls[0]
        self.assertEqual(auth, "Bearer meta-test"); self.assertEqual(body["model"], "muse-spark-1.3")
        self.assertEqual(body["reasoning_effort"], "minimal"); self.assertNotIn("temperature", body)
        self.assertIn("max_completion_tokens", body); self.assertEqual(self.newapi_calls, [])

    async def test_meta_error_falls_back_to_newapi(self):
        self.meta_fail = True
        out = await A.translate_typed(self.http, "好的", "zh", "es")
        self.assertEqual(out, "Vale (newapi).")
        self.assertEqual(self.newapi_calls[0][0], "Bearer newapi-test"); self.assertEqual(self.newapi_calls[0][1]["model"], "gpt-6-luna")

    async def test_newapi_models_unchanged(self):
        os.environ["LLM_FAST_MODEL"] = "groq-qwen-27b"
        await A.translate_typed(self.http, "好的", "zh", "es")
        self.assertEqual(self.meta_calls, []); self.assertEqual(self.newapi_calls[0][1]["temperature"], 0.2)

    def test_fallback_rules(self):
        self.assertEqual(A.fallback_for("muse-spark-1.3"), "gpt-6-luna")
        os.environ["LLM_FALLBACK_MODEL"] = "muse-spark-1.2"; self.assertIsNone(A.fallback_for("muse-spark-1.3"))


if __name__ == "__main__":
    unittest.main()
