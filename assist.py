"""Escucha 对话助手：场合判断、已知信息清单、建议回答、结束前提醒、纪要、打字翻译。
LLM = 任意 OpenAI 兼容接口（现在是 NewAPI，以后可换 Meta muse-spark-1.3），全部可用环境变量配置。"""
import json, os, re
import aiohttp

def _env(k, d=""):
    return os.environ.get(k, d).strip()

def llm_conf():
    base = (_env("LLM_BASE_URL") or _env("OPENAI_BASE_URL")).rstrip("/")
    key = _env("LLM_API_KEY") or _env("OPENAI_API_KEY")
    return base, key, _env("LLM_FAST_MODEL", "groq-qwen-27b"), _env("LLM_SUMMARY_MODEL", "gpt-6-luna")

# 支持的语言（Soniox 识别+翻译+朗读都支持）。值 = 中文名（提示词里用）
LANGS = {"zh": "中文", "es": "西班牙语", "en": "英语", "fr": "法语", "de": "德语", "it": "意大利语", "pt": "葡萄牙语",
         "ar": "阿拉伯语", "ru": "俄语", "ja": "日语", "ko": "韩语", "nl": "荷兰语", "pl": "波兰语", "tr": "土耳其语",
         "uk": "乌克兰语", "vi": "越南语", "hi": "印地语"}

def pair(me=None, them=None):
    """校验语言对；非法或相同就回到默认 中文⇄西语。"""
    me = me if me in LANGS else "zh"; them = them if them in LANGS else "es"
    return ("zh", "es") if me == them else (me, them)

def lname(c):
    return "中文" if c == "zh" else LANGS.get(c, c)

SCENES = {"daily": "日常", "doctor": "看医生", "school": "学校", "bank": "银行", "gov": "政府办事"}

# 信息项：key -> (中文名, 现成的西语问题)
ITEMS = {
    "time": ("时间", "¿A qué hora y qué día sería?"),
    "place": ("地点", "¿Dónde exactamente tengo que ir?"),
    "documents": ("要带的资料", "¿Qué documentos tengo que traer?"),
    "cost": ("费用", "¿Cuánto cuesta?"),
    "contact": ("联系人/电话", "¿Con quién puedo contactar y en qué teléfono?"),
    "diagnosis": ("诊断", "¿Qué tiene exactamente? ¿Cuál es el diagnóstico?"),
    "medicine": ("药和用量", "¿Qué medicamento tiene que tomar y cuántas veces al día?"),
    "duration": ("吃药/治疗几天", "¿Durante cuántos días?"),
    "next_visit": ("复诊时间", "¿Cuándo tenemos que volver a revisión?"),
    "justificante": ("证明（justificante）", "¿Me puede dar un justificante, por favor?"),
    "fees": ("手续费", "¿Hay alguna comisión o gasto?"),
    "deadline": ("截止日期", "¿Hasta qué fecha tengo plazo?"),
    "cita": ("预约（cita）", "¿Necesito pedir cita previa? ¿Cómo la pido?"),
}
MUST = {
    "daily": [],
    "doctor": ["diagnosis", "medicine", "duration", "next_visit", "justificante", "cost"],
    "school": ["time", "documents", "contact"],
    "bank": ["fees", "documents", "deadline"],
    "gov": ["cita", "documents", "deadline"],
}
# 追问只针对这些“基础项”或本场合必问项
BASIC = ["time", "place", "documents"]


def parse_json(text):
    """从模型输出里取出第一个 JSON 对象（容忍 ```json 包裹、前后废话、思考标签）。"""
    if not text:
        return {}
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    cand = m.group(1) if m else text
    s = cand.find("{")
    if s < 0:
        return {}
    depth, ins, esc = 0, False, False
    for i, ch in enumerate(cand[s:], s):
        if ins:
            esc = (ch == "\\" and not esc)
            if ch == '"' and not esc and cand[i - 1] != "\\":
                ins = False
            continue
        if ch == '"':
            ins = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(cand[s:i + 1])
                except ValueError:
                    return {}
    return {}


def merge_facts(old, new):
    """已知信息只增不减：新值非空才覆盖。"""
    out = dict(old or {})
    for k, v in (new or {}).items():
        if k in ITEMS and isinstance(v, str) and v.strip() and v.strip().lower() not in ("null", "none", "无", "未知", "未提及"):
            out[k] = v.strip()
    return out


def missing(scene, facts):
    return [k for k in MUST.get(scene, []) if not known(k, facts)]


def reminders(scene, facts):
    return [{"key": k, "zh": ITEMS[k][0], "es": ITEMS[k][1]} for k in missing(scene, facts)]


ALIAS = {"time": ("cita", "next_visit")}

def known(k, facts):
    facts = facts or {}
    return bool(facts.get(k)) or any(re.search(r"\d{1,2}[:：点]\d{0,2}|\d+\s*月|\d+\s*日", facts.get(a, "")) for a in ALIAS.get(k, ()))


def clean_question(q, scene, facts):
    """追问只允许问还空着的项；已说清的绝不再问。"""
    if not isinstance(q, dict) or not q.get("es"):
        return None
    k = q.get("key")
    allowed = set(BASIC) | set(MUST.get(scene, []))
    if k not in ITEMS or k not in allowed or known(k, facts):
        return None
    return {"key": k, "zh": str(q.get("zh", "")), "es": str(q["es"])}


GOODBYE = re.compile(r"\b(adi[oó]s|hasta luego|hasta pronto|hasta mañana|hasta la pr[oó]xima|nos vemos|que vaya bien|chao|chau|goodbye|bye|see you|au revoir|à bientôt|auf wiedersehen|tschüss|arrivederci|ciao|tchau|adeus|até logo|tot ziens|do widzenia|görüşürüz)\b|до свидания|пока|до побачення|さようなら|안녕히|مع السلامة|再见|拜拜", re.I)

def is_goodbye(text):
    return bool(GOODBYE.search(text or ""))


def transcript_text(lines):
    out = []
    for i, l in enumerate(lines[-40:], 1):
        who = "我" if l.get("me") else ("对方·" + str(l["who"])[:30] if l.get("who") else "对方")
        out.append(f"{i}. [{who}] {l.get('orig','')}" + (f"（译：{l.get('tr')}）" if l.get("tr") else ""))
    return "\n".join(out)


def assist_prompt(lines, scene, facts, manual, me="zh", them="es"):
    M, T = lname(me), lname(them)
    intro = "你是在西班牙帮中国人办事的对话助手" if (me, them) == ("zh", "es") else f"你是帮用户（说{M}）和对方（说{T}）面对面交流的对话助手"
    tterm = "西班牙" if them == "es" else T
    keys = ", ".join(f"{k}={v[0]}" for k, v in ITEMS.items())
    return [
        {"role": "system", "content": (
            intro + "。只输出一个 JSON 对象，不要解释。字段：\n"
            '"scene": 从 daily/doctor/school/bank/gov 里判断整场对话的场合；\n'
            f'"facts": 整场对话中【对方或我】已经明确说清的信息，键只能用：{keys}；值用简短{M}，没说过的键不要写；\n'
            f'"terms": 对方最后一句里的{tterm}办事/专业术语' + ("，如 justificante、cita previa、empadronamiento" if them == "es" else "") + f'，格式 [{{"term":"","zh":"一句{M}解释"}}]，没有就 []；\n'
            f'"suggestions": 2 条我可以回复对方最后一句的话，贴合对方说的内容，不必是是/否，格式 [{{"zh":"{M}","es":"{T}"}}]（zh 写{M}，es 写{T}）；\n'
            f'"question": 如果还有重要信息没说清，给 1 条追问 {{"key":"信息键","zh":"{M}","es":"{T}"}}，只能问 facts 里还没有的键；全都说清了就 null。\n'
            f'"speaker_name": 对方最后一句如果做了自我介绍（如 Soy la doctora García / me llamo Ana / I\'m John），写对方的称呼，用{M}的习惯写法（如 "García 医生"、"Ana"），没有自我介绍就 null。\n'
            "预约/见面的日期和时间一律写进 time（cita 只写“是否需要预约/怎么预约”）。\n"
            "注意：要看整场对话，前面已经说过的时间、地点、资料等绝不要再问。")},
        {"role": "user", "content": (
            f"当前场合：{SCENES.get(scene, '日常')}{'（用户手动选的）' if manual else ''}\n"
            f"目前已知信息：{json.dumps(facts or {}, ensure_ascii=False)}\n"
            f"整场对话：\n{transcript_text(lines)}")},
    ]


def is_meta(model):
    """muse-* 模型走 Meta Model API（https://api.meta.ai/v1，OpenAI 兼容），其余走 NewAPI。"""
    return (model or "").startswith("muse-")


def meta_conf():
    return (_env("META_BASE_URL", "https://api.meta.ai/v1").rstrip("/"),
            _env("META_API_KEY") or _env("MODEL_API_KEY"), _env("META_REASONING_EFFORT", "low"))


def fallback_for(model):
    """（旧接口，保留）出错/限流时的备用模型：Meta 模型 -> NewAPI（LLM_FALLBACK_MODEL，默认 gpt-6-luna）；NewAPI 模型 -> 纪要模型。"""
    if is_meta(model):
        fb = _env("LLM_FALLBACK_MODEL") or "gpt-6-luna"
        return None if is_meta(fb) else fb
    return _env("LLM_FALLBACK_MODEL") or llm_conf()[3]


# ---- 每个任务一条备用链：主模型出错 / 429 限流 / 5xx / 超时 / 返回空或不是合法 JSON -> 依次换下一个 ----
# 备用模型默认值（NewAPI 网关里没有 gpt-6.1-terra，所以用 gpt-6-luna）
FALLBACK_DEFAULT = {"translate": "groq-gpt-120b,gpt-6-luna,local-llm", "fast": "groq-gpt-120b,gpt-6-luna,local-llm",
                    "summary": "gpt-6-luna,groq-qwen-27b,groq-gpt-120b"}
# 每一步的超时（秒），按链上的顺序：主模型、备用1、备用2…；不够长就沿用最后一个。最坏情况总耗时 = 各项相加
TIMEOUTS_DEFAULT = {"translate": (2.0, 2.0, 3.0, 5.0), "fast": (3.0, 3.0, 4.0, 8.0), "summary": (15.0, 20.0, 10.0, 15.0)}
LAST_RESORT = ("local",)       # 本地小模型质量差（实测会译错剂量），永远排在最后
GROUPS = {"groq-": "groq"}     # 同一服务商共用一个账号额度：一个 429 另一个多半也 429
_cool = {}   # (网关, 模型或服务商) -> 冷却到的时间（刚失败的模型 N 秒内先不试，直接用备用，免得每句都白等一次超时）
_cool429 = {}   # 同上，只记 429 限流的
log = __import__("logging").getLogger("escucha")


def _group(model):
    return next((g for p, g in GROUPS.items() if (model or "").startswith(p)), None)


def _ck(model):
    return ((meta_conf()[0] if is_meta(model) else llm_conf()[0]), model)


def _csv(v):
    return [x.strip() for x in (v or "").split(",") if x.strip()]


def task_models(task):
    """返回 (主模型, [备用…])。主模型由 LLM_*_MODEL 配置，备用链由 LLM_*_FALLBACK（逗号分隔）配置。"""
    _, _, fast, summ = llm_conf()
    if task == "translate":
        primary = _env("LLM_TRANSLATE_MODEL") or fast
    elif task == "summary":
        primary = summ
    else:
        primary = fast
    fb = _env(f"LLM_{task.upper()}_FALLBACK")
    if not fb and task == "summary" and _env("LLM_FALLBACK_MODEL"):   # 旧配置：LLM_FALLBACK_MODEL 排在默认备用前面
        fb = ",".join([_env("LLM_FALLBACK_MODEL")] + _csv(FALLBACK_DEFAULT["summary"]))
    chain = []
    for m in _csv(fb or FALLBACK_DEFAULT[task]):
        if m != primary and m not in chain:
            chain.append(m)
    return primary, chain


def task_timeouts(task):
    """按链上位置（主模型、备用1、备用2…）的超时秒数列表。LLM_<TASK>_TIMEOUTS=2,2,3,5 整体覆盖；
    LLM_<TASK>_TIMEOUT（旧，只改主模型）和 TRANSLATE_TIMEOUT（更旧）仍然有效。"""
    def num(v):
        try:
            return float(v)
        except (TypeError, ValueError):
            return None
    ts = [num(x) for x in _csv(_env(f"LLM_{task.upper()}_TIMEOUTS"))]
    ts = [x for x in ts if x] or list(TIMEOUTS_DEFAULT[task])
    one = num(_env(f"LLM_{task.upper()}_TIMEOUT")) or (num(_env("TRANSLATE_TIMEOUT")) if task == "translate" else None)
    if one:
        ts[0] = one
    return ts


def _reason(e):
    s = str(e)
    m = re.search(r"HTTP (\d+)", s)
    if m:
        return m.group(1)
    if isinstance(e, (TimeoutError, __import__("asyncio").TimeoutError)):
        return "timeout"
    return type(e).__name__ + (":" + s[:60] if s else "")


async def chat_task(http, messages, task, max_tokens=700, validate=None):
    """按任务（translate / fast / summary）调用：主模型 -> 备用链。记录由谁回答（日志 + chat_task.last）。"""
    import time as _t
    primary, chain = task_models(task)
    chain_all = [primary] + chain
    tos = task_timeouts(task)
    tmo = {m: tos[min(i, len(tos) - 1)] for i, m in enumerate(chain_all)}   # 超时跟着“链上位置”走，不受冷却重排影响
    cool = float(_env("LLM_COOLDOWN_S") or 20)
    now = _t.monotonic()
    def cooled(m):
        g = _group(m)
        return _cool.get(_ck(m), 0) > now or bool(g and _cool.get(_ck("group:" + g), 0) > now)
    last = lambda m: m.startswith(LAST_RESORT)
    # 先试没在冷却的，再试冷却中的（全都冷却时仍会试）；本地小模型永远最后
    order = ([m for m in chain_all if not cooled(m) and not last(m)] + [m for m in chain_all if cooled(m) and not last(m)]
             + [m for m in chain_all if last(m)])
    errs, started = [], _t.monotonic()
    for i, m in enumerate(order):
        t0 = _t.monotonic()
        try:
            out = await chat(http, messages, m, max_tokens=max_tokens, timeout=tmo[m], effort=_effort(task, m), fallback=False)
            if not (out or "").strip():
                raise RuntimeError("LLM empty")
            if validate and not validate(out):
                raise RuntimeError("LLM bad output")
            if errs:
                log.warning("llm %s: served by %s after %s", task, m, "; ".join(f"{a}={b}" for a, b in errs))
            else:
                log.info("llm %s: served by %s in %.2fs", task, m, _t.monotonic() - t0)
            chat_task.last = {"task": task, "model": m, "fallback": m != primary, "errors": list(errs),
                              "ms": int((_t.monotonic() - started) * 1000)}
            return out
        except Exception as e:
            r = _reason(e)
            errs.append((m, r))
            if not (r.isdigit() and r.startswith("4") and r != "429") and "未配置" not in str(e):
                _cool[_ck(m)] = _t.monotonic() + cool   # 超时/429/5xx/网络错/空输出：先冷却，别每句都白等
            if r == "429":
                # 同一服务商（比如 Groq）共用一个账号额度：第二个模型也 429 -> 整个服务商一起冷却
                now2, g = _t.monotonic(), _group(m)
                _cool429[_ck(m)] = now2 + cool
                if g and any(_cool429.get(_ck(x), 0) > now2 for x in chain_all if x != m and _group(x) == g):
                    for x in chain_all:
                        if _group(x) == g:
                            _cool[_ck(x)] = now2 + cool
                    _cool[_ck("group:" + g)] = now2 + cool
            log.warning("llm %s: %s failed (%s, %.2fs)%s", task, m, r, _t.monotonic() - t0, " -> next" if i + 1 < len(order) else " -> no more fallbacks")
    chat_task.last = {"task": task, "model": None, "fallback": True, "errors": list(errs), "ms": int((_t.monotonic() - started) * 1000)}
    raise RuntimeError(f"LLM {task} 全部失败: " + "; ".join(f"{a}={b}" for a, b in errs))
chat_task.last = None


def _effort(task, model):
    """gpt-* 推理模型的 reasoning_effort：快任务一律 none（实测 ~1s，不设要 2.25s；minimal 会 400）。"""
    if not (model or "").startswith("gpt-"):
        return None
    if task == "summary":
        return _env("LLM_GPT_SUMMARY_EFFORT") or "none"
    return "none"


async def chat(http, messages, model, max_tokens=700, timeout=20, effort=None, fallback=True):
    """单个模型调用。fallback=True（旧行为）：出错/限流时换一个备用模型再试一次；chat_task 用 fallback=False 自己管备用链。"""
    if not fallback:
        return await _chat(http, messages, model, max_tokens, timeout, effort=effort)
    try:
        return await _chat(http, messages, model, max_tokens, timeout, effort=effort)
    except (RuntimeError, aiohttp.ClientError, TimeoutError, __import__('asyncio').TimeoutError) as e:
        fb = fallback_for(model)
        if not fb or fb == model or "LLM 未配置" in str(e) and not is_meta(model):
            raise
        return await _chat(http, messages, fb, max_tokens, max(timeout, 30))


async def _chat(http, messages, model, max_tokens, timeout, effort=None):
    if is_meta(model):
        base, key, meta_effort = meta_conf()
        if not key:
            raise RuntimeError("Meta LLM 未配置")
        # Muse Spark 是推理模型：不设 temperature（官方建议默认 1.0），用 reasoning_effort 控制思考量，输出额度要留思考空间
        body = {"model": model, "messages": messages, "reasoning_effort": meta_effort,
                "max_completion_tokens": max(max_tokens * 4, 2000)}
    else:
        base, key, *_ = llm_conf()
        if not base or not key:
            raise RuntimeError("LLM 未配置")
        body = {"model": model, "messages": messages}
        if not model.startswith("gpt-"):
            body["temperature"] = 0.2
        if model.startswith("gpt-"):
            if effort:   # 不思考：额度只要够输出就行
                body["reasoning_effort"] = effort
                body["max_completion_tokens"] = max_tokens + 100 if effort == "none" else max(max_tokens * 3, 2000)
            else:
                body["max_completion_tokens"] = max(max_tokens * 3, 2000)  # 推理模型要留思考额度
        elif model.startswith("groq-gpt"):
            # Groq 上的 gpt-oss 是推理模型：思考 token 也算在 max_tokens 里，不限制会把 JSON 截断（实测 700 不够）
            body["reasoning_effort"] = "low"
            body["max_tokens"] = max(max_tokens * 2, 1000)
        else:
            body["max_tokens"] = max_tokens
    async with http.post(f"{base}/chat/completions", json=body, headers={"Authorization": f"Bearer {key}"},
                         timeout=aiohttp.ClientTimeout(total=timeout)) as r:
        data = await r.json(content_type=None)
        if r.status != 200:
            raise RuntimeError(f"LLM HTTP {r.status}: {str(data)[:200]}")
        _chat.last_usage = data.get("usage")
        return data["choices"][0]["message"]["content"] or ""


async def assist(http, lines, scene, facts, manual=False, me="zh", them="es"):
    me, them = pair(me, them)
    raw = parse_json(await chat_task(http, assist_prompt(lines, scene, facts, manual, me, them), "fast", 700, validate=lambda t: bool(parse_json(t))))
    facts2 = merge_facts(facts, raw.get("facts"))
    guess = raw.get("scene") if raw.get("scene") in SCENES else None
    use_scene = scene if manual or not guess else guess
    sugg = [{"zh": str(s.get("zh", "")), "es": str(s.get("es", ""))} for s in (raw.get("suggestions") or [])
            if isinstance(s, dict) and s.get("es")][:2]
    terms = [{"term": str(t.get("term", "")), "zh": str(t.get("zh", ""))} for t in (raw.get("terms") or [])
             if isinstance(t, dict) and t.get("term")][:3]
    last = next((l for l in reversed(lines) if not l.get("me")), {})
    return {"scene": guess, "facts": facts2, "terms": terms, "suggestions": sugg,
            "question": clean_question(raw.get("question"), use_scene, facts2),
            "goodbye": is_goodbye(last.get("orig", "")), "speaker_name": clean_name(raw.get("speaker_name"))}


def clean_name(v):
    """LLM 给的自我介绍称呼：只要短字符串，空/null/无 都丢掉。"""
    if not isinstance(v, str):
        return None
    v = v.strip().strip('"\'“”').strip()
    if not v or v.lower() in ("null", "none", "无", "n/a", "unknown") or len(v) > 30:
        return None
    return v


async def summary(http, lines, scene, facts, me="zh", them="es"):
    me, them = pair(me, them); M, T = lname(me), lname(them)
    tw = "西语" if them == "es" else T
    msgs = [{"role": "system", "content": (
        f"根据对话和已知信息写{M}纪要（对话里 [对方·X] 表示对方叫 X，纪要里用这个称呼），只输出 JSON："
        f'{{"summary":"3-5 句{M}总结","todos":[{{"text":"待办（{M}）","date":"YYYY-MM-DD 或空","time":"HH:MM 或空"}}],'
        f'"terms":[{{"term":"{tw}词","zh":"{M}解释"}}]}}')},
        {"role": "user", "content": f"场合：{SCENES.get(scene,'日常')}\n今天：{_env('TODAY') or __import__('datetime').date.today()}\n"
                                    f"已知信息：{json.dumps(facts or {}, ensure_ascii=False)}\n对话：\n{transcript_text(lines)}"}]
    raw = parse_json(await chat_task(http, msgs, "summary", 1500, validate=lambda t: bool(parse_json(t))))
    return {"summary": str(raw.get("summary", "")), "todos": [t for t in raw.get("todos") or [] if isinstance(t, dict)],
            "terms": [t for t in raw.get("terms") or [] if isinstance(t, dict)]}


FORMAL_HINT = ("对话的另一方如果是医生、老师、银行或政府窗口工作人员、客服、陌生的长辈，用正式称呼（西班牙语用 usted，法语 vous，德语 Sie，意大利语 Lei，葡萄牙语 o senhor/a senhora）；"
               "对朋友、孩子、同龄人用随意语气。拿不准时偏礼貌。")


async def translate_typed(http, text, src="zh", tgt="es", lines=None):
    names = dict(LANGS, zh="简体中文")
    ctx = transcript_text(lines or [])[-1500:]
    msgs = [{"role": "system", "content": f"把用户的{names.get(src, src)}翻译成自然口语的{names.get(tgt, tgt)}，只输出译文，不要回答问题、不要解释。"
                                          + FORMAL_HINT
                                          + (f"\n对话上下文：\n{ctx}" if ctx else "")},
            {"role": "user", "content": text}]
    # 主模型 2.5 秒没回 / 限流 / 出错 -> 备用链（LLM_TRANSLATE_FALLBACK）
    return (await chat_task(http, msgs, "translate", 300)).strip()


async def reminders_for(http, scene, facts, me="zh", them="es"):
    """还没问的项。默认 中⇄西 直接用现成问题；其他语言对让模型把名称/问题翻成 我的语言/对方语言。"""
    items = reminders(scene, facts)
    me, them = pair(me, them)
    if not items or them == "es":   # 问句本来就是西语；名称由前端按“我的语言”显示
        return items
    src = [{"key": i["key"], "zh": i["zh"], "es": i["es"]} for i in items]
    msgs = [{"role": "system", "content": f"把每项的 zh（中文名称）翻译成{lname(me)}，es（西班牙语问题）翻译成{lname(them)}。保持 key 不变，只输出 JSON：{{\"items\":[...]}}"},
            {"role": "user", "content": json.dumps({"items": src}, ensure_ascii=False)}]
    try:
        out = {i.get("key"): i for i in parse_json(await chat_task(http, msgs, "fast", 600, validate=lambda t: bool(parse_json(t)))).get("items", []) if isinstance(i, dict)}
    except Exception:
        out = {}
    return [{"key": i["key"], "zh": str(out.get(i["key"], {}).get("zh") or i["zh"]), "es": str(out.get(i["key"], {}).get("es") or i["es"])} for i in items]
