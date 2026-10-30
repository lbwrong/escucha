"""Meta Muse Spark 基准：python tests/bench_meta.py [次数] [reasoning_effort]  （需 META_API_KEY；只打印耗时/tokens/有效性，不打印 key）"""
import asyncio, json, os, sys, time, statistics, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
N = int(sys.argv[1]) if len(sys.argv) > 1 else 1
os.environ.update(LLM_FAST_MODEL="muse-spark-1.3", LLM_SUMMARY_MODEL="muse-spark-1.3", LLM_FALLBACK_MODEL="muse-none")  # 不回落，只测 Meta
if len(sys.argv) > 2: os.environ["META_REASONING_EFFORT"] = sys.argv[2]
import aiohttp, assist as A
from tests.test_assist import CONV, FACTS
from tests.test_langs import CONV_EN_FR
CJK = lambda s: any("\u4e00" <= c <= "\u9fff" for c in s)
async def one(http, name):
    t = time.time()
    if name == "assist zh/es": r = await A.assist(http, CONV, "doctor", {}); ok = bool(r["suggestions"]) and "time" in r["facts"] and (r["question"] is None or r["question"]["key"] not in ("time", "place")); s = r["suggestions"][:1]
    elif name == "assist en/fr": r = await A.assist(http, CONV_EN_FR, "doctor", {}, False, "en", "fr"); ok = bool(r["suggestions"]) and not CJK(json.dumps(r["suggestions"], ensure_ascii=False)); s = r["suggestions"][:1]
    elif name == "typed zh->es": r = await A.translate_typed(http, "好的，那天我会带上疫苗本", "zh", "es", CONV); ok = bool(r) and not CJK(r); s = r
    elif name == "missing en/fr": r = await A.reminders_for(http, "doctor", {}, "en", "fr"); ok = len(r) == 6 and not CJK(r[0]["zh"]); s = r[:1]
    elif name == "summary zh/es": r = await A.summary(http, CONV, "doctor", FACTS); ok = bool(r["summary"]) and bool(r["todos"]); s = r["summary"][:80]
    return time.time() - t, ok, A._chat.last_usage or {}, s
async def main():
    res = {}
    async with aiohttp.ClientSession() as http:
        for name in ["assist zh/es", "assist en/fr", "typed zh->es", "missing en/fr", "summary zh/es"]:
            for i in range(N):
                try: dt, ok, u, s = await one(http, name)
                except Exception as e: dt, ok, u, s = None, False, {}, str(e)[:150]
                res.setdefault(name, []).append((dt, ok, u.get("prompt_tokens", 0), u.get("completion_tokens", 0)))
                if i == 0: print(name, "sample:", json.dumps(s, ensure_ascii=False)[:200])
    cost = 0
    for name, rs in res.items():
        ts = sorted(r[0] for r in rs if r[0] is not None); ok = sum(r[1] for r in rs)
        pin = sum(r[2] for r in rs); pout = sum(r[3] for r in rs); cost += pin * 1.25e-6 + pout * 4.25e-6
        p50 = statistics.median(ts) if ts else None; p90 = ts[min(len(ts) - 1, int(round(0.9 * (len(ts) - 1))))] if ts else None
        print(f"{name:15s} n={len(rs)} ok={ok} P50={p50 and round(p50,2)}s P90={p90 and round(p90,2)}s tokens in/out={pin}/{pout}")
    print(f"est cost ${cost:.4f}")
asyncio.run(main())
