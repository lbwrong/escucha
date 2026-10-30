"""假 LLM（OpenAI 兼容），给浏览器测试用：python3 tests/fake_llm.py 8798"""
import json, sys
from aiohttp import web
async def chat(req):
    b = await req.json(); sysmsg = b["messages"][0]["content"]; user = b["messages"][-1]["content"]
    if "纪要" in sysmsg:
        out = {"summary": "在 Ruzafa 卫生中心给孩子约了儿科，11 月 3 日 13:30，12 号诊室。需带医保卡和疫苗本。",
               "todos": [{"text": "带孩子去 Ruzafa 卫生中心看儿科", "date": "2026-11-03", "time": "13:30"}, {"text": "准备医保卡和疫苗本", "date": "", "time": ""}],
               "terms": [{"term": "tarjeta sanitaria", "zh": "医保卡"}, {"term": "cita previa", "zh": "提前预约"}]}
    elif "翻译成" in sysmsg:
        return web.json_response({"choices": [{"message": {"content": "Vale, la traeré ese día."}}]})
    else:
        facts = {}
        if "13:30" in user: facts.update(time="11月3日 13:30", place="Ruzafa 卫生中心 12 号诊室")
        if "vacunas" in user: facts["documents"] = "医保卡、疫苗本"
        out = {"scene": "doctor", "facts": facts, "terms": [{"term": "cita previa", "zh": "提前预约：西班牙看病办事都要先约"}] if "cita" in user else [],
               "suggestions": [{"zh": "好的，那天我会带上", "es": "Vale, lo traeré ese día"}, {"zh": "疫苗本找不到怎么办？", "es": "¿Y si no encuentro el libro?"}],
               "question": {"key": "time", "zh": "几点？", "es": "¿A qué hora?"} if "13:30" in user else {"key": "next_visit", "zh": "需要复诊吗？", "es": "¿Tengo que volver?"}}
        out["question"] = {"key": "cost", "zh": "看病要付费吗？", "es": "¿Tengo que pagar algo?"} if "vacunas" in user else out["question"]
    return web.json_response({"choices": [{"message": {"content": json.dumps(out, ensure_ascii=False)}}]})
app = web.Application(); app.router.add_post("/v1/chat/completions", chat)
web.run_app(app, host="127.0.0.1", port=int(sys.argv[1]), print=None)
