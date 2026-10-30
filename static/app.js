// Escucha front-end: mic -> PCM16 24kHz -> WebSocket; captions <- WebSocket.
const $ = (id) => document.getElementById(id);
let ws, ctx, stream, node, running = false, live = false, sent = 0;
const lines = {};
const echo = Echo.createEchoGuard();
const ducker = Echo.createDucker({ duckTo: 0.3, holdMs: 1500 });
let ttsGain = null, duckTimer = null;
function duck() {   // other person talks over our TTS -> TTS to 30 %, back to 100 % after 1.5 s quiet
  if (!ttsGain) return;
  const t = playCtx.currentTime; ttsGain.gain.cancelScheduledValues(t); ttsGain.gain.setTargetAtTime(0.3, t, 0.05);
  window.__ducked = (window.__ducked || 0) + 1;
  clearTimeout(duckTimer);
  duckTimer = setTimeout(function restore() {
    if (ducker.level(Date.now()) < 1) { duckTimer = setTimeout(restore, 200); return; }
    ttsGain.gain.setTargetAtTime(1, playCtx.currentTime, 0.15);
  }, 1500);
}
const spokenIds = new Set(), speakTimers = {};
let lastMine = null;  // {es, zh}
$('autoSpeak').checked = localStorage.autoSpeak !== '0';
$('autoSpeak').onchange = () => { localStorage.autoSpeak = $('autoSpeak').checked ? '1' : '0'; };

// ---- Soniox TTS playback (PCM16 24 kHz chunks over our websocket, played with Web Audio) ----
let playCtx = null, playAt = 0, ttsSeq = 0;
const ttsText = {};   // request id -> text being spoken (for the echo guard)
function ensurePlayCtx() {
  if (!playCtx) {
    playCtx = new (window.AudioContext || window.webkitAudioContext)();
    ttsGain = playCtx.createGain(); ttsGain.connect(playCtx.destination);
  }
  if (playCtx.state === 'suspended') playCtx.resume();
  return playCtx;
}
let curVol = 1;
function playPcm(b64, rate) {
  const ctx = ensurePlayCtx();
  const bin = atob(b64), n = bin.length >> 1, buf = ctx.createBuffer(1, n, rate), ch = buf.getChannelData(0);
  for (let i = 0; i < n; i++) { let v = bin.charCodeAt(2 * i) | (bin.charCodeAt(2 * i + 1) << 8); if (v >= 32768) v -= 65536; ch[i] = v / 32768; }
  const src = ctx.createBufferSource(); src.buffer = buf; const g = ctx.createGain(); g.gain.value = curVol; src.connect(g); g.connect(ttsGain);
  playAt = Math.max(playAt, ctx.currentTime + 0.05); src.start(playAt); playAt += buf.duration;
}
function onTts(m) {
  const text = ttsText[m.id] || '';
  if (m.audio) { if (m.seq === 1) echo.started(text, Date.now()); playPcm(m.audio, m.rate || 24000); }
  if (m.end) {  // speaking state lasts until the scheduled audio has played (+1.5 s tail in the guard)
    const left = playCtx ? Math.max(0, playAt - playCtx.currentTime) : 0;
    setTimeout(() => echo.ended(text, Date.now()), left * 1000);
    delete ttsText[m.id];
    if (ttsBusy === m.id) { ttsBusy = null; setTimeout(pumpTts, left * 1000); }
  }
}
// TTS queue: one utterance at a time (my words to them / their words to me never overlap)
const ttsQueue = []; let ttsBusy = null;
function pumpTts() {
  if (ttsBusy || !ttsQueue.length) return;
  const q = ttsQueue.shift(); const sock = q.sock;
  if (!sock || sock.readyState !== 1) return pumpTts();
  const id = 't' + (++ttsSeq); ttsText[id] = q.text; ttsBusy = id; curVol = q.vol;
  sock.send(JSON.stringify({ type: 'speak', text: q.text, voice: $('voice').value, id, lang: q.lang }));
  setTimeout(() => { if (ttsBusy === id) { ttsBusy = null; pumpTts(); } }, 20000);  // safety
}
// Optional access code (server env ESCUCHA_PASSCODE): asked once, kept in localStorage.
function wsUrl() {
  return (location.protocol === 'https:' ? 'wss://' : 'ws://') + location.host + '/ws?code=' + encodeURIComponent(localStorage.passcode || '');
}
function askCode() {
  const c = prompt(t('codePrompt')); if (c !== null) localStorage.passcode = c.trim();
}
fetch('/config').then(r => r.json()).then(c => { if (c.needCode && !localStorage.passcode) askCode(); });
function requestSpeak(text, sock, lang, vol) {
  sock = sock || ws;
  if (!text || !sock || sock.readyState !== 1) return;
  ttsQueue.push({ text, sock, lang: lang || L.them, vol: vol || 1 }); pumpTts();
}
function speak(text) { if ($('autoSpeak').checked) requestSpeak(text); }
function speakTheirs(zh) { if ($('readTheirs').checked) requestSpeak(zh, ws, L.me, 0.6); }
$('readTheirs').checked = localStorage.readTheirs === '1';
$('readTheirs').onchange = () => { localStorage.readTheirs = $('readTheirs').checked ? '1' : '0'; };
// iOS Safari: audio must be unlocked by a user gesture -> create/resume the AudioContext on the first tap.
function unlockSpeech() {
  const ctx = ensurePlayCtx();
  const b = ctx.createBuffer(1, 1, 22050), s = ctx.createBufferSource(); s.buffer = b; s.connect(ctx.destination); s.start(0);
}
fetch('/config').then(r => r.json()).then(c => {
  const sel = $('voice'); sel.innerHTML = '';
  for (const v of c.voices || []) { const o = document.createElement('option'); o.value = v.id; o.dataset.g = v.g || ''; o.textContent = v.g ? (L.me === 'zh' ? v.label : `${v.id} (${t(v.g)})`) : v.label; o.dataset.label = v.label; sel.appendChild(o); }
  if (localStorage.ttsVoice && [...sel.options].some(o => o.value === localStorage.ttsVoice)) sel.value = localStorage.ttsVoice;
  if (!c.tts) { $('ttsNote').dataset.t = 'ttsOff'; $('ttsNote').textContent = t('ttsOff'); }
});
$('voice').onchange = () => { localStorage.ttsVoice = $('voice').value; };
$('gear').onclick = () => { $('sheet').hidden = false; };
$('closeSheet').onclick = () => { $('sheet').hidden = true; };
$('testVoice').onclick = () => {
  unlockSpeech();
  const sample = SAMPLE[L.them] || SAMPLE.en;
  if (ws && ws.readyState === 1) return requestSpeak(sample);
  const t = new WebSocket(wsUrl());
  t.onopen = () => requestSpeak(sample, t);
  t.onmessage = (ev) => { const m = JSON.parse(ev.data); if (m.type === 'tts') { onTts(m); if (m.end) setTimeout(() => t.close(), 500); } };
};
function showMine() {
  if (!lastMine) return;
  $('ftEs').textContent = lastMine.es || '…'; $('ftZh').textContent = lastMine.zh;
  $('fullEs').textContent = lastMine.es || '…'; $('fullZh').textContent = lastMine.zh;
}
$('show').onclick = () => { showMine(); $('full').hidden = false; };
$('closeFull').onclick = () => { $('full').hidden = true; };
$('rot').onclick = () => $('full').classList.toggle('rot');

fetch('/config').then(r => r.json()).then(c => {
  live = c.live;
  $('mode').textContent = live ? t('live') + ' · ' + (({local: 'Whisper', soniox: 'Soniox'})[c.provider] || 'Meta') : t('demo');
  $('langBtn').classList.toggle('demo', !live);
  $('mode').className = 'sr';
});

function addLine(m) {
  const div = document.createElement('div');
  div.className = 'line';
  div.innerHTML = `<div class="zh pending"></div><div class="es"></div>`;
  div.querySelector('.zh').textContent = t('translating');
  div.dataset.lang = m.lang || L.them;
  if (isMine(m.lang)) div.classList.add('me');
  const c = Echo.classify(echo, ducker, m.es, m.lang || L.them, Date.now(), L.me);
  if (!c.show) div.classList.add('echo');  // our own TTS heard back -> hidden
  else { if (c.duck) duck(); duoAdd(m); }
  div.querySelector('.es').textContent = m.es;
  if (m.speaker) div.querySelector('.es').insertAdjacentHTML('afterbegin', `<span class="who"></span>`), div.querySelector('.who').textContent = m.speaker;
  if (m.demo) div.querySelector('.es').insertAdjacentHTML('beforeend', '<span class="tag">' + t('demoTag') + '</span>');
  $('captions').appendChild(div);
  lines[m.id] = div;
  if (m.startMs != null) { div.dataset.s = m.startMs; div.dataset.e = m.endMs; div.dataset.lang0 = m.lang || ''; Speakers.line(m.id); }
  if (c.show && typeof Assist !== 'undefined') Assist.onFinal(m);
  scroll();
}
function scroll() { const c = $('captions'); if (c.scrollHeight - c.scrollTop - c.clientHeight < 200) c.scrollTop = c.scrollHeight; }

const srvVars = (m) => Object.assign({}, m.vars, m.vars && m.vars.a ? { a: lname(m.vars.a), b: lname(m.vars.b) } : {});
function onMsg(ev) {
  const m = JSON.parse(ev.data);
  if (m.type === 'tts') return onTts(m);
  if (m.type === 'status') $('status').textContent = m.key ? t(m.key, srvVars(m)) : m.text;
  else if (m.type === 'error') $('status').textContent = '⚠️ ' + (m.key ? t(m.key, srvVars(m)) : m.text);
  else if (m.type === 'partial') {
    const orig = (m.es || '').split('  →  ')[0];
    if (orig && !Echo.looksLike(orig, L.me) && Echo.classify(echo, ducker, orig, L.them, Date.now(), L.me).duck) duck();
    $('partial').textContent = echo.isEcho(orig, Date.now()) ? '' : m.es;
  }
  else if (m.type === 'final') {
    $('partial').textContent = ''; addLine(m);
    if (isMine(m.lang)) { lastMine = { es: '', zh: m.es }; showMine(); }
  }
  else if (m.type === 'translation') {
    const d = lines[m.id]; if (!d) return;
    const z = d.querySelector('.zh'); z.textContent = m.zh; z.classList.remove('pending'); scroll(); duoUpdate(m.id, m.zh);
    if (!d.classList.contains('echo') && typeof Assist !== 'undefined') Assist.onTranslation(m, isMine(d.dataset.lang));
    if (isMine(d.dataset.lang)) {
      lastMine = { es: m.zh, zh: d.querySelector('.es').textContent }; showMine();
      // speak once the Spanish translation is complete (debounced in case more tokens follow)
      clearTimeout(speakTimers[m.id]);
      if (m.done && !spokenIds.has(m.id)) speakTimers[m.id] = setTimeout(() => {
        spokenIds.add(m.id); speak(lines[m.id].querySelector('.zh').textContent);
      }, 400);
    }
  } else if (m.type === 'speaker') Speakers.span(m);
  else if (m.type === 'speakerStatus') window.__speakerOk = m.ok;
  else if (m.type === 'mic') window.__serverMicSeconds = m.seconds;
}

async function startMic() {
  stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true } });
  ctx = new (window.AudioContext || window.webkitAudioContext)();
  await ctx.audioWorklet.addModule('/static/pcm-worklet.js');
  node = new AudioWorkletNode(ctx, 'pcm-worklet');
  node.port.onmessage = (e) => {
    $('level').style.width = Math.min(100, e.data.peak * 200) + '%';
    if (ws && ws.readyState === 1) { ws.send(e.data.pcm); sent += 0.08; sessSent += 0.08; }
    $('mic').textContent = t('micOn', { n: sent.toFixed(0) });
  };
  ctx.createMediaStreamSource(stream).connect(node);
  // Silent sink keeps the graph running on Safari; nothing is played aloud.
  const mute = ctx.createGain(); mute.gain.value = 0; node.connect(mute).connect(ctx.destination);
}

let sessSent = 0, wsRetrying = false, wsGen = 0;
function maxLineId() { return Math.max(0, ...Object.keys(lines).map(Number).filter(Number.isFinite)); }
// 连接（或断线后重连）识别服务。重连时带上已有的字幕编号和音频时间，编号/说话人时间轴接着走。
async function openWs() {
  const gen = ++wsGen, sock = new WebSocket(wsUrl());
  sock.binaryType = 'arraybuffer';
  sock.onmessage = onMsg;
  sock.onclose = (e) => {
    if (gen !== wsGen || !running) return;   // 已被新连接取代 / 用户已点停止
    if (e.code === 4401) { localStorage.removeItem('passcode'); $('status').textContent = t('codeWrong'); askCode(); stop(); return; }
    if (live) reconnectWs(); else $('status').textContent = t('disconnected');
  };
  await new Promise((ok, bad) => { sock.onopen = ok; sock.onerror = () => bad(new Error('ws')); });
  ws = sock;
  ws.send(JSON.stringify({ type: 'start', demo: !live, me: L.me, them: L.them, seq0: maxLineId(), clock0: Math.round(sessSent * 1000) }));
}
// 断线自动重连：最多 6 次（0.5/1/2/4/4/4 秒），每次都在状态栏提示；全失败才让用户手动点开始
async function reconnectWs() {
  if (wsRetrying) return;
  wsRetrying = true;
  const waits = [500, 1000, 2000, 4000, 4000, 4000];
  try {
    for (let n = 0; n < waits.length && running; n++) {
      $('status').textContent = t('netLost', { n: (n + 1) + '/' + waits.length });
      await new Promise(r => setTimeout(r, waits[n]));
      if (!running) return;
      try { await openWs(); return; } catch (_) { /* 再试 */ }
    }
    if (running) { stop(); $('status').textContent = '⚠️ ' + t('netDown'); }
  } finally { wsRetrying = false; }
}

async function start() {
  unlockSpeech();
  running = true; sessSent = 0; $('goLbl').dataset.t = 'stop'; $('go').dataset.ta = 'stopAria'; $('goLbl').textContent = t('stop'); $('go').classList.add('stop'); $('go').setAttribute('aria-label', t('stopAria'));
  await openWs();
  try { await startMic(); }
  catch (e) { $('mic').textContent = t('micErr', { e: e.message }); }
}
function stop() {
  running = false; wsGen++; $('goLbl').dataset.t = 'start'; $('go').dataset.ta = 'startAria'; $('goLbl').textContent = t('start'); $('go').classList.remove('stop'); $('go').setAttribute('aria-label', t('startAria'));
  if (stream) stream.getTracks().forEach(t => t.stop());
  if (ctx) ctx.close();
  if (ws) ws.close();
  $('mic').textContent = t('micClosed');
}
$('go').onclick = () => (running ? stop() : start());

// ---- 对坐模式: bottom half faces me, top half faces them. Mirrored & bilingual:
// each half: the OTHER side's lines big (in this half's language) + small original; this side's own lines one size smaller.
// Top half is NOT rotated as a whole (iOS can't scroll a rotated scroller): items are rotated one by one and the
// newest item sits at the physical top (= their bottom), so scrolling works natively in both halves.
const duo = {};
function duoItem(big, small, own) {
  const d = document.createElement('div'); d.className = 'dl' + (own ? ' own' : '');
  d.innerHTML = '<div class="big"></div><div class="small"></div>';
  d.querySelector('.big').textContent = big;
  if (small === null) d.querySelector('.small').remove(); else d.querySelector('.small').textContent = small; return d;
}
const NEAR = 80;
function meNear() { const e = $('duoMe'); return e.scrollHeight - e.scrollTop - e.clientHeight < NEAR; }
function themNear() { return $('duoThem').scrollTop < NEAR; }
function duoAppendMe(el) { const e = $('duoMe'), near = meNear(); e.appendChild(el); if (near) e.scrollTop = e.scrollHeight; else $('newMe').hidden = false; }
function duoPrependThem(el) {
  const e = $('duoThem'), near = themNear(); e.insertBefore(el, e.firstChild);
  if (near) e.scrollTop = 0; else { e.scrollTop += el.offsetHeight; $('newThem').hidden = false; }
}
function duoResize(el, half, fn) {  // keep the reader's position when a line grows (translation arrives)
  if (half === 'them') { const e = $('duoThem'), near = themNear(), h = el.offsetHeight; fn(); if (!near) e.scrollTop += el.offsetHeight - h; else e.scrollTop = 0; }
  else { const near = meNear(); fn(); if (near) $('duoMe').scrollTop = $('duoMe').scrollHeight; }
}
$('duoMe').addEventListener('scroll', () => { if (meNear()) $('newMe').hidden = true; });
$('duoThem').addEventListener('scroll', () => { if (themNear()) $('newThem').hidden = true; });
$('newMe').onclick = () => { $('duoMe').scrollTop = $('duoMe').scrollHeight; $('newMe').hidden = true; };
$('newThem').onclick = () => { $('duoThem').scrollTop = 0; $('newThem').hidden = true; };
function duoAdd(m) {
  const mine = isMine(m.lang);
  // bottom (me): their line -> big 中文 (pending) + small Spanish; my line -> own (smaller) my Chinese + small Spanish
  const a = duoItem(mine ? m.es : t('translating'), mine ? '…' : m.es, mine);
  // top (them): my line -> big Spanish (pending) + small my Chinese; their line -> own (smaller) Spanish only
  const b = duoItem(mine ? '…' : m.es, mine ? m.es : null, !mine);  // their own line: original only, no bilingual
  if (!mine) a.querySelector('.big').classList.add('pending'); else b.querySelector('.big').classList.add('pending');
  duoAppendMe(a); duoPrependThem(b);
  duo[m.id] = { mine, a, b };
}
function duoUpdate(id, tr) {
  const x = duo[id]; if (!x) return;
  if (x.mine) {
    duoResize(x.b, 'them', () => { const z = x.b.querySelector('.big'); z.textContent = tr; z.classList.remove('pending'); });
    duoResize(x.a, 'me', () => { x.a.querySelector('.small').textContent = tr; });
  } else {
    duoResize(x.a, 'me', () => { const z = x.a.querySelector('.big'); z.textContent = tr; z.classList.remove('pending'); });
    // top half: their own line stays original-only
  }
}
function setDuo(on) {
  $('forThem').hidden = true; $('full').hidden = true;   // no leftover blocks when switching views
  document.body.classList.toggle('duo', on); $('duoBtn').classList.toggle('on', on); $('duoBtn').setAttribute('aria-pressed', on);
  localStorage.duo = on ? '1' : '0';
  if (on) requestAnimationFrame(() => { $('duoMe').scrollTop = $('duoMe').scrollHeight; $('duoThem').scrollTop = 0; $('newMe').hidden = $('newThem').hidden = true; });
}
$('duoBtn').onclick = () => setDuo(!document.body.classList.contains('duo'));
setDuo(localStorage.duo === '1');

// ---- 语言切换：顶部右侧按钮 -> 小面板（我的语言 / 对方的语言 / 互换），改了就记住
function langLabel() {
  applyI18n(); if (typeof Speakers !== 'undefined') Speakers.relabel();
  [...$('voice').options].forEach(o => { if (o.dataset.g) o.textContent = L.me === 'zh' ? o.dataset.label : `${o.value} (${t(o.dataset.g)})`; });
  $('langTxt').textContent = shortCode(L.me) + '⇄' + shortCode(L.them);
  $('langBtn').setAttribute('aria-label', t('langAria', { me: lname(L.me), them: lname(L.them) }));
  $('duoThem').lang = L.them; $('duoMe').lang = L.me; $('newThem').textContent = tThem('latest'); $('newThem').setAttribute('aria-label', tThem('latest'));
  $('duoThem').dataset.empty = (I18N[L.them] || I18N.en).emptyThem || I18N.en.emptyThem; $('duoMe').dataset.empty = t('emptyMe');
  $('dbThem').textContent = L.them.toUpperCase(); $('dbMe').textContent = L.me === 'zh' ? '中' : L.me.toUpperCase();
  $('typeBox').dataset.base = t('typePh', { me: lname(L.me), them: lname(L.them) });
  $('missHint').textContent = t('missHint', { them: lname(L.them) });
  if (typeof Assist !== 'undefined') Assist.relabel();
}
function fillLangs() {
  for (const [id, v] of [['langMe', L.me], ['langThem', L.them]]) {
    const sel = $(id); sel.innerHTML = '';
    for (const [c, n] of Object.entries(LANGS)) { const o = document.createElement('option'); o.value = c; o.textContent = L.me === 'zh' ? `${n[0]} · ${n[2]}` : (lname(c) === n[2] ? n[2] : `${lname(c)} · ${n[2]}`); sel.appendChild(o); }
    sel.value = v;
  }
}
function setLangs(me, them) {
  if (me === them) { $('langWarn').hidden = false; return false; }
  $('langWarn').hidden = true;
  const changed = me !== L.me || them !== L.them;
  L.me = me; L.them = them; localStorage.langMe = me; localStorage.langThem = them; langLabel(); fillLangs();
  if (changed && running) { stop(); start(); }   // 新语言对要重新连接识别
  return true;
}
$('langBtn').onclick = () => { fillLangs(); $('langWarn').hidden = true; $('langSheet').hidden = false; };
$('langMe').onchange = $('langThem').onchange = () => setLangs($('langMe').value, $('langThem').value);
$('langSwap').onclick = () => { const a = $('langMe').value, b = $('langThem').value; $('langMe').value = b; $('langThem').value = a; setLangs(b, a); };
$('langClose').onclick = () => { $('langSheet').hidden = true; };
langLabel();

// ---- 说话人标签（Meta Muse Voice Transcribe 并行区分说话人）：按时间重叠把 A/B 标到字幕行上 ----
// 字幕不等它：标签晚到就晚一点出现。语言判断仍是主依据；只有语言不在这对语言里（判不准）时，才用"这个说话人通常是谁"来定我/对方。
var Speakers = (function () {
  const spans = [], stats = {}, order = [], names = {}, pending = {};   // stats[label] = {mine, theirs}; names[label] = {name, manual}
  function overlap(a0, a1, b0, b1) { return Math.max(0, Math.min(a1, b1) - Math.max(a0, b0)); }
  function isMe(label) { const st = stats[label]; return !!st && st.mine > st.theirs; }
  // 我 / 对方 / 对方 2 …（按出现顺序；不显示原始 A/B），有名字就用名字
  function display(label) {
    if (names[label]) return names[label].name;
    if (isMe(label)) return t('spkMe');
    const others = order.filter(l => !isMe(l)), i = others.indexOf(label);
    return i <= 0 ? t('spkThem') : t('spkThemN', { n: i + 1 });
  }
  function rename(label) {
    const v = window.prompt(t('renamePrompt'), display(label)); if (v == null) return;
    const name = v.trim().slice(0, 30);
    if (name) names[label] = { name, manual: true }; else delete names[label];
    relabel();
  }
  function tag(el, label) {
    if (!el) return;
    let g = el.querySelector('.spk');
    if (!g) {
      g = document.createElement('span'); g.className = 'spk'; g.setAttribute('role', 'button'); g.tabIndex = 0;
      g.onclick = (e) => { e.stopPropagation(); rename(g.dataset.label); };
      g.onkeydown = (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); rename(g.dataset.label); } };
      (el.querySelector('.es') || el.querySelector('.small') || el).prepend(g);
    }
    g.dataset.label = label; g.textContent = display(label); g.setAttribute('aria-label', t('spkAria', { s: display(label) }));
  }
  function relabel() { document.querySelectorAll('.spk').forEach(e => { e.textContent = display(e.dataset.label); e.setAttribute('aria-label', t('spkAria', { s: e.textContent })); }); }
  function setName(id, name) {
    const d = lines[id], label = d && d.dataset.spk;
    if (!label) { pending[id] = name; return; }
    if (isMe(label) || (names[label] && names[label].manual)) return;
    names[label] = { name, manual: false }; relabel();
  }
  function assign(id) {
    const d = lines[id]; if (!d || d.dataset.s == null) return;
    const s0 = +d.dataset.s, s1 = +d.dataset.e + 300, ov = {};
    for (const p of spans) { const o = overlap(s0, s1, p.startMs, p.endMs); if (o > 0) ov[p.label] = (ov[p.label] || 0) + o; }
    const best = Object.keys(ov).sort((a, b) => ov[b] - ov[a])[0]; if (!best || d.dataset.spk === best) return;
    const prev = d.dataset.spk; d.dataset.spk = best;
    if (!order.includes(best)) order.push(best);
    const lang = (d.dataset.lang0 || '').split('-')[0], known = lang === L.me || lang === L.them;
    if (known) { if (prev && stats[prev]) stats[prev][lang === L.me ? 'mine' : 'theirs']--; (stats[best] = stats[best] || { mine: 0, theirs: 0 })[lang === L.me ? 'mine' : 'theirs']++; }
    else {   // 语言判不准 -> 看这个说话人以往多半是谁
      const st = stats[best] || { mine: 0, theirs: 0 }, n = st.mine + st.theirs;
      if (n >= 2 && Math.max(st.mine, st.theirs) / n >= 0.75) {
        const mine = st.mine > st.theirs; d.classList.toggle('me', mine); d.dataset.lang = mine ? L.me : L.them;
        if (typeof Assist !== 'undefined' && Assist.state.byId[id]) Assist.state.byId[id].me = mine;
      }
    }
    tag(d, best); if (typeof duo !== 'undefined' && duo[id]) tag(duo[id].a, best);
    if (pending[id]) { const nm = pending[id]; delete pending[id]; setName(id, nm); }
    relabel();
  }
  return {
    span(m) { spans.push(m); if (spans.length > 400) spans.shift(); for (const id of Object.keys(lines).slice(-30)) assign(id); },
    line(id) { assign(id); },
    relabel, setName, display, rename,
    // 给纪要/建议用的称呼：对方的行才带（我方不带）
    who(id) { const d = lines[id], l = d && d.dataset.spk; return l && !isMe(l) ? display(l) : ''; },
    stats, spans, names, order,
  };
})();
