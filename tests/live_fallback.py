"""真实网关实测：正常路径 vs 强制备用路径（打字翻译 / 建议回答 / 纪要）的耗时。不打印任何密钥。
Run（需 LLM_BASE_URL LLM_API_KEY，纪要主模型走 Meta 还需 META_API_KEY）：python3 tests/live_fallback.py [次数]"""
import asyncio, os, statistics, sys, time, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1])); sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import aiohttp, assist as A
from test_assist import CONV, FACTS
N = int(sys.argv[1]) if len(sys.argv) > 1 else 3
TXT = ["这个药一天吃几次？", "我想预约下周二的号。", "医生说每八小时吃一片。", "我的孩子三年级，想问一下转学手续。", "我想在银行开一个账户。"]
CJK = lambda s: any("\u4e00" <= c <= "\u9fff" for c in s)

async def timed(fn):
    A._cool.clear(); t = time.time()
    try:
        r = await fn(); err = None
    except Exception as e:
        r, err = None, str(e)[:150]
    return r, time.time() - t, A.chat_task.last, err

def row(name, ts, lasts, errs):
    served = sorted({(l or {}).get("model") or "FAIL" for l in lasts})
    print(f"{name:34s} n={len(ts)} avg {statistics.mean(ts):.2f}s  max {max(ts):.2f}s  served={served}  errors={sorted(set(errs)) or '-'}")

async def run(http, name, mk, n=N, setenv=None):
    for k, v in (setenv or {}).items(): os.environ[k] = v
    ts, lasts, errs, outs = [], [], [], []
    for i in range(n):
        r, dt, last, err = await timed(lambda: mk(i)); ts.append(dt); lasts.append(last); outs.append(r)
        errs += [f"{m}:{e}" for m, e in (last or {}).get("errors", [])]
        if err: errs.append("RAISED " + err)
    row(name, ts, lasts, errs)
    for k in (setenv or {}): os.environ.pop(k, None)
    return outs

async def main():
    async with aiohttp.ClientSession() as http:
        print("config:", {t: A.task_models(t) for t in ("translate", "fast", "summary")}, {t: A.task_timeouts(t) for t in ("translate", "fast", "summary")})
        DOSE = "医生说每八小时吃一片。"
        tr = lambda i: A.translate_typed(http, TXT[i % len(TXT)], "zh", "es")
        dose = lambda i: A.translate_typed(http, DOSE, "zh", "es")
        B = "no-such-model-"
        lv = [("L0 主模型 qwen", {}),
              ("L1 -> groq-gpt-120b", {"LLM_TRANSLATE_MODEL": B + "a"}),
              ("L2 -> gpt-6-luna", {"LLM_TRANSLATE_MODEL": B + "a", "LLM_TRANSLATE_FALLBACK": B + "b,gpt-6-luna,local-llm"}),
              ("L3 -> local-llm", {"LLM_TRANSLATE_MODEL": B + "a", "LLM_TRANSLATE_FALLBACK": B + "b," + B + "c,local-llm"}),
              ("L3' 真超时一路走到 local", {"LLM_TRANSLATE_TIMEOUTS": "0.05,0.05,0.05,5"})]
        for nm, env in lv:
            await run(http, "translate " + nm, tr, setenv=env)
            o = await run(http, "   (剂量句)", dose, n=1, setenv=env); print("     ->", o[0])
        fl = [("L0 主模型 qwen", {}),
              ("L1 -> groq-gpt-120b", {"LLM_FAST_MODEL": B + "a"}),
              ("L2 -> gpt-6-luna", {"LLM_FAST_MODEL": B + "a", "LLM_FAST_FALLBACK": B + "b,gpt-6-luna,local-llm"}),
              ("L3 -> local-llm", {"LLM_FAST_MODEL": B + "a", "LLM_FAST_FALLBACK": B + "b," + B + "c,local-llm"}),
              ("L3' 真超时一路走到 local", {"LLM_FAST_TIMEOUTS": "0.05,0.05,0.05,8"})]
        asst = lambda i: A.assist(http, CONV[:4], "doctor", {})
        for nm, env in fl:
            o = await run(http, "suggestions " + nm, asst, setenv=env)
            print("     ->", [x["es"] for x in (o[0] or {}).get("suggestions", [])] if o[0] else None)
        summ = lambda i: A.summary(http, CONV, "doctor", FACTS)
        sl = [("L0 Meta muse-spark", {}),
              ("L1 -> gpt-6-luna", {"LLM_SUMMARY_MODEL": "muse-no-such"}),
              ("L2 -> groq-qwen-27b", {"LLM_SUMMARY_MODEL": "muse-no-such", "LLM_SUMMARY_FALLBACK": B + "b,groq-qwen-27b,groq-gpt-120b"}),
              ("L3 -> groq-gpt-120b", {"LLM_SUMMARY_MODEL": "muse-no-such", "LLM_SUMMARY_FALLBACK": B + "b," + B + "c,groq-gpt-120b"})]
        for nm, env in sl:
            o = await run(http, "summary " + nm, summ, n=max(1, N - 1), setenv=env)
            r = o[0] or {}; print("     ->", "ok" if (r.get("summary") and r.get("todos")) else "BAD", "|", r.get("summary", "")[:50].replace("\n", " "))
asyncio.run(main())
