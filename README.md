# Escucha

**English:** Escucha is a full-duplex, face-to-face live conversation translator (any two of 17 languages, default Chinese ⇄ Spanish). The microphone never stops: while the app reads a translation aloud, it keeps listening, so nothing the other person says is lost. Built for the Meta Global AI Developer Hackathon (Indie track). Streaming speech (ASR/translation/TTS) via Soniox, summaries and speaker diarization via Meta Model API (muse-spark / muse-voice-transcribe), with an automatic multi-model fallback chain. Copy `.env.example` to `.env` and add your own API keys; no secrets are stored in this repo. Run: `./run.sh` then open http://127.0.0.1:8765 (demo mode works without keys). Chinese documentation below.

---

> 任意两种语言的面对面实时对话助手（默认 中文⇄西班牙语；顶部右侧语言按钮可改成英⇄法、中⇄日等 17 种语言任意两种）。下文以默认的中⇄西为例。

手机放在桌上，**麦克风从头到尾不停**，对方说的西班牙语实时变成**中文字幕**往下滚（每行下方小字是西语原文）。
解决的痛点：普通翻译 App 听完西语会用中文念出来，念的时候就不听了，对方接着说的话就漏掉。Escucha 只出文字、不出声音，所以永远在听。

适用场景：和学校老师谈话、政府窗口办事、维修工上门。

## 怎么运行
```bash
cd escucha
./run.sh            # 打开 http://127.0.0.1:8765
```
- 没有 `.env` / 没填 Key → **演示模式**：播放一段内置的示例对话（家长会），标注「示例数据」；麦克风照样采集并上传，用来验证收音链路，但不转写。
- 有 Key → **实时模式**：`cp .env.example .env`，填 `MODEL_API_KEY=...`，重启即可。
- 手机麦克风必须 HTTPS 页面才能用（localhost 除外）。

## 工作原理
手机浏览器 `getUserMedia` + AudioWorklet → 16 位 PCM 24kHz 单声道（每帧 80ms）→ WebSocket `/ws` →
Python 后端 → Meta 实时转写 `wss://api.meta.ai/v1/asr/realtime`（模型 `muse-voice-transcribe-1.0`，语言偏向西语+中文）→
每句说完 → Muse Spark（`muse-spark-1.3`，OpenAI 兼容接口）翻成中文 → 推回手机显示。
转写会话到时自动重连，麦克风不中断。

## 文件
| 文件 | 作用 |
|---|---|
| `server.py` | 后端：静态页面、WebSocket、Meta 转写中继、翻译、演示模式 |
| `static/index.html` `style.css` `app.js` | 手机网页 |
| `static/pcm-worklet.js` | 把麦克风声音转成 24kHz PCM |
| `demo/sample_dialogue.json` | 演示用示例对话（虚构） |
| `tests/test_server.py` | 用假的 Meta 服务器测试实时链路和演示模式 |
| `tests/headless_demo.mjs` | 无头浏览器 + 虚拟麦克风端到端测试 |

测试：`.venv/bin/python -m unittest -v tests/test_server.py`

密钥只放 `.env`（已在 `.gitignore`），代码里没有任何密钥。

---

## English
**Escucha** is a mobile web app for face-to-face conversations: the microphone never stops, and Spanish speech becomes live, scrolling Chinese captions (original Spanish shown underneath). Unlike speak-back translators, it never goes deaf while "talking".
Built for the Meta Global AI Developer Hackathon with **Muse Voice Transcribe** (realtime ASR over WebSocket) and **Muse Spark** (translation).
Run: `./run.sh`, open `http://127.0.0.1:8765`. Put `MODEL_API_KEY` in `.env` for live mode; without it the app runs a clearly labelled demo. License: MIT.

## 本地识别模式（Mac 上用 Whisper 听西语 + NewAPI 翻译）

不用 Meta Key 也能真听真翻：西语识别在 Mac 本机用 mlx-whisper（Apple 芯片加速），翻译走你的 NewAPI（默认模型 `groq-qwen-27b`）。

1. 在 `escucha` 文件夹里放一个 `.env`（权限 600，已在 .gitignore 里，不会上传）：
   ```
   OPENAI_API_KEY=你的NewAPI令牌
   OPENAI_BASE_URL=http://你的NewAPI地址:3000/v1
   ```
2. 安装并启动：
   ```bash
   cd ~/escucha
   .venv/bin/pip install -r requirements.txt mlx-whisper
   PROVIDER=local PORT=8790 .venv/bin/python -u server.py
   ```
   第一次会下载 Whisper 模型（small 约 0.5 GB）。
3. 可调参数（环境变量）：`WHISPER_MODEL`（默认 `mlx-community/whisper-small-mlx`，启动时预热）、`LOCAL_CHAT_MODEL`（默认 `groq-qwen-27b`，实测约 0.15 秒；也可用 `gpt-6-luna`，约 2 秒）、`VAD_RMS`（音量门限，默认 400）、`VAD_SILENCE`（停顿多少秒算一句，默认 0.45）、`VAD_MAX`（一句最长秒数，默认 4）、`STALE_S`（排队超过几秒的旧句子直接丢弃，默认 6）、`KEEPWARM_S`（每隔几秒空跑一次识别，防止内存紧张时模型被换出，默认 20）。

不设 `PROVIDER` 时自动选择：有 `MODEL_API_KEY` 用 Meta，有 `SONIOX_API_KEY` 用 Soniox，有 NewAPI 配置用本地模式，否则演示模式。

## Soniox 模式（日常用，最快；比赛仍用 Meta）

识别和翻译都交给 Soniox 云端（`stt-rt-v5`，西语→中文单向翻译，边说边出），Mac 上不加载任何本地模型，几乎不占内存。费用约每小时 0.18 美元。

1. 在 https://console.soniox.com 注册并创建 API Key。
2. 在 `escucha/.env` 加一行（文件权限 600，不会上传）：
   ```
   SONIOX_API_KEY=你的Soniox Key
   ```
3. 启动：
   ```bash
   cd ~/escucha
   PROVIDER=soniox PORT=8790 .venv/bin/python -u server.py
   ```
可选：`SONIOX_MODEL`（默认 `stt-rt-v5`）。

## 双向对话（Soniox 模式）

- 对方说西语 → 上方大字中文字幕（和以前一样）。
- 你说中文 → 自动翻成西语：顶部蓝色框里显示大字西语，下面小字是你的中文原话；同时用 Soniox 真人感西语声音自动朗读（底部"自动朗读"可关）。
- 点"给对方看"：全屏白底超大西语，可"翻转 180°"给桌子对面的人看。
- 防回声：朗读时麦克风继续听。如果朗读期间或结束后 1.5 秒内识别到的西语和刚读的内容有 60% 以上的词重合，就当作回声隐藏；内容不同（对方插话）照常显示。
- iPhone 上第一次点"开始收听"时会顺便解锁朗读功能（Safari 要求必须先点一下）。

测试：`node tests/echo.test.js`（回声过滤）和 `.venv/bin/python -m unittest tests/test_server.py`。

### 朗读声音（Soniox 真人感语音）
你的中文翻成西语后，由服务器调用 Soniox 实时语音合成（`tts-rt-v2`，西语），把声音分段传到手机上用 Web Audio 播放（iPhone 第一次点"开始收听"时解锁声音）。
点右下角 ⚙︎ 选择声音：Lucia（女）、Carmen（女）、Mateo（男）、Rafael（男）、Javier（男）、Santiago（男），点"试听"可以先听；选择会记住。不再使用手机自带声音。
费用约每小时生成语音 0.7 美元（只按读出来的时长计）。需要 `.env` 里有 `SONIOX_API_KEY`。

## 访问码（可选）
在 `.env` 加 `ESCUCHA_PASSCODE=你想要的码` 并重启服务后，手机第一次打开会要求输入访问码（存在手机里，之后不用再输）。不设就不需要访问码。建议用公网域名时开启，防止别人用你的付费 Key。

## 部署（Docker，自行部署示例）
- 用一个简单的 Dockerfile + docker-compose 跑 `server.py`，`.env` 里放 `SONIOX_API_KEY`、`ESCUCHA_PASSCODE` 等（权限 600，不要提交到仓库）。
- 前面放一个支持 WebSocket 的 HTTPS 反向代理。公网使用请务必设置 `ESCUCHA_PASSCODE`。
- 端到端测试：`ESCUCHA_CODE=访问码 .venv/bin/python tests/e2e_tts_ws.py`（用 `URL=wss://你的域名/ws` 指定地址）。

## 同时说同时听 + 对坐模式（2026-10-27）
- **同时说同时听**：朗读西语时麦克风不关（开启回声消除、降噪、自动增益）。手机自己放出的朗读声被认出后直接丢掉；对方插话照常翻译显示，同时朗读声音自动降到约 30%，对方停下 1.5 秒后恢复。
- **对坐模式**：点底部「对坐」，屏幕分上下两半。下半朝自己：对方的话大字中文、小字原文，自己说的话蓝色显示。上半倒转 180° 朝对方：大字全是西语（对方原话和我的话的西语翻译），我的中文原话小字显示。再点一次回到普通字幕；开关会记住。
- 测试：`node tests/echo.test.js`（含"朗读时对方插话"）；`python3 tests/browser_duplex.py 截图.png`（无头 Chrome，需先启动演示模式服务，`URL=http://127.0.0.1:端口/`）。


## v2 对话助手（场合 / 小清单 / 建议回答 / 还没问 / 纪要 / 打字）
- 代码在 `assist.py`（提示词、JSON 解析、"已说清不再问"过滤、场合必问项表），接口 `POST /api/assist|reminders|summary|translate`（访问码放在 `X-Code` 头）。
- 大模型走任意 OpenAI 兼容接口，`.env` 配置：
```
LLM_BASE_URL=http://<NewAPI 地址>:3000/v1
LLM_API_KEY=...
LLM_FAST_MODEL=groq-qwen-27b      # 每句话后的建议/清单/场合，以后可换 muse-spark-1.3
LLM_SUMMARY_MODEL=gpt-6-luna      # 结束纪要
LLM_TRANSLATE_MODEL=groq-qwen-27b # 打字翻译（不填就用 LLM_FAST_MODEL）
# 每个任务的备用模型（逗号分隔，主模型出错/429/5xx/超时/空输出时依次换下一个；下面是默认值）
# LLM_TRANSLATE_FALLBACK=groq-gpt-120b,gpt-6-luna,local-llm
# LLM_FAST_FALLBACK=groq-gpt-120b,gpt-6-luna,local-llm
# LLM_SUMMARY_FALLBACK=gpt-6-luna,groq-qwen-27b,groq-gpt-120b
# 每一步的超时秒数（按 主模型,备用1,备用2… 的顺序；默认 translate 2,2,3,5  fast 3,3,4,8  summary 15,20,10,15）
# LLM_TRANSLATE_TIMEOUTS=2,2,3,5   LLM_FAST_TIMEOUTS=3,3,4,8   LLM_SUMMARY_TIMEOUTS=15,20,10,15
# LLM_COOLDOWN_S=20   # 失败后冷却秒数；同一服务商（groq-*）两个模型都 429 会一起冷却
```
- 大模型只在字幕显示之后异步调用，绝不拖慢字幕。
- 每个模型都有备用（见上面 `*_FALLBACK`）；日志里能看到每次是谁回答的。识别/翻译/朗读用的 Soniox 没有别的服务商可换，所以掉线会自动重连并在状态栏提示。
- 测试：
```bash
.venv/bin/python -m unittest -v tests/test_assist.py tests/test_server.py
node tests/echo.test.js
REAL_LLM=1 .venv/bin/python -m unittest tests.test_assist.RealLLM   # 真实模型，需能连 NewAPI
# 浏览器测试：
.venv/bin/python tests/fake_llm.py 8798 &
LLM_BASE_URL=http://127.0.0.1:8798/v1 LLM_API_KEY=x PROVIDER=demo PORT=8799 .venv/bin/python server.py &
python3 tests/browser_v2.py && URL=http://127.0.0.1:8799/ python3 tests/browser_duplex.py
```
