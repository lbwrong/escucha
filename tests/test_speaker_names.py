"""说话人称呼：自我介绍 -> speaker_name（同一次建议调用里返回），纪要/提示词带名字。"""
import unittest, assist as A


class SpeakerNames(unittest.TestCase):
    def test_clean_name(self):
        self.assertEqual(A.clean_name(" García 医生 "), "García 医生")
        for bad in (None, "", "null", "None", "无", 3, "x" * 31, '""'):
            self.assertIsNone(A.clean_name(bad), bad)

    def test_transcript_uses_names(self):
        t = A.transcript_text([{"me": False, "orig": "Soy la doctora García", "who": "García 医生"},
                               {"me": True, "orig": "你好", "who": "ignored"}, {"me": False, "orig": "Hola"}])
        self.assertIn("[对方·García 医生] Soy la doctora García", t)
        self.assertIn("[我] 你好", t); self.assertIn("[对方] Hola", t)

    def test_prompts_ask_and_explain(self):
        sys_ = A.assist_prompt([{"me": False, "orig": "Soy la doctora García"}], "doctor", {}, False)[0]["content"]
        self.assertIn('"speaker_name"', sys_); self.assertIn("García 医生", sys_)
        sys_en = A.assist_prompt([], "daily", {}, False, "en", "fr")[0]["content"]
        self.assertIn("speaker_name", sys_en)


class AssistReturnsName(unittest.IsolatedAsyncioTestCase):
    async def test_assist_passes_name_no_extra_call(self):
        calls = []
        async def fake_chat(http, msgs, model, **kw):
            calls.append(model); return '{"suggestions":[{"zh":"您好","es":"Hola"}],"speaker_name":"García 医生"}'
        orig = A.chat; A.chat = fake_chat
        try:
            r = await A.assist(None, [{"me": False, "orig": "Soy la doctora García"}], "doctor", {})
        finally:
            A.chat = orig
        self.assertEqual(r["speaker_name"], "García 医生"); self.assertEqual(len(calls), 1)

    async def test_assist_no_intro(self):
        async def fake_chat(http, msgs, model, **kw): return '{"suggestions":[],"speaker_name":null}'
        orig = A.chat; A.chat = fake_chat
        try:
            r = await A.assist(None, [{"me": False, "orig": "Hola"}], "daily", {})
        finally:
            A.chat = orig
        self.assertIsNone(r["speaker_name"])


if __name__ == "__main__":
    unittest.main()
