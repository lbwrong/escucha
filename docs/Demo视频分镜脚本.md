# Escucha 3 分钟 Demo 视频分镜脚本

> 不用真人露脸：只拍**手 + 手机 + 屏幕录制 + 旁白**。**一个人 + 两台设备**：设备 A＝iPhone 跑 Escucha（真实现场识别/翻译）；设备 B＝笔记本电脑（或第二部手机）用 `demo-audio/player.html` 外放事先合成好的西语“医生”台词。
> 评分：Impact 30% / Meta 工具 25% / Demo 25% / 技术深度 20%。视频要让评委 20 秒内看懂“为什么不一样”。
> 原则：**App 全程真跑、不剪不假**；医生的声音是预先合成的西语语音，从设备 B 真实外放、被 iPhone 麦克风现场听到——视频里明确标注（见第七节）。另录一段 60 秒无剪辑完整片段放 README。

---

## 一、器材和准备清单

| 项目 | 说明 |
|---|---|
| iPhone（主角） | 运行 Escucha（你的网址），电量 >80%，开勿扰模式，亮度调最高、自动锁定设“永不” |
| 第二部手机 / 电脑 | ①拍摄机位（俯拍、侧拍）；②开场播放“别的翻译软件” |
| 手机支架 | 俯拍用：顶视支架或台灯夹；没有就用两摞书架一根尺子 |
| iPhone 自带屏幕录制 | 控制中心 → 屏幕录制（长按打开“麦克风”，录到声音） |
| 桌面布置 | 浅色桌布或木桌，一张“处方”或预约单当道具，一支笔 |
| 安静房间 | 关空调/风扇，避免回声大的空房间 |
| 演员 | 只有你自己：“我”说中文；“医生”＝设备 B 播放 `demo-audio/*.mp3`（西班牙女声 es-ES） |
| 设备 B（医生） | 笔记本/第二部手机打开 `demo-audio/player.html`，音量 60–70%，扬声器朝向 iPhone 底部麦克风，距离 50–80 cm；关掉设备 B 的通知声 |
| “医生”道具 | 设备 B 旁放听诊器/白大褂一角/写着 “Dra. García” 的小名牌，或在设备 B 屏幕上显示医生头像图，俯拍时把它当“对面的医生” |
| 剪辑软件 | 剪映（有自动字幕 + 英文翻译字幕，最省事）或 iMovie / CapCut |
| 打印台词 | 把你自己的中文台词打印出来，放在镜头外照着念 |

拍摄前 10 分钟：刷新网站 → 说两句试试字幕、朗读、“谁在说话”标签都正常 → 关掉 Wi‑Fi 不稳的设备。

---

## 一点五、一个人 + 两台设备怎么拍（替代真人医生）

**摆位**：iPhone（A）平放桌子中间偏你这边；设备 B 放在桌子对面“医生的位置”，扬声器朝 iPhone，距离 50–80 cm。太近会爆音、太远识别变慢。先试播 06 号台词：iPhone 上西语原文完整、无错字即可；不准就调近 10 cm 或音量 +10%。拍摄机位（第三部手机或支架）只拍 iPhone 和你的手；设备 B 可以露一角（带道具），代表“医生”。

**医生的手怎么办**：不拍医生的手。镜头里的“医生”就是对面那台设备 + 道具（名牌 “Dra. García”/听诊器）。镜头 6 俯拍时上半屏朝向设备 B，正好表示“对面是医生”。

**台词与文件对应**（`demo-audio/`，每个开头有 0.5 秒静音）：
| 镜头 | 文件 | 台词 |
|---|---|---|
| 1 | 01_alergico.mp3 | Perdone, ¿es alérgico a algún medicamento? |
| 4 ★插话 | 04_tiene_fiebre.mp3 | Vale, vale. ¿Tiene fiebre también? |
| 6 | 06_doctora_garcia.mp3 | Buenos días. Soy la doctora García. ¿Qué le pasa? |
| 7 | 07a_ibuprofeno.mp3 → 07b_despues_de_comer.mp3 | 开药 → 饭后吃 |
| 8 | 08a_ya_esta.mp3 → 08b_volver_cita.mp3 | 再见 → 一周后再预约 |

**镜头 4 插话时机**：你说完中文 → Escucha 开始用西语朗读（约 3–4 秒长）→ 听到朗读开头约 1 秒时，用左手点设备 B 上橙色★按钮。这样插话正好落在朗读中间。多拍 3–5 遍，挑字幕最快的一条。
注意：iPhone 朗读声和设备 B 声音同时响是正常的，这正是要演示的“全双工”。

**其他镜头**：每次点“开始”后等 3 秒再点播放（让说话人标签就绪）；一句播完、字幕出来后再进行下一步。

---

## 二、分镜总表

| 段落 | 时间 | 内容 | 主打评分项 |
|---|---|---|---|
| 1 | 0:00–0:20 | 痛点：别的翻译软件朗读时“聋了” | Impact |
| 2 | 0:20–1:20 | 全双工：朗读时对方插话，照样翻译 | Demo / 技术 |
| 3 | 1:20–2:10 | 看医生：对坐俯拍、名字标签、建议回复、还没问、纪要 | Impact / Meta |
| 4 | 2:10–2:30 | 无障碍：盲人 / 聋人 / 不能说话 | Impact |
| 5 | 2:30–3:00 | 架构 + Meta 用法 + 实测速度 | Meta / 技术 |

---

## 三、逐镜头脚本

### 镜头 1｜0:00–0:10 痛点：别的软件
- **机位**：侧面 45°，拍桌上两部手机和两只手。
- **画面**：左边手机是普通翻译软件（品牌打码或不露名），正在朗读中文→西语。
- **动作**：软件朗读时，医生在画外插话说西语；那款软件屏幕上没有任何新字。
- **医生（插话）**：「Perdone, ¿es alérgico a algún medicamento?」（不好意思，您对什么药过敏吗？）
- **旁白**：「我住在西班牙，不会说西语。我试过的翻译软件都有同一个问题：它一开口朗读，就听不见对方了。」
- **英文字幕**：I live in Spain and don't speak Spanish. Every translator I tried goes deaf while it's speaking.

### 镜头 2｜0:10–0:20 问题后果 + 片名
- **画面**：定格在没反应的屏幕上，打红字“漏听 ✗”；黑屏出 Logo“Escucha — 朗读时也在听”。
- **旁白**：「看医生的时候，漏掉一句话，可能就是漏掉一种过敏药。所以我做了 Escucha——西语‘听’的意思。」
- **英文字幕**：At the doctor's, one missed sentence can be a missed allergy. So I built Escucha — "listen" in Spanish. It listens even while it talks.

### 镜头 3｜0:20–0:40 我说话，开始朗读
- **App 设置**：普通模式；语言 中⇄西；“朗读我的话给对方”开；“朗读对方的话给我”关；场合 日常。
- **机位**：iPhone 屏幕录制（主画面）+ 右下角小窗拍手。
- **动作**：点中间“开始”，说中文。
- **我（中文）**：「你好，我最近三天一直头疼，晚上也睡不好，想请医生帮我看一下。」
- **画面**：字幕出现，Escucha 开始用西语朗读这句。
- **旁白**：「我说中文，它马上翻成西语读给对方听。」
- **英文字幕**：I speak Chinese; Escucha reads it aloud in Spanish.

### 镜头 4｜0:40–1:05 关键镜头：朗读中插话
- **动作**：在 Escucha 还在朗读时，医生直接打断。
- **医生**：「Vale, vale. ¿Tiene fiebre también?」（好的好的，您也发烧吗？）
- **画面**：朗读音量自动变小（剪辑时加文字“朗读降到 30%”），屏幕上同时出现中文大字“好的好的，您也发烧吗？”，小字西语原文；1.5 秒后朗读音量恢复。
- **旁白**：「对方随时插话，它照样听、照样翻，朗读声音自动让路。这就是全双工。」
- **英文字幕**：Interrupt anytime — it keeps listening and translating. Playback ducks automatically. This is full duplex.

### 镜头 5｜1:05–1:20 回声不会被当成对方的话
- **我**：「没有发烧，就是头疼。」
- **画面**：朗读西语时，屏幕上**没有**重复出现自己的朗读内容；放大字幕区。
- **旁白**：「手机自己读出来的声音会被过滤掉，不会被当成对方又说了一遍。」
- **英文字幕**：Its own voice is filtered out as echo — no fake lines.

### 镜头 6｜1:20–1:35 对坐俯拍 + 医生自我介绍
- **App 设置**：点“对坐”；场合可留“日常”，演示 AI 自动切到“看医生”（若没自动切，提前在 ⚙︎ 选“看医生”）。
- **机位**：手机**正上方俯拍**，平放在桌子中间；医生的手在上方，我的手在下方。
- **医生**：「Buenos días. Soy la doctora García. ¿Qué le pasa?」（早上好，我是 García 医生。您哪里不舒服？）
- **画面**：上半屏朝医生显示西语；下半屏我这边显示中文；说话人标签由“对方”变成“García 医生”（剪辑时圈出来）。
- **旁白**：「对坐模式：手机放在中间，两边各看自己的语言。Meta 的语音模型听出这是另一个人，听到自我介绍后，标签自动变成‘García 医生’。」
- **英文字幕**：Face-to-face mode. Meta's voice model tells speakers apart and auto-names "Dr. García" from her intro.

### 镜头 7｜1:35–1:50 医生开药 + 点建议回复
- **医生**：「Le voy a recetar ibuprofeno, seiscientos miligramos, cada ocho horas, durante cinco días.」（我给您开布洛芬，600 毫克，每 8 小时一次，吃 5 天。）
- **动作**：我点输入框 → 出现 2–3 条建议 → 点一条，例如「饭前吃还是饭后吃？」→ 发送并朗读成西语。
- **画面**：小清单自动加上“布洛芬 600mg，每 8 小时，5 天”。
- **医生（回答）**：「Después de comer, siempre con algo en el estómago.」（饭后吃，胃里一定要有东西。）
- **旁白**：「每听一句，AI 结合整场对话给出建议回复，点一下就能问，已经问过的不会重复。」
- **英文字幕**：After every line, AI suggests replies based on the whole conversation. One tap to ask.

### 镜头 8｜1:50–2:02 结束 → 还没问
- **我**：（点“结束”，或医生说）「Bueno, pues ya está. Adiós.」（好了，就这样，再见。）
- **画面**：弹出“还没问”：例如“需要复诊吗？”“有什么副作用要注意？”，每条带现成西语问题。点一条直接朗读：
  - 屏幕朗读：「¿Tengo que volver a la consulta?」（我需要再来复诊吗？）
- **医生**：「Si en una semana sigue igual, pida cita otra vez.」（如果一周后还这样，再预约。）
- **旁白**：「结束前，它会提醒这个场合重要但还没问的事，点一下就替我问。」
- **英文字幕**：Before you leave, it reminds you what you forgot to ask — ready to read aloud.

### 镜头 9｜2:02–2:10 纪要
- **画面**：纪要页：总结 + 待办（“布洛芬 600mg 每 8 小时饭后，5 天”“一周不好转再预约”），点“加到日历”“复制”。
- **旁白**：「最后，Meta 的 Muse Spark 在约 1.3 秒内写好中文纪要和待办。」
- **英文字幕**：Meta Muse Spark writes the summary and to-dos in about 1.3 s.

### 镜头 10｜2:10–2:30 无障碍（快切，每个约 6 秒）
- **画面 A**：⚙︎ 打开两个朗读开关 → 文字“看不见：双向语音”。
- **画面 B**：两个开关都关，字幕大字 → 文字“听不见：纯字幕”。
- **画面 C**：在输入框打字「我听不见，请写下来」→ 朗读成西语。
- **旁白**：「看不见，就双向朗读；听不见，就纯字幕；不能说话，就打字让它读。语言也不限于中西，任意两种都行。」
- **英文字幕**：Blind: two-way voice. Deaf: captions only. Can't speak: type and it speaks. Any two languages.
- （可加 1 秒：语言按钮切到 英⇄法 的画面）

### 镜头 11｜2:30–2:50 架构 + Meta
- **画面**：一张架构图（Keynote/PPT 做一页，按下面内容）：
  ```
  iPhone 麦克风（回声消除）──┬─► Soniox：实时识别 + 翻译 + 朗读（TTS）
                              └─► Meta muse-voice-transcribe-1.0：说话人区分 → “García 医生”
  每句话 ─► 快模型：建议回复 + 小清单（0.5–0.7 s）
  结束   ─► Meta muse-spark-1.3：纪要 + 待办（P50 1.34 s / P90 1.58 s）
  ```
- **旁白**：「同一路声音并行送两处：Soniox 负责边听边翻和朗读，因为 Meta 目前没有语音合成；Meta 的语音模型负责分清谁在说话；Muse Spark 负责纪要。任何一处出错都会自动降级，对话不中断。」
- **英文字幕**：One mic stream, two engines in parallel: Soniox for streaming translation and TTS (Meta has no TTS yet); Meta Voice Transcribe for speaker diarization; Muse Spark for summaries. Graceful fallback everywhere.

### 镜头 12｜2:50–3:00 数字收尾
- **画面**：大字数字卡：
  - 建议回复 0.5–0.7 s
  - 纪要（Muse Spark）P50 1.34 s
  - 说话人标签：句末后约 1–1.5 s
  - 打字翻译 0.09–0.14 s
  - 目标：对方说完到看到译文 ≤ 2 s
  - 最后：Logo + 你的网址
- **旁白**：「Escucha：它在说话的时候，也在听你说话。」
- **英文字幕**：Escucha — it listens, even while it speaks.
- ⚠️ 如果拍摄前补测了 iPhone 端到端 P50/P90 和回声误判率，把这两个数字放在第一行，最有说服力。

---

## 四、每段拍摄前的 App 设置

| 镜头 | 模式 | 语言 | 朗读我的话 | 朗读对方的话 | 场合 |
|---|---|---|---|---|---|
| 1–2 | （别的软件） | — | — | — | — |
| 3–5 | 普通 | 中⇄西 | 开 | 关 | 日常 |
| 6–9 | 对坐 | 中⇄西 | 开 | 关 | 自动（备用：看医生） |
| 10 | 普通 | 中⇄西（可切英⇄法 1 秒） | 按画面切换 | 按画面切换 | 任意 |

每段开拍前：点“结束”清空上一段对话，再重新“开始”，免得旧内容出现在纪要里。

---

## 五、英文字幕 / 旁白建议
- 评委是国际的，**至少要英文字幕**。推荐做法：旁白用中文真声（更真实，也呼应“我不会西语”的故事），**画面烧录英文字幕**。
- 或者英文旁白：剪映“文本朗读”可用 AI 英文配音，但对话部分一律保留真人声音。
- App 屏幕上的中文字幕旁，剪辑时可加小号英文注释（如 “Chinese caption: Do you also have a fever?”），让评委看懂翻译是对的。
- 医生的西语台词也配英文字幕。
- 医生台词出现时，角落加小字：“Doctor voice: pre-recorded Spanish TTS played aloud from a laptop. App runs live.”

---

## 六、重拍和剪辑小贴士
1. **镜头 4 最重要**，多拍 3–5 遍，挑插话时机最清楚、字幕出得最快的一条。
2. 插话要在朗读**正在进行**时开始，不要等读完。
3. 设备 B 离 iPhone 50–80 cm、音量 60–70%；你自己说话离手机 30 cm 左右，除镜头 4 外不要和播放同时说。
4. 俯拍要防反光：避开头顶灯，可以把手机稍倾斜或关灯用侧光。
5. 屏幕录制和外部机位分开录，剪辑时用拍手声对齐。
6. 不要加速关键镜头（评委会质疑延迟）；可以剪掉“等待”的空白，但关键插话段保留原速，最好角落标“Real time, no cuts”。
7. 名字标签有时要 1–2 秒才出现，开头 3 秒内说的话可能没标签——点“开始”后等 3 秒再点播放医生台词。
8. 万一某次识别错了，不要硬剪，重拍一遍。
9. 总长控制在 2:55–3:00，超时可能扣分。
10. 导出 1080p，上传 YouTube（不公开/公开）并检查字幕。

---

## 七、提交用英文简介（约 100 词）

**Escucha — a full‑duplex live conversation helper**

Escucha helps immigrants talk to doctors, schools, banks and government offices in a language they don't speak. Unlike other translators that go deaf while speaking, Escucha keeps listening and translating during playback, ducking its own voice when the other person interrupts and filtering its own echo. Meta's muse-voice-transcribe-1.0 tells speakers apart and auto-names them from self-introductions; muse-spark-1.3 writes the summary and to-dos in ~1.3 s. After every line it suggests context-aware replies, and before you leave it reminds you what you forgot to ask. Face-to-face split screen, any two languages, and accessible modes for blind, deaf and non-speaking users.

*Demo note: to film alone, the doctor's Spanish lines are pre-recorded TTS played aloud from a laptop; Escucha hears and translates them live on the iPhone, with no edits to the app's output.*
