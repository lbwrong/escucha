"""Escucha — live two-way conversation captions (any language pair; default zh<->es) — backend.

Browser  --(PCM16 24kHz mono, WebSocket /ws)-->  this server  --> Meta realtime ASR
Final Spanish utterances --> Muse Spark translation --> Chinese caption --> browser.
Without MODEL_API_KEY the server runs in DEMO mode (sample dialogue, labelled 示例数据).
"""
import asyncio, json, os, pathlib, time, uuid, logging
import aiohttp
from aiohttp import web

ROOT = pathlib.Path(__file__).parent
log = logging.getLogger("escucha")

def load_env(path=ROOT / ".env"):
    if path.exists():
        for line in path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

load_env()
API_KEY = os.environ.get("MODEL_API_KEY", "").strip()
ASR_URL = os.environ.get("ASR_URL", "wss://api.meta.ai/v1/asr/realtime")
CHAT_URL = os.environ.get("CHAT_URL", "https://api.meta.ai/v1/chat/completions")
ASR_MODEL = os.environ.get("ASR_MODEL", "muse-voice-transcribe-1.0")
CHAT_MODEL = os.environ.get("CHAT_MODEL", "muse-spark-1.3")
ASR_MODE = os.environ.get("ASR_MODE", "ENDPOINTING")
PORT = int(os.environ.get("PORT", "8765"))
# Local mode: mlx-whisper on this Mac for Spanish ASR + OpenAI-compatible gateway (NewAPI) for translation
OPENAI_KEY = os.environ.get("OPENAI_API_KEY", "").strip()
OPENAI_BASE = os.environ.get("OPENAI_BASE_URL", "").strip().rstrip("/")
LOCAL_CHAT_MODEL = os.environ.get("LOCAL_CHAT_MODEL", "groq-qwen-27b")
WHISPER_MODEL = os.environ.get("WHISPER_MODEL", "mlx-community/whisper-small-mlx")
PASSCODE = os.environ.get("ESCUCHA_PASSCODE", "").strip()  # empty = no access code required


def passcode_ok(given: str) -> bool:
    import hmac
    return not PASSCODE or hmac.compare_digest((given or "").strip().encode(), PASSCODE.encode())


SONIOX_KEY = os.environ.get("SONIOX_API_KEY", "").strip()
SONIOX_URL = os.environ.get("SONIOX_URL", "wss://stt-rt.soniox.com/transcribe-websocket")
SONIOX_MODEL = os.environ.get("SONIOX_MODEL", "stt-rt-v5")
PROVIDER = os.environ.get("PROVIDER", "").strip().lower() or (
    "meta" if API_KEY else "soniox" if SONIOX_KEY else ("local" if OPENAI_KEY and OPENAI_BASE else "demo"))
VAD_RMS = float(os.environ.get("VAD_RMS", "400"))       # int16 RMS above = speech
VAD_SILENCE = float(os.environ.get("VAD_SILENCE", "0.45"))  # seconds of silence ending a segment
STALE_S = float(os.environ.get("STALE_S", "6"))          # drop segments waiting longer than this
KEEPWARM_S = float(os.environ.get("KEEPWARM_S", "20"))   # tiny inference to keep weights in RAM
VAD_MAX = float(os.environ.get("VAD_MAX", "4"))            # max segment seconds

SYSTEM_PROMPT = (
    "你是现场口译员。把用户给出的西班牙语口语翻译成自然、简洁的简体中文，"
    "只输出译文，不要解释。若原文已是中文，原样输出。")


LOCAL_PROMPT = "西语译成简体中文，只输出译文。"


def handshake_frame(key: str) -> dict:
    return {
        "authorization": {"accessToken": f"Bearer {key}"},
        "audioEncoding": "PCM_24KHZ",
        "model": ASR_MODEL,
        "mode": ASR_MODE,
        "languageBias": ["Spanish", "Mandarin Chinese"],
    }


async def translate(session: aiohttp.ClientSession, text: str, history: list,
                    url: str = None, key: str = None, model: str = None) -> str:
    url, key, model = url or CHAT_URL, key or API_KEY, model or CHAT_MODEL
    local = bool(OPENAI_KEY) and key == OPENAI_KEY
    msgs = [{"role": "system", "content": LOCAL_PROMPT if local else SYSTEM_PROMPT}]
    for es, zh in history[-2:] if local else history[-4:]:  # short context helps pronouns/names
        msgs += [{"role": "user", "content": es}, {"role": "assistant", "content": zh}]
    msgs.append({"role": "user", "content": text})
    async with session.post(url, json={"model": model, "messages": msgs, **(({"max_completion_tokens": 200} if model.startswith("gpt-") else {"max_tokens": 100})
                                      if local else {"temperature": 0.2})},
                            headers={"Authorization": f"Bearer {key}"},
                            timeout=aiohttp.ClientTimeout(total=30)) as r:
        data = await r.json()
        if r.status != 200:
            raise RuntimeError(f"translate HTTP {r.status}: {str(data)[:200]}")
        return data["choices"][0]["message"]["content"].strip()


class MetaRelay:
    """One browser connection -> one (auto-reconnecting) Meta ASR session."""

    def __init__(self, browser: web.WebSocketResponse, http: aiohttp.ClientSession):
        self.browser, self.http = browser, http
        self.asr = None
        self.history = []
        self.seq = 0
        self.closed = False

    async def send(self, obj):
        if not self.browser.closed:
            await self.browser.send_json(obj)

    async def connect(self):
        url = f"{ASR_URL}?sessionId=escucha-{uuid.uuid4()}"
        self.asr = await self.http.ws_connect(url, timeout=aiohttp.ClientWSTimeout(ws_close=10), heartbeat=20)
        await self.asr.send_str(json.dumps(handshake_frame(API_KEY)))
        ack = await self.asr.receive(timeout=15)
        if ack.type != aiohttp.WSMsgType.TEXT or "sessionId" not in json.loads(ack.data):
            raise RuntimeError(f"ASR handshake failed: {str(ack.data)[:200]}")
        asyncio.create_task(self.reader(self.asr))
        await self.send({"type": "status", "text": "已连接 Meta 实时转写"})

    async def reader(self, asr):
        async for msg in asr:
            if msg.type != aiohttp.WSMsgType.TEXT:
                continue
            ev = json.loads(msg.data)
            await self.handle_event(ev)
        if not self.closed:  # session ended (e.g. max duration) -> reconnect, mic keeps flowing
            await self.send({"type": "status", "text": "转写会话重连中…"})
            try:
                await self.connect()
            except Exception as e:
                await self.send({"type": "error", "text": str(e)})

    async def handle_event(self, ev):
        t = ev.get("type")
        if t == "error":
            await self.send({"type": "error", "text": ev.get("message", "ASR error")})
        elif t == "transcript":
            text = (ev.get("transcript") or "").strip()
            if not text:
                return
            speaker = ev.get("speaker") or ev.get("speakerId")
            if not ev.get("final"):
                await self.send({"type": "partial", "es": text, "speaker": speaker})
                return
            self.seq += 1
            sid = self.seq
            await self.send({"type": "final", "id": sid, "es": text, "speaker": speaker})
            asyncio.create_task(self.do_translate(sid, text))

    async def do_translate(self, sid, text):
        try:
            zh = await translate(self.http, text, self.history)
            self.history.append((text, zh))
            await self.send({"type": "translation", "id": sid, "zh": zh})
        except Exception as e:
            await self.send({"type": "translation", "id": sid, "zh": "（翻译失败）", "error": str(e)})

    async def audio(self, data: bytes):
        if self.asr is not None and not self.asr.closed:
            await self.asr.send_bytes(data)

    async def close(self):
        self.closed = True
        if self.asr is not None and not self.asr.closed:
            try:
                await self.asr.send_str(json.dumps({"type": "endStream"}))
                await asyncio.sleep(1)
            finally:
                await self.asr.close()


class Segmenter:
    """Energy VAD over PCM16 24 kHz mono: returns finished speech segments (bytes)."""
    FRAME = 960  # 20 ms @ 24 kHz, 2 bytes/sample -> 480 samples

    def __init__(self, rms=None, silence=None, max_s=None):
        self.rms = VAD_RMS if rms is None else rms
        self.sil_frames = int((VAD_SILENCE if silence is None else silence) / 0.02)
        self.max_frames = int((VAD_MAX if max_s is None else max_s) / 0.02)
        self.buf, self.pending, self.seg, self.quiet, self.speech = b"", [], [], 0, 0

    def feed(self, data: bytes) -> list:
        import numpy as np
        self.buf += data
        out = []
        while len(self.buf) >= self.FRAME:
            fr, self.buf = self.buf[:self.FRAME], self.buf[self.FRAME:]
            a = np.frombuffer(fr, dtype="<i2").astype(np.float32)
            loud = float(np.sqrt((a * a).mean())) > self.rms
            if not self.seg:
                self.pending = (self.pending + [fr])[-10:]  # 200 ms pre-roll
                if loud:
                    self.seg, self.pending, self.quiet, self.speech = self.pending, [], 0, 1
                continue
            self.seg.append(fr)
            self.speech += loud
            self.quiet = 0 if loud else self.quiet + 1
            if self.quiet >= self.sil_frames or len(self.seg) >= self.max_frames:
                if self.speech >= 10:  # >=200 ms of speech, else noise
                    out.append(b"".join(self.seg))
                self.seg, self.quiet, self.speech = [], 0, 0
        return out

    def flush(self) -> list:
        seg, self.seg = self.seg, []
        return [b"".join(seg)] if seg and self.speech >= 10 else []


_whisper_lock = None

def whisper_transcribe(pcm24: bytes) -> str:
    import numpy as np, mlx_whisper
    a = np.frombuffer(pcm24, dtype="<i2").astype(np.float32) / 32768.0
    n = int(len(a) * 16000 / 24000)
    a16 = np.interp(np.linspace(0, len(a) - 1, n), np.arange(len(a)), a).astype(np.float32)
    r = mlx_whisper.transcribe(a16, path_or_hf_repo=WHISPER_MODEL, language="es",
                               condition_on_previous_text=False, temperature=0.0)
    return (r.get("text") or "").strip()


def warmup_whisper():
    import numpy as np
    t = time.time()
    whisper_transcribe((np.random.randn(24000) * 300).astype("<i2").tobytes())
    log.info("whisper warm (%s) in %.1fs", WHISPER_MODEL, time.time() - t)


SONIOX_TTS_URL = os.environ.get("SONIOX_TTS_URL", "wss://tts-rt.soniox.com/tts-websocket")
SONIOX_TTS_MODEL = os.environ.get("SONIOX_TTS_MODEL", "tts-rt-v2")
# Spanish-sounding built-in voices (all Soniox voices speak every language); label = 男/女
TTS_VOICES = [("Lucia", "女"), ("Carmen", "女"), ("Mateo", "男"), ("Rafael", "男"), ("Javier", "男"), ("Santiago", "男")]
TTS_RATE = 24000


def tts_start_msg(text: str, voice: str, stream_id: str, lang: str = "es") -> list:
    """Messages to send on the TTS websocket for one utterance (config, then the whole text)."""
    return [
        {"stream_id": stream_id, "model": SONIOX_TTS_MODEL, "language": lang, "voice": voice,
         "audio_format": "pcm_s16le", "sample_rate": TTS_RATE},
        {"stream_id": stream_id, "text": text, "text_end": True},
    ]


async def soniox_tts(http: aiohttp.ClientSession, text: str, voice: str, lang: str = "es"):
    """Async generator of raw PCM16 24 kHz chunks from Soniox realtime TTS."""
    import base64
    if voice not in dict(TTS_VOICES):
        voice = TTS_VOICES[0][0]
    sid = f"tts-{uuid.uuid4().hex[:8]}"
    async with http.ws_connect(SONIOX_TTS_URL, headers={"Authorization": f"Bearer {SONIOX_KEY}"}) as ws:
        for m in tts_start_msg(text, voice, sid, lang):
            await ws.send_str(json.dumps(m))
        async for msg in ws:
            if msg.type != aiohttp.WSMsgType.TEXT:
                break
            res = json.loads(msg.data)
            if res.get("error_code") is not None:
                raise RuntimeError(f"Soniox TTS {res.get('error_code')}: {res.get('error_message')}")
            if res.get("audio"):
                yield base64.b64decode(res["audio"])
            if res.get("terminated"):
                break


async def stream_tts_to_browser(ws, http, text, voice, rid, lang="es"):
    """Send {type:'tts', id, seq, audio(base64 pcm16 24k), end} messages to the browser."""
    import base64
    t0, n = time.time(), 0
    for attempt in (1, 2):   # 一个音频包都还没发出就失败：自动再试一次
        try:
            async for chunk in soniox_tts(http, text, voice, lang):
                if n == 0:
                    log.info("tts first audio %.0f ms (%s)", (time.time() - t0) * 1000, voice)
                n += 1
                if not ws.closed:
                    await ws.send_json({"type": "tts", "id": rid, "seq": n, "rate": TTS_RATE,
                                        "audio": base64.b64encode(chunk).decode()})
            break
        except Exception as e:
            log.warning("tts attempt %d failed: %s", attempt, str(e)[:160])
            if n == 0 and attempt == 1 and not ws.closed:
                await asyncio.sleep(0.3)
                continue
            if not ws.closed:
                await ws.send_json({"type": "error", "text": f"朗读失败：{e}", "key": "ttsFail", "vars": {"e": str(e)[:200]}})
            break
    if not ws.closed:
        await ws.send_json({"type": "tts", "id": rid, "end": True})


def soniox_config(me: str = "zh", them: str = "es") -> dict:
    return {
        "model": SONIOX_MODEL,
        "audio_format": "pcm_s16le", "sample_rate": 24000, "num_channels": 1,
        "language_hints": [them, me],
        "enable_language_identification": True,
        "enable_endpoint_detection": True,
        # two-way: other person's language <-> my language
        "translation": {"type": "two_way", "language_a": them, "language_b": me},
    }


END_PUNCT = tuple(".?!。？！…")


class SonioxRelay(MetaRelay):
    """Soniox realtime STT + two-way es<->zh translation over one websocket. No local model.

    Browser protocol: final {id, es: <original text>, lang: es|zh};
    translation {id, zh: <translated text>, lang: <target lang>, done: bool}.
    (field names kept from the original one-way protocol: 'es' = original, 'zh' = translation)"""

    me, them = "zh", "es"   # language pair (set from the browser's start message)
    clock = None             # ms of mic audio received (for speaker-tag time alignment)
    base_ms = 0              # audio time when the current Soniox session started
    t0 = t1 = None           # utterance start/end ms (Soniox token times)

    def __init__(self, browser, http, me="zh", them="es"):
        super().__init__(browser, http)
        self.me, self.them = A.pair(me, them)
        self.orig, self.orig_lang = "", None   # finalized original text of the current utterance
        self.tr = ""                           # finalized translation text pending for cur_id
        self.cur_id, self.cur_lang = None, None

    async def connect(self):
        self.asr = await self.http.ws_connect(SONIOX_URL, headers={"Authorization": f"Bearer {SONIOX_KEY}"}, heartbeat=20)
        await self.asr.send_str(json.dumps(soniox_config(self.me, self.them)))
        self.base_ms = self.clock() if self.clock else 0
        asyncio.create_task(self.reader(self.asr))
        await self.send({"type": "status", "text": f"已连接 Soniox 实时双向翻译（{A.lname(self.them)}⇄{A.lname(self.me)}）", "key": "connected", "vars": {"a": self.them, "b": self.me}})

    retries = 0   # 连续重连次数（收到识别结果就清零）
    RETRY_WAITS = (0, 1, 2, 4, 4, 4)

    async def reader(self, asr):
        try:
            async for msg in asr:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    await self.handle_event(json.loads(msg.data))
        except Exception as e:
            log.warning("soniox reader: %s", str(e)[:160])
        if not self.closed and asr is self.asr:
            await self.reconnect()

    async def reconnect(self):
        """Soniox 掉线：自动重连最多 6 次（告诉用户在重连）；全失败就给出明确错误，不再静默。"""
        while not self.closed:
            if self.retries >= len(self.RETRY_WAITS):
                log.error("soniox: gave up after %d reconnects", self.retries)
                await self.send({"type": "error", "text": "识别服务连不上了，请检查网络后重新点开始", "key": "netDown"})
                return
            wait = self.RETRY_WAITS[self.retries]
            self.retries += 1
            await self.send({"type": "status", "text": "识别会话重连中…", "key": "reconnecting"})
            await asyncio.sleep(wait)
            if self.closed:
                return
            try:
                await self.connect()
                return
            except Exception as e:
                log.warning("soniox reconnect %d failed: %s", self.retries, str(e)[:160])

    async def audio(self, data: bytes):
        try:   # 重连的空档里 Soniox 连接可能半关闭：丢掉这几十毫秒音频，别让整个浏览器连接崩掉
            await super().audio(data)
        except (ConnectionError, RuntimeError, aiohttp.ClientError):
            pass

    async def send_tr(self, text, done):
        tgt = self.me if self.cur_lang != self.me else self.them
        await self.send({"type": "translation", "id": self.cur_id, "zh": text.strip(), "lang": tgt, "done": done})

    async def handle_event(self, res):
        if res.get("error_code") is not None:
            e = f"{res.get('error_code')}: {res.get('error_message')}"
            log.warning("soniox error %s", e[:200])
            await self.send({"type": "error", "text": f"Soniox {e}", "key": "asrErr", "vars": {"e": e[:160]}})
            return
        if res.get("tokens"):
            self.retries = 0
        nf_orig, nf_tr, endpoint = "", "", False
        for t in res.get("tokens", []):
            text = t.get("text") or ""
            if text == "<end>":
                endpoint = True
                continue
            if t.get("translation_status") == "translation":
                if t.get("is_final"):
                    self.tr += text
                else:
                    nf_tr += text
                continue
            if not self.orig_lang and t.get("language") and text.strip():
                self.orig_lang = t["language"]
            if t.get("is_final"):
                self.orig += text
                if text.strip() and t.get("start_ms") is not None:
                    self.t0 = t["start_ms"] if self.t0 is None else self.t0
                    self.t1 = t.get("end_ms", t["start_ms"])
            else:
                nf_orig += text
        if endpoint and self.orig.strip():
            self.seq += 1
            self.cur_id, self.cur_lang = self.seq, (self.me if (self.orig_lang or "").split("-")[0] == self.me else self.them)
            fin = {"type": "final", "id": self.seq, "es": self.orig.strip(), "lang": self.cur_lang}
            if self.t0 is not None:
                fin["startMs"], fin["endMs"] = self.base_ms + self.t0, self.base_ms + self.t1
            await self.send(fin)
            self.t0 = self.t1 = None
            # self.tr keeps translation tokens already received for this utterance
            self.orig, self.orig_lang, nf_orig = "", None, ""
            await self.send({"type": "partial", "es": ""})
        if self.cur_id and (self.tr or nf_tr) and not (self.orig or nf_orig):
            done = not nf_tr and self.tr.strip().endswith(END_PUNCT)
            await self.send_tr(self.tr + nf_tr, done)
        elif self.orig or nf_orig:
            if self.cur_id and self.tr:
                await self.send_tr(self.tr, True)
                self.tr, self.cur_id = "", None
            partial = (self.orig + nf_orig).strip()
            if nf_tr or self.tr:
                partial += "  →  " + (self.tr + nf_tr).strip()
            await self.send({"type": "partial", "es": partial})

    async def close(self):
        self.closed = True
        if self.asr is not None and not self.asr.closed:
            try:
                await self.asr.send_str("")
                await asyncio.sleep(1)
            finally:
                await self.asr.close()


async def keepwarm():
    """Under memory pressure macOS pages model weights out; a tiny periodic run keeps them resident."""
    global _whisper_lock
    _whisper_lock = _whisper_lock or asyncio.Lock()
    while True:
        await asyncio.sleep(KEEPWARM_S)
        if not _whisper_lock.locked():
            async with _whisper_lock:
                t = time.time()
                await asyncio.to_thread(whisper_transcribe, bytes(9600))
                if time.time() - t > 1:
                    log.info("keepwarm slow: %.1fs", time.time() - t)


class LocalRelay(MetaRelay):
    """mlx-whisper (local) ASR + NewAPI translation, same browser protocol as MetaRelay."""

    def __init__(self, browser, http):
        super().__init__(browser, http)
        self.vad = Segmenter()
        self.queue = asyncio.Queue()
        self.worker = None

    async def connect(self):
        self.worker = asyncio.create_task(self.run())
        await self.send({"type": "status", "text": f"本地识别（Whisper）+ {LOCAL_CHAT_MODEL} 翻译已就绪"})

    async def run(self):
        global _whisper_lock
        _whisper_lock = _whisper_lock or asyncio.Lock()
        while True:
            seg, t_in = await self.queue.get()
            if seg is None:
                return
            t0 = time.time()
            if t0 - t_in > STALE_S:  # backlog (e.g. Mac swapping): skip old audio instead of lagging forever
                log.warning("drop stale segment %.1fs old", t0 - t_in)
                continue
            try:
                async with _whisper_lock:
                    text = await asyncio.to_thread(whisper_transcribe, seg)
            except Exception as e:
                await self.send({"type": "error", "text": f"识别失败：{e}"})
                continue
            log.info("asr %.2fs (%.1fs audio): %s", time.time() - t0, len(seg) / 48000, text)
            if text:
                self.seq += 1
                await self.send({"type": "final", "id": self.seq, "es": text})
                asyncio.create_task(self.do_translate(self.seq, text))

    async def do_translate(self, sid, text):
        try:
            zh = await translate(self.http, text, self.history, f"{OPENAI_BASE}/chat/completions",
                                 OPENAI_KEY, LOCAL_CHAT_MODEL)
            self.history.append((text, zh))
            await self.send({"type": "translation", "id": sid, "zh": zh})
        except Exception as e:
            await self.send({"type": "translation", "id": sid, "zh": "（翻译失败）", "error": str(e)[:200]})

    async def audio(self, data: bytes):
        for seg in self.vad.feed(data):
            await self.send({"type": "partial", "es": "…识别中…"})
            self.queue.put_nowait((seg, time.time()))

    async def close(self):
        self.closed = True
        for seg in self.vad.flush():
            self.queue.put_nowait((seg, time.time()))
        self.queue.put_nowait((None, 0))


async def demo_session(ws: web.WebSocketResponse, stats: dict):
    """Replay the bundled sample dialogue as partial/final transcripts."""
    script = json.loads((ROOT / "demo" / "sample_dialogue.json").read_text("utf-8"))
    await ws.send_json({"type": "status", "text": "演示模式：以下为示例数据（未接入 Meta 模型）", "key": "demoStart", "demo": True})
    for i, line in enumerate(script["lines"], 1):
        words = line["es"].split()
        for n in range(1, len(words) + 1):
            if ws.closed:
                return
            await ws.send_json({"type": "partial", "es": " ".join(words[:n]), "speaker": line.get("speaker"), "demo": True})
            await asyncio.sleep(0.18)
        await ws.send_json({"type": "final", "id": i, "es": line["es"], "speaker": line.get("speaker"), "demo": True})
        await asyncio.sleep(0.6)
        await ws.send_json({"type": "translation", "id": i, "zh": line["zh"], "demo": True})
        await ws.send_json({"type": "mic", "seconds": round(stats["bytes"] / 48000, 1)})
        await asyncio.sleep(line.get("pause", 1.2))
    await ws.send_json({"type": "status", "text": "示例对话播放完毕。麦克风仍在收音（演示模式不转写）", "key": "demoEnd", "demo": True})


META_ASR_URL = os.environ.get("META_ASR_URL", "wss://api.meta.ai/v1/asr/realtime")
META_ASR_MODEL = os.environ.get("META_ASR_MODEL", "muse-voice-transcribe-1.0")
# Muse Voice Transcribe languageBias names (ru/uk are not supported -> speaker tags off)
DIAR_LANG = {"zh": "Mandarin Chinese", "es": "Spanish", "en": "English", "fr": "French", "de": "German", "it": "Italian",
             "pt": "Portuguese", "ar": "Arabic", "ja": "Japanese", "ko": "Korean", "nl": "Dutch", "pl": "Polish",
             "tr": "Turkish", "vi": "Vietnamese", "hi": "Hindi"}


def meta_key():
    return (os.environ.get("META_API_KEY") or "").strip()


def diarize_enabled(me, them):
    return bool(meta_key()) and os.environ.get("DIARIZE", "1") != "0" and me in DIAR_LANG and them in DIAR_LANG


class Diarizer:
    """说话人区分：同一路麦克风 PCM 并行送给 Meta Muse Voice Transcribe（DIARIZATION 模式）。
    只用它的 speaker 事件（A/B…）给字幕行打标签；字幕/翻译/朗读仍全部来自 Soniox，所以不会增加字幕延迟。
    浏览器 <- {type:'speaker', label, startMs, endMs}（毫秒，从本次收听开始的音频时间轴，与 Soniox 的 final.startMs/endMs 同一时间轴）。
    Meta 不可用时静默关闭：字幕照常，只是没有说话人标签。"""

    def __init__(self, browser_send, http, me, them, clock):
        self.send, self.http, self.me, self.them, self.clock = browser_send, http, me, them, clock
        self.ws, self.base_ms, self.mark, self.closed, self.q, self.task = None, 0, 0, False, asyncio.Queue(maxsize=400), None

    ready = False

    async def connect(self):
        self.ready = False
        self.ws = await self.http.ws_connect(f"{META_ASR_URL}?sessionId=escucha-diar-{uuid.uuid4().hex[:12]}", heartbeat=20,
                                             timeout=aiohttp.ClientWSTimeout(ws_close=5))
        await self.ws.send_str(json.dumps({"authorization": {"accessToken": "Bearer " + meta_key()}, "audioEncoding": "PCM_24KHZ",
                                           "model": META_ASR_MODEL, "mode": "DIARIZATION", "emitAudioProgress": False,
                                           "languageBias": [DIAR_LANG[self.them], DIAR_LANG[self.me]]}))
        ack = await self.ws.receive(timeout=10)
        if ack.type != aiohttp.WSMsgType.TEXT or "sessionId" not in (ack.data or ""):
            raise RuntimeError("diarization handshake failed")
        self.base_ms, self.mark = self.clock(), 0
        while not self.q.empty():
            self.q.get_nowait()
        self.ready = True
        asyncio.create_task(self.reader(self.ws))
        if not self.task:
            self.task = asyncio.create_task(self.pump())

    async def start(self):
        try:
            await asyncio.wait_for(self.connect(), 12)
            await self.send({"type": "speakerStatus", "ok": True})
        except Exception as e:
            log.warning("diarization off: %s", str(e)[:120])
            self.closed = True
            await self.send({"type": "speakerStatus", "ok": False})

    def feed(self, data: bytes):
        """非阻塞：放进队列就返回，绝不拖慢 Soniox。队列满（Meta 卡住）就丢最旧的。"""
        if self.closed or not self.ready:   # 未连上时不排队：时间轴从连上那一刻算起
            return
        if self.q.full():
            try: self.q.get_nowait()
            except asyncio.QueueEmpty: pass
        self.q.put_nowait(data)

    async def pump(self):
        while not self.closed:
            data = await self.q.get()
            try:
                if self.ready and not self.ws.closed:
                    await self.ws.send_bytes(data)
            except Exception:
                pass

    async def handle(self, ev):
        t, ms = ev.get("type"), ev.get("audioProcessedMs")
        if ms is None:
            return
        if t == "speechStart":
            self.mark = ms
        elif t == "speaker" and ev.get("label"):
            await self.send({"type": "speaker", "label": str(ev["label"])[:8], "startMs": self.base_ms + self.mark, "endMs": self.base_ms + ms})
            self.mark = ms

    async def reader(self, ws):
        try:
            async for msg in ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    ev = json.loads(msg.data)
                    if ev.get("type") == "error":
                        log.warning("diarization error: %s", str(ev)[:160]); break
                    await self.handle(ev)
        except Exception as e:
            log.warning("diarization reader: %s", str(e)[:120])
        self.ready = False
        if not self.closed:   # 60 分钟上限或断线：重连，标签时间轴接着走
            try:
                await asyncio.wait_for(self.connect(), 12)
            except Exception:
                self.closed = True
                await self.send({"type": "speakerStatus", "ok": False})

    async def close(self):
        self.closed = True
        if self.ws is not None and not self.ws.closed:
            try:
                await self.ws.send_str(json.dumps({"type": "endStream"}))
            finally:
                await self.ws.close()
        if self.task:
            self.task.cancel()


async def ws_handler(request):
    ws = web.WebSocketResponse(heartbeat=25, max_msg_size=1 << 20)
    await ws.prepare(request)
    if not passcode_ok(request.query.get("code", "")):
        await ws.close(code=4401, message=b"passcode")
        return ws
    http = request.app["http"]
    stats = {"bytes": 0}
    relay, demo_task, diar = None, None, None
    clock = lambda: stats["bytes"] * 1000 // 48000   # ms of mic audio received so far (PCM16 24 kHz mono)
    try:
        async for msg in ws:
            if msg.type == aiohttp.WSMsgType.BINARY:
                if diar:
                    diar.feed(msg.data)        # 先放进说话人队列（非阻塞），再送 Soniox
                stats["bytes"] += len(msg.data)
                if relay:
                    await relay.audio(msg.data)
            elif msg.type == aiohttp.WSMsgType.TEXT:
                cmd = json.loads(msg.data)
                if cmd.get("type") == "start":
                    try:   # 浏览器断线重连时带上已有字幕编号和音频时间，编号/说话人时间轴接着走
                        stats["bytes"] = max(0, min(int(cmd.get("clock0") or 0), 6 * 3600 * 1000)) * 48
                        seq0 = max(0, int(cmd.get("seq0") or 0))
                    except (TypeError, ValueError):
                        seq0 = 0
                    if PROVIDER in ("meta", "local", "soniox") and not cmd.get("demo"):
                        cls = {"local": LocalRelay, "soniox": SonioxRelay}.get(PROVIDER, MetaRelay)
                        relay = cls(ws, http, cmd.get("me"), cmd.get("them")) if cls is SonioxRelay else cls(ws, http)
                        relay.seq = seq0
                        if cls is SonioxRelay:
                            relay.clock = clock
                            if diarize_enabled(relay.me, relay.them):
                                async def bsend(o, ws=ws):
                                    if not ws.closed:
                                        await ws.send_json(o)
                                diar = Diarizer(bsend, http, relay.me, relay.them, clock)
                                asyncio.create_task(diar.start())
                        try:
                            await relay.connect()
                        except Exception as e:
                            await ws.send_json({"type": "error", "text": f"连接识别服务失败：{e}", "key": "connFail", "vars": {"e": str(e)[:200]}})
                            relay = None
                    else:
                        demo_task = asyncio.create_task(demo_session(ws, stats))
                elif cmd.get("type") == "speak" and SONIOX_KEY and (cmd.get("text") or "").strip():
                    asyncio.create_task(stream_tts_to_browser(ws, http, cmd["text"].strip()[:500],
                                                              cmd.get("voice") or "", cmd.get("id"),
                                                              cmd.get("lang") if cmd.get("lang") in A.LANGS else "es"))
                elif cmd.get("type") == "ping":
                    await ws.send_json({"type": "mic", "seconds": round(stats["bytes"] / 48000, 1)})
    finally:
        if diar:
            await diar.close()
        if demo_task:
            demo_task.cancel()
        if relay:
            await relay.close()
    return ws


async def config(request):
    return web.json_response({"tts": bool(SONIOX_KEY), "needCode": bool(PASSCODE),
                              "llm": bool(A.llm_conf()[0] and A.llm_conf()[1]), "langs": A.LANGS, "voices": [{"id": v, "label": f"{v}（{g}）", "g": "female" if g == "女" else "male"} for v, g in TTS_VOICES],"live": PROVIDER != "demo", "provider": PROVIDER,
                              "model": {"local": WHISPER_MODEL, "soniox": SONIOX_MODEL}.get(PROVIDER, ASR_MODEL),
                              "translator": {"local": LOCAL_CHAT_MODEL, "soniox": SONIOX_MODEL}.get(PROVIDER, CHAT_MODEL)})


import assist as A


def _api(fn):
    async def h(request):
        if not passcode_ok(request.headers.get("X-Code", "")):
            return web.json_response({"error": "passcode"}, status=401)
        try:
            body = await request.json()
            return web.json_response(await fn(request.app["http"], body))
        except Exception as e:
            log.warning("api %s: %s", fn.__name__, str(e)[:200])
            return web.json_response({"error": str(e)[:200]}, status=502)
    return h


async def api_assist(http, b):
    return await A.assist(http, b.get("lines") or [], b.get("scene") or "daily", b.get("facts") or {}, bool(b.get("manual")), *A.pair(b.get("me"), b.get("them")))


async def api_summary(http, b):
    r = await A.summary(http, b.get("lines") or [], b.get("scene") or "daily", b.get("facts") or {}, *A.pair(b.get("me"), b.get("them")))
    return r


async def api_reminders(http, b):
    return {"items": await A.reminders_for(http, b.get("scene") or "daily", b.get("facts") or {}, *A.pair(b.get("me"), b.get("them")))}


async def api_translate(http, b):
    return {"text": await A.translate_typed(http, (b.get("text") or "")[:500], *A.pair(b.get("src", "zh"), b.get("tgt", "es")), b.get("lines"))}


async def index(request):
    return web.FileResponse(ROOT / "static" / "index.html")


def make_app():
    app = web.Application()
    async def on_start(app):
        app["http"] = aiohttp.ClientSession()
        if PROVIDER == "local":
            await asyncio.to_thread(warmup_whisper)
            app["keepwarm"] = asyncio.create_task(keepwarm())
    async def on_stop(app):
        await app["http"].close()
    app.on_startup.append(on_start)
    app.on_cleanup.append(on_stop)
    app.router.add_get("/", index)
    app.router.add_get("/ws", ws_handler)
    app.router.add_get("/config", config)
    for name, fn in (("assist", api_assist), ("summary", api_summary), ("reminders", api_reminders), ("translate", api_translate)):
        app.router.add_post(f"/api/{name}", _api(fn))
    app.router.add_static("/static", ROOT / "static")
    return app


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(f"Escucha on http://127.0.0.1:{PORT}  provider={PROVIDER}")
    web.run_app(make_app(), host="0.0.0.0", port=PORT, print=None)
