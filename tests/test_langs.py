"""语言对（非默认）测试：en⇄fr。Run: .venv/bin/python -m unittest -v tests/test_langs.py  （REAL_LLM=1 再加真模型测试）"""
import asyncio, json, os, sys, pathlib, unittest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import aiohttp
import server, assist as A

CONV_EN_FR = [{"me": False, "orig": "Bonjour, vous avez rendez-vous mardi à 10h30 au cabinet, rue de Rivoli.", "tr": "Hello, you have an appointment on Tuesday at 10:30 at the office on Rue de Rivoli."},
              {"me": True, "orig": "Great, what should I bring?", "tr": "Parfait, qu'est-ce que je dois apporter ?"},
              {"me": False, "orig": "Apportez votre carte Vitale et votre ordonnance.", "tr": "Bring your Carte Vitale and your prescription."}]


class PairTest(unittest.IsolatedAsyncioTestCase):
    def test_pair_validation(self):
        self.assertEqual(A.pair("en", "fr"), ("en", "fr"))
        self.assertEqual(A.pair(None, None), ("zh", "es"))
        self.assertEqual(A.pair("xx", "fr"), ("zh", "fr"))
        self.assertEqual(A.pair("fr", "fr"), ("zh", "es"))

    def test_soniox_config_pair(self):
        c = server.soniox_config("en", "fr")
        self.assertEqual(c["language_hints"], ["fr", "en"])
        self.assertEqual(c["translation"], {"type": "two_way", "language_a": "fr", "language_b": "en"})
        self.assertEqual(server.soniox_config()["language_hints"], ["es", "zh"])

    async def test_relay_maps_en_fr(self):
        r = server.SonioxRelay.__new__(server.SonioxRelay)
        server.MetaRelay.__init__(r, None, None)
        r.me, r.them = "en", "fr"
        r.orig, r.orig_lang, r.tr, r.cur_id, r.cur_lang, out = "", None, "", None, None, []
        async def send(o): out.append(o)
        r.send = send
        await r.handle_event({"tokens": [{"text": "Bonjour", "is_final": True, "language": "fr", "translation_status": "original"}, {"text": "<end>", "is_final": True}]})
        await r.handle_event({"tokens": [{"text": "Hello.", "is_final": True, "language": "en", "translation_status": "translation"}]})
        self.assertIn({"type": "final", "id": 1, "es": "Bonjour", "lang": "fr"}, out)
        self.assertEqual(out[-1], {"type": "translation", "id": 1, "zh": "Hello.", "lang": "en", "done": True})
        await r.handle_event({"tokens": [{"text": "How much?", "is_final": True, "language": "en", "translation_status": "original"}, {"text": "<end>", "is_final": True}]})
        self.assertIn({"type": "final", "id": 2, "es": "How much?", "lang": "en"}, out)

    def test_prompts_use_pair(self):
        p = A.assist_prompt(CONV_EN_FR, "doctor", {}, False, "en", "fr")[0]["content"]
        self.assertIn("说英语", p); self.assertIn("说法语", p); self.assertIn('"zh":"英语","es":"法语"', p)
        self.assertNotIn("西班牙", p)
        d = A.assist_prompt(CONV_EN_FR, "doctor", {}, False)[0]["content"]
        self.assertTrue(d.startswith("你是在西班牙帮中国人办事的对话助手"))

    def test_goodbye_multilang(self):
        for t in ("Au revoir !", "Goodbye", "Auf Wiedersehen", "До свидания", "再见"):
            self.assertTrue(A.is_goodbye(t), t)

    async def test_reminders_default_untouched(self):
        items = await A.reminders_for(None, "bank", {})
        self.assertEqual(items, A.reminders("bank", {}))


@unittest.skipUnless(os.environ.get("REAL_LLM"), "set REAL_LLM=1 to call the real NewAPI model")
class RealLLMPair(unittest.IsolatedAsyncioTestCase):
    async def test_real_en_fr(self):
        import time
        async with aiohttp.ClientSession() as http:
            t = time.time(); r = await A.assist(http, CONV_EN_FR, "doctor", {}, False, "en", "fr"); dt = time.time() - t
            print(f"\nreal assist en/fr {dt:.2f}s:", json.dumps(r, ensure_ascii=False))
            self.assertGreaterEqual(len(r["suggestions"]), 1)
            s = r["suggestions"][0]
            self.assertFalse(any("\u4e00" <= ch <= "\u9fff" for ch in s["zh"] + s["es"]), s)   # no Chinese at all
            rem = await A.reminders_for(http, "doctor", r["facts"], "en", "fr")
            print("reminders:", json.dumps(rem, ensure_ascii=False))
            self.assertTrue(rem and not any("\u4e00" <= ch <= "\u9fff" for ch in rem[0]["zh"]), rem)
            sm = await A.summary(http, CONV_EN_FR, "doctor", r["facts"], "en", "fr")
            print("summary:", sm["summary"])
            self.assertTrue(sm["summary"] and not any("\u4e00" <= ch <= "\u9fff" for ch in sm["summary"]))
            tr = await A.translate_typed(http, "Thank you, see you on Tuesday.", "en", "fr")
            print("typed:", tr); self.assertTrue(tr)


if __name__ == "__main__":
    unittest.main()
