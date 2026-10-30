"""助手逻辑测试：JSON 解析、已知信息合并、'已说清的不再问'、结束提醒、HTTP 接口（假 LLM）。
真实模型测试：REAL_LLM=1 .venv/bin/python -m unittest tests.test_assist
Run: .venv/bin/python -m unittest -v tests/test_assist.py"""
import json, os, sys, pathlib, unittest
import aiohttp
from aiohttp import web
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import assist as A

CONV = [  # 时间+地点在第 3 句说清，第 6 句只提资料
    {"me": False, "orig": "Buenos días, ¿en qué le puedo ayudar?"},
    {"me": True, "orig": "我想给孩子预约看儿科"},
    {"me": False, "orig": "Tiene cita el martes 3 de noviembre a las 13:30 en el centro de salud de Ruzafa, consulta 12."},
    {"me": True, "orig": "好的，谢谢"},
    {"me": False, "orig": "¿Tiene la tarjeta sanitaria del niño?"},
    {"me": False, "orig": "Ese día tiene que traer también el libro de vacunas."},
]
FACTS = {"time": "11月3日（周二）13:30", "place": "Ruzafa 卫生中心 12 号诊室"}


class Parse(unittest.TestCase):
    def test_plain(self):
        self.assertEqual(A.parse_json('{"a": 1}'), {"a": 1})

    def test_fenced_and_noise(self):
        self.assertEqual(A.parse_json('好的：\n```json\n{"a": {"b": "x}"}}\n```\n完'), {"a": {"b": "x}"}})

    def test_think_and_trailing(self):
        self.assertEqual(A.parse_json('<think>{"no":1}</think> result {"ok": true} extra }'), {"ok": True})

    def test_garbage(self):
        self.assertEqual(A.parse_json("no json here"), {})
        self.assertEqual(A.parse_json('{"broken": '), {})

    def test_merge_keeps_old(self):
        f = A.merge_facts(FACTS, {"time": "", "documents": "医保卡、疫苗本", "bogus": "x", "cost": "未提及"})
        self.assertEqual(f["time"], FACTS["time"]); self.assertEqual(f["documents"], "医保卡、疫苗本")
        self.assertNotIn("bogus", f); self.assertNotIn("cost", f)


class NoReask(unittest.TestCase):
    def test_question_on_answered_item_dropped(self):
        for k in ("time", "place"):
            self.assertIsNone(A.clean_question({"key": k, "zh": "?", "es": "¿?"}, "doctor", FACTS))

    def test_question_on_missing_kept(self):
        q = A.clean_question({"key": "next_visit", "zh": "什么时候复诊？", "es": "¿Cuándo vuelvo?"}, "doctor", FACTS)
        self.assertEqual(q["key"], "next_visit")

    def test_time_given_as_cita_counts(self):
        self.assertIsNone(A.clean_question({"key": "time", "es": "¿A qué hora?"}, "doctor", {"cita": "11月3日 13:30"}))

    def test_unknown_key_dropped(self):
        self.assertIsNone(A.clean_question({"key": "weather", "es": "¿?"}, "doctor", {}))

    def test_reminders_only_missing(self):
        keys = [r["key"] for r in A.reminders("doctor", {"diagnosis": "感冒", "cost": "免费"})]
        self.assertEqual(keys, ["medicine", "duration", "next_visit", "justificante"])
        self.assertTrue(all(r["es"].startswith("¿") for r in A.reminders("gov", {})))
        self.assertEqual(A.reminders("daily", {}), [])

    def test_goodbye(self):
        self.assertTrue(A.is_goodbye("Muy bien, ¡hasta luego!")); self.assertTrue(A.is_goodbye("Adiós"))
        self.assertFalse(A.is_goodbye("¿Hasta qué fecha tengo plazo?"))

    def test_prompt_has_whole_conversation(self):
        p = A.assist_prompt(CONV, "doctor", FACTS, False)[1]["content"]
        self.assertIn("13:30", p); self.assertIn("libro de vacunas", p); self.assertIn("Ruzafa", p)


class FakeLLM(unittest.IsolatedAsyncioTestCase):
    """模型故意又问时间 -> 必须被过滤掉。"""
    async def asyncSetUp(self):
        async def chat(req):
            body = await req.json(); self.body = body
            out = {"scene": "doctor", "facts": {"documents": "医保卡、疫苗本"},
                   "terms": [{"term": "tarjeta sanitaria", "zh": "医保卡"}],
                   "suggestions": [{"zh": "好的，我会带上", "es": "Vale, lo traigo"}, {"zh": "疫苗本丢了怎么办？", "es": "¿Y si lo he perdido?"}],
                   "question": {"key": "time", "zh": "几点？", "es": "¿A qué hora?"}}
            if "纪要" in body["messages"][0]["content"]:
                out = {"summary": "预约了儿科。", "todos": [{"text": "带孩子看儿科", "date": "2026-11-03", "time": "13:30"}], "terms": []}
            return web.json_response({"choices": [{"message": {"content": "```json\n" + json.dumps(out) + "\n```"}}]})
        app = web.Application(); app.router.add_post("/v1/chat/completions", chat)
        self.run_ = web.AppRunner(app); await self.run_.setup()
        site = web.TCPSite(self.run_, "127.0.0.1", 0); await site.start()
        port = site._server.sockets[0].getsockname()[1]
        os.environ.update(LLM_BASE_URL=f"http://127.0.0.1:{port}/v1", LLM_API_KEY="k", LLM_FAST_MODEL="fast-x")
        self.http = aiohttp.ClientSession()

    async def asyncTearDown(self):
        await self.http.close(); await self.run_.cleanup()
        for k in ("LLM_BASE_URL", "LLM_API_KEY", "LLM_FAST_MODEL"): os.environ.pop(k, None)

    async def test_assist_filters_reask(self):
        r = await A.assist(self.http, CONV, "daily", FACTS)
        self.assertEqual(self.body["model"], "fast-x")
        self.assertIsNone(r["question"]); self.assertEqual(r["scene"], "doctor")
        self.assertEqual(r["facts"]["time"], FACTS["time"]); self.assertIn("documents", r["facts"])
        self.assertEqual(len(r["suggestions"]), 2); self.assertEqual(r["terms"][0]["term"], "tarjeta sanitaria")

    async def test_summary(self):
        r = await A.summary(self.http, CONV, "doctor", FACTS)
        self.assertEqual(r["todos"][0]["date"], "2026-11-03")

    async def test_http_api_and_passcode(self):
        import server
        server.PASSCODE = "pw"
        app = server.make_app(); cli_run = web.AppRunner(app); await cli_run.setup()
        site = web.TCPSite(cli_run, "127.0.0.1", 0); await site.start()
        port = site._server.sockets[0].getsockname()[1]; base = f"http://127.0.0.1:{port}/api/"
        try:
            async with self.http.post(base + "reminders", json={"scene": "bank"}) as r:
                self.assertEqual(r.status, 401)
            async with self.http.post(base + "reminders", json={"scene": "bank", "facts": {"fees": "0"}}, headers={"X-Code": "pw"}) as r:
                self.assertEqual([i["key"] for i in (await r.json())["items"]], ["documents", "deadline"])
            async with self.http.post(base + "assist", json={"lines": CONV, "scene": "doctor", "facts": FACTS, "manual": True}, headers={"X-Code": "pw"}) as r:
                j = await r.json(); self.assertIsNone(j["question"])
        finally:
            server.PASSCODE = ""; await cli_run.cleanup()


@unittest.skipUnless(os.environ.get("REAL_LLM"), "set REAL_LLM=1 to call the real NewAPI model")
class RealLLM(unittest.IsolatedAsyncioTestCase):
    async def test_real_no_reask(self):
        import time
        async with aiohttp.ClientSession() as http:
            t = time.time(); r = await A.assist(http, CONV, "doctor", {}); dt = time.time() - t
        print(f"\nreal assist {dt:.2f}s:", json.dumps(r, ensure_ascii=False))
        self.assertTrue(A.known("time", r["facts"])); self.assertIn("place", r["facts"])
        q = r["question"]
        self.assertTrue(q is None or q["key"] not in ("time", "place"))
        self.assertGreaterEqual(len(r["suggestions"]), 1)
