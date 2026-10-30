"""每个模型都有备用：主模型出错 / 429 / 5xx / 超时 / 空输出 / 非 JSON -> 自动换备用；Soniox 掉线自动重连并有明确提示；Meta 说话人区分挂了字幕照常。
Run: python3 -m unittest tests/test_fallback.py"""
import asyncio, json, os, sys, pathlib, unittest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import aiohttp
from aiohttp import web
import assist as A
import server as S

KEYS = ("LLM_BASE_URL", "LLM_API_KEY", "LLM_FAST_MODEL", "LLM_TRANSLATE_MODEL", "LLM_SUMMARY_MODEL", "LLM_FALLBACK_MODEL", "LLM_TRANSLATE_FALLBACK",
        "LLM_FAST_FALLBACK", "LLM_SUMMARY_FALLBACK", "LLM_TRANSLATE_TIMEOUTS", "LLM_FAST_TIMEOUTS", "LLM_TRANSLATE_TIMEOUT", "LLM_FAST_TIMEOUT", "LLM_SUMMARY_TIMEOUT", "LLM_COOLDOWN_S",
        "META_BASE_URL", "META_API_KEY", "TRANSLATE_TIMEOUT")
GOOD_JSON = json.dumps({"scene": "doctor", "facts": {}, "suggestions": [{"zh": "好", "es": "Vale"}], "terms": [], "question": None,
                        "summary": "纪要", "todos": []}, ensure_ascii=False)


class Fallback(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.saved = {k: os.environ.get(k) for k in KEYS}
        for k in KEYS: os.environ.pop(k, None)
        self.calls, self.mode = [], {}   # mode: model -> "ok" | "429" | "500" | "slow" | "empty" | "bad"
        async def handler(req):
            b = await req.json(); m = b["model"]; self.calls.append(b); how = self.mode.get(m, "ok")
            if how == "429": return web.json_response({"error": {"message": "rate limit"}}, status=429)
            if how == "500": return web.json_response({"error": {"message": "boom"}}, status=500)
            if how == "slow": await asyncio.sleep(3)
            txt = {"empty": "", "bad": "sorry, I cannot do that"}.get(how)
            if txt is None:
                sysm = b["messages"][0]["content"]
                txt = '{"items": []}' if "保持 key 不变" in sysm else f"[{m}]" if "翻译成" in sysm else GOOD_JSON
            return web.json_response({"choices": [{"message": {"content": txt}}]})
        app = web.Application(); app.router.add_post("/v1/chat/completions", handler)
        self.runner = web.AppRunner(app); await self.runner.setup(); site = web.TCPSite(self.runner, "127.0.0.1", 0); await site.start()
        port = site._server.sockets[0].getsockname()[1]
        os.environ.update(LLM_BASE_URL=f"http://127.0.0.1:{port}/v1", LLM_API_KEY="k", LLM_FAST_MODEL="groq-qwen-27b",
                          LLM_TRANSLATE_MODEL="groq-qwen-27b", LLM_SUMMARY_MODEL="muse-spark-1.3", META_BASE_URL=f"http://127.0.0.1:{port}/v1", META_API_KEY="m")
        A._cool.clear(); A._cool429.clear()
        self.http = aiohttp.ClientSession()

    async def asyncTearDown(self):
        await self.http.close(); await self.runner.cleanup()
        for k, v in self.saved.items():
            if v is None: os.environ.pop(k, None)
            else: os.environ[k] = v

    models = lambda self: [c["model"] for c in self.calls]

    # --- translate ---
    async def test_translate_normal_uses_primary(self):
        self.assertEqual(await A.translate_typed(self.http, "好", "zh", "es"), "[groq-qwen-27b]")
        self.assertEqual(self.models(), ["groq-qwen-27b"]); self.assertFalse(A.chat_task.last["fallback"])

    async def test_translate_429_falls_back_to_groq_120b(self):
        self.mode["groq-qwen-27b"] = "429"
        self.assertEqual(await A.translate_typed(self.http, "好", "zh", "es"), "[groq-gpt-120b]")
        self.assertEqual(self.models(), ["groq-qwen-27b", "groq-gpt-120b"])
        self.assertEqual(A.chat_task.last["errors"], [("groq-qwen-27b", "429")])

    async def test_translate_luna_uses_effort_none_and_small_budget(self):
        self.mode.update({"groq-qwen-27b": "500", "groq-gpt-120b": "500"})
        self.assertEqual(await A.translate_typed(self.http, "好", "zh", "es"), "[gpt-6-luna]")
        self.assertEqual(self.models(), ["groq-qwen-27b", "groq-gpt-120b", "gpt-6-luna"])
        b = self.calls[2]; self.assertEqual(b["reasoning_effort"], "none"); self.assertLessEqual(b["max_completion_tokens"], 500)
        self.assertNotIn("temperature", b)

    async def test_groq_gpt_oss_reasoning_low_and_enough_tokens(self):
        self.mode["groq-qwen-27b"] = "500"
        await A.assist(self.http, [{"me": False, "orig": "Hola", "tr": "你好"}], "doctor", {})
        b = self.calls[1]; self.assertEqual(b["model"], "groq-gpt-120b")
        self.assertEqual(b["reasoning_effort"], "low"); self.assertGreaterEqual(b["max_tokens"], 1000); self.assertEqual(b["temperature"], 0.2)

    async def test_full_chain_to_local_last(self):
        self.mode.update({"groq-qwen-27b": "500", "groq-gpt-120b": "429", "gpt-6-luna": "500"})
        self.assertEqual(await A.translate_typed(self.http, "好", "zh", "es"), "[local-llm]")
        self.assertEqual(self.models(), ["groq-qwen-27b", "groq-gpt-120b", "gpt-6-luna", "local-llm"])

    async def test_groq_shared_quota_cooldown(self):
        """qwen 429 后 120b 正常 -> 下次直接用 120b；120b 也 429 -> 两个 groq 一起冷却，下次直接 luna。"""
        self.mode["groq-qwen-27b"] = "429"
        await A.translate_typed(self.http, "好", "zh", "es"); self.calls.clear()
        self.assertEqual(await A.translate_typed(self.http, "好", "zh", "es"), "[groq-gpt-120b]"); self.assertEqual(self.models(), ["groq-gpt-120b"])
        self.mode["groq-gpt-120b"] = "429"; self.calls.clear()
        self.assertEqual(await A.translate_typed(self.http, "好", "zh", "es"), "[gpt-6-luna]")   # 120b 也 429 -> 触发整组冷却
        self.calls.clear()
        self.assertEqual(await A.translate_typed(self.http, "好", "zh", "es"), "[gpt-6-luna]"); self.assertEqual(self.models(), ["gpt-6-luna"])
        # 全部非 groq 也挂了：冷却中的 groq 仍会作为最后手段重试，local 永远最后
        self.mode.update({"gpt-6-luna": "500", "groq-qwen-27b": "ok", "groq-gpt-120b": "ok"}); None
        self.calls.clear(); out = await A.translate_typed(self.http, "好", "zh", "es")
        self.assertEqual(self.models()[:2], ["gpt-6-luna", "groq-qwen-27b"]); self.assertNotEqual(self.models()[0], "local-llm")
        self.assertEqual(out, "[groq-qwen-27b]")

    async def test_per_step_timeouts_and_worst_case(self):
        self.assertEqual(A.task_timeouts("translate"), [2.0, 2.0, 3.0, 5.0]); self.assertEqual(sum(A.task_timeouts("translate")), 12.0)
        self.assertEqual(A.task_timeouts("fast"), [3.0, 3.0, 4.0, 8.0])
        os.environ["LLM_TRANSLATE_TIMEOUTS"] = "1,1.5"; self.assertEqual(A.task_timeouts("translate"), [1.0, 1.5])
        os.environ["LLM_TRANSLATE_TIMEOUT"] = "0.7"; self.assertEqual(A.task_timeouts("translate"), [0.7, 1.5])

    async def test_each_step_has_own_timeout(self):
        os.environ["LLM_TRANSLATE_TIMEOUTS"] = "0.3,0.3,5"
        self.mode.update({"groq-qwen-27b": "slow", "groq-gpt-120b": "slow"})
        import time; t = time.time()
        self.assertEqual(await A.translate_typed(self.http, "好", "zh", "es"), "[gpt-6-luna]")
        self.assertLess(time.time() - t, 2); self.assertEqual([e[1] for e in A.chat_task.last["errors"]], ["timeout", "timeout"])

    async def test_translate_5xx_falls_back(self):
        self.mode["groq-qwen-27b"] = "500"
        self.assertEqual(await A.translate_typed(self.http, "好", "zh", "es"), "[groq-gpt-120b]")

    async def test_translate_timeout_falls_back(self):
        os.environ["LLM_TRANSLATE_TIMEOUT"] = "0.3"; self.mode["groq-qwen-27b"] = "slow"
        import time; t = time.time()
        self.assertEqual(await A.translate_typed(self.http, "好", "zh", "es"), "[groq-gpt-120b]")
        self.assertLess(time.time() - t, 2); self.assertEqual(A.chat_task.last["errors"][0][1], "timeout")

    async def test_translate_empty_output_falls_back(self):
        self.mode["groq-qwen-27b"] = "empty"
        self.assertEqual(await A.translate_typed(self.http, "好", "zh", "es"), "[groq-gpt-120b]")

    async def test_default_timeouts(self):
        self.assertEqual(A.task_timeouts("translate")[0], 2.0); self.assertEqual(A.task_timeouts("fast")[0], 3.0); self.assertEqual(A.task_timeouts("summary")[0], 15.0)

    async def test_cooldown_skips_failed_primary(self):
        self.mode["groq-qwen-27b"] = "429"
        await A.translate_typed(self.http, "好", "zh", "es"); self.calls.clear()
        await A.translate_typed(self.http, "好", "zh", "es")
        self.assertEqual(self.models(), ["groq-gpt-120b"])   # 冷却期内直接用备用
        os.environ["LLM_COOLDOWN_S"] = "0"; A._cool.clear(); self.mode["groq-qwen-27b"] = "ok"; self.calls.clear()
        await A.translate_typed(self.http, "好", "zh", "es"); self.assertEqual(self.models(), ["groq-qwen-27b"])

    async def test_env_fallback_chain_and_all_fail(self):
        os.environ["LLM_TRANSLATE_FALLBACK"] = "model-b, model-c"
        self.mode.update({"groq-qwen-27b": "500", "model-b": "429"})
        self.assertEqual(await A.translate_typed(self.http, "好", "zh", "es"), "[model-c]")
        self.mode["model-c"] = "500"; A._cool.clear()
        with self.assertRaises(RuntimeError) as cm: await A.translate_typed(self.http, "好", "zh", "es")
        self.assertIn("全部失败", str(cm.exception))

    async def test_usted_in_prompt(self):
        await A.translate_typed(self.http, "我想预约", "zh", "es")
        sysmsg = self.calls[0]["messages"][0]["content"]
        self.assertIn("usted", sysmsg); self.assertIn("医生", sysmsg); self.assertIn("银行", sysmsg)

    # --- fast (suggestions / facts) ---
    async def test_assist_primary_error_and_bad_json_fall_back(self):
        lines = [{"me": False, "orig": "Hola", "tr": "你好"}]
        self.mode["groq-qwen-27b"] = "429"
        r = await A.assist(self.http, lines, "doctor", {}); self.assertTrue(r["suggestions"]); self.assertEqual(self.models(), ["groq-qwen-27b", "groq-gpt-120b"])
        A._cool.clear(); self.calls.clear(); self.mode.update({"groq-qwen-27b": "bad", "groq-gpt-120b": "500"})
        r = await A.assist(self.http, lines, "doctor", {}); self.assertTrue(r["suggestions"]); self.assertEqual(self.models(), ["groq-qwen-27b", "groq-gpt-120b", "gpt-6-luna"])
        self.assertEqual(self.calls[2]["reasoning_effort"], "none")

    # --- summary ---
    async def test_summary_chain_meta_luna_qwen(self):
        lines = [{"me": False, "orig": "Hola", "tr": "你好"}]
        r = await A.summary(self.http, lines, "doctor", {}); self.assertEqual(r["summary"], "纪要"); self.assertEqual(self.models(), ["muse-spark-1.3"])
        self.calls.clear(); A._cool.clear(); self.mode["muse-spark-1.3"] = "500"
        await A.summary(self.http, lines, "doctor", {}); self.assertEqual(self.models(), ["muse-spark-1.3", "gpt-6-luna"])
        self.calls.clear(); A._cool.clear(); self.mode.update({"muse-spark-1.3": "429", "gpt-6-luna": "500"})
        r = await A.summary(self.http, lines, "doctor", {}); self.assertEqual(self.models(), ["muse-spark-1.3", "gpt-6-luna", "groq-qwen-27b"])
        self.assertEqual(r["summary"], "纪要"); self.assertEqual(A.chat_task.last["model"], "groq-qwen-27b")
        self.calls.clear(); A._cool.clear(); self.mode.update({"groq-qwen-27b": "429"})
        r = await A.summary(self.http, lines, "doctor", {}); self.assertEqual(self.models(), ["muse-spark-1.3", "gpt-6-luna", "groq-qwen-27b", "groq-gpt-120b"])
        self.assertEqual(A.chat_task.last["model"], "groq-gpt-120b")

    async def test_summary_legacy_fallback_env_still_first(self):
        os.environ["LLM_FALLBACK_MODEL"] = "gpt-x"
        self.assertEqual(A.task_models("summary"), ("muse-spark-1.3", ["gpt-x", "gpt-6-luna", "groq-qwen-27b", "groq-gpt-120b"]))

    async def test_gpt_summary_not_starved_of_tokens(self):
        os.environ["LLM_SUMMARY_MODEL"] = "gpt-6-luna"; os.environ["LLM_SUMMARY_FALLBACK"] = "groq-qwen-27b"
        await A.summary(self.http, [{"me": False, "orig": "Hola"}], "doctor", {})
        self.assertGreaterEqual(self.calls[0]["max_completion_tokens"], 1500)

    async def test_reminders_other_language_falls_back(self):
        self.mode["groq-qwen-27b"] = "500"
        out = await A.reminders_for(self.http, "doctor", {}, "en", "fr"); self.assertTrue(out)
        self.assertEqual(self.models(), ["groq-qwen-27b", "groq-gpt-120b"])


class Resilience(unittest.IsolatedAsyncioTestCase):
    async def test_diarizer_down_captions_continue(self):
        out = []
        async def send(o): out.append(o)
        d = S.Diarizer(send, aiohttp.ClientSession(), "zh", "es", lambda: 0)
        old = S.META_ASR_URL; S.META_ASR_URL = "ws://127.0.0.1:1/x"
        try:
            await d.start()
        finally:
            S.META_ASR_URL = old; await d.http.close()
        self.assertEqual(out, [{"type": "speakerStatus", "ok": False}])
        d.feed(b"\0" * 100)   # 关闭后喂音频：不抛错、不排队
        self.assertTrue(d.q.empty())

    async def test_soniox_reconnects_then_clear_error(self):
        sent = []
        class R(S.SonioxRelay):
            attempts = 0
            async def send(self, o): sent.append(o)
            async def connect(self):
                self.attempts += 1; raise ConnectionError("down")
        R.RETRY_WAITS = (0, 0, 0)
        r = R(None, None, "zh", "es"); r.asr = object()
        await r.reconnect()
        self.assertEqual(r.attempts, 3)
        self.assertEqual([m.get("key") for m in sent if m["type"] == "status"], ["reconnecting"] * 3)
        self.assertEqual(sent[-1]["type"], "error"); self.assertEqual(sent[-1]["key"], "netDown")

    async def test_soniox_reconnect_success_and_reader_exception(self):
        sent = []
        class Boom:
            closed = False
            def __aiter__(self): return self
            async def __anext__(self): raise ConnectionResetError("reset")
        class R(S.SonioxRelay):
            attempts = 0
            async def send(self, o): sent.append(o)
            async def connect(self): self.attempts += 1; self.asr = object() if self.attempts >= 2 else self.asr
        R.RETRY_WAITS = (0, 0, 0)
        r = R(None, None, "zh", "es"); b = Boom(); r.asr = b
        await r.reader(b)   # 读流异常也走重连，不静默
        self.assertEqual(r.attempts, 1); self.assertEqual(sent[0]["key"], "reconnecting")

    async def test_soniox_error_event_is_visible_and_retries_reset_on_tokens(self):
        sent = []
        class R(S.SonioxRelay):
            async def send(self, o): sent.append(o)
        r = R(None, None, "zh", "es"); r.retries = 4
        await r.handle_event({"error_code": 402, "error_message": "balance"})
        self.assertEqual(sent[-1]["key"], "asrErr"); self.assertIn("402", sent[-1]["vars"]["e"])
        await r.handle_event({"tokens": [{"text": "Hola", "is_final": False}]}); self.assertEqual(r.retries, 0)


if __name__ == "__main__":
    unittest.main()
