// Escucha v2 assistant UI: 场合 / 已知信息 / 建议回答 / 打字 / 还没问 / 纪要.
// All LLM calls happen AFTER a caption is shown and never block captions.
const tr = (...a) => t(...a);
const Assist = (function () {
  const S = { scene: localStorage.scene || 'daily', manual: localStorage.sceneManual === '1', prevScene: null,
              facts: {}, conv: [], byId: {}, reqN: 0, timers: {}, typedN: 0, summary: null };
  const NAMES = new Proxy({}, { get: (_, k) => t('scene_' + String(k)) });
  const LABEL = new Proxy({}, { get: (_, k) => { const v = t('f_' + String(k)); return v === 'f_' + String(k) ? undefined : v; } });
  const api = (name, body) => fetch('/api/' + name, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Code': localStorage.passcode || '' },
    body: JSON.stringify(body) }).then(r => r.json());
  const lines = () => S.conv.map(l => { const o = { me: l.me, orig: l.orig, tr: l.tr }, w = !l.me && typeof Speakers !== 'undefined' ? Speakers.who(l.id) : ''; if (w) o.who = w; return o; });
  window.__assist = S;

  function setScene(s, manual) {
    S.scene = s; localStorage.scene = s;
    if (manual !== undefined) { S.manual = manual; localStorage.sceneManual = manual ? '1' : '0'; }
    document.querySelectorAll('#scenes button').forEach(b => { const on = b.dataset.s === s; b.classList.toggle('on', on); b.setAttribute('aria-checked', on); if (on && $('sceneChip')) { $('sceneChip').textContent = NAMES[s]; $('sceneChip').setAttribute('aria-label', t('sceneChipAria', { s: NAMES[s] })); } });
  }
  document.querySelectorAll('#scenes button').forEach(b => b.onclick = () => { setScene(b.dataset.s, true); $('sceneHint').hidden = true; });
  $('sceneUndo').onclick = () => { setScene(S.prevScene || 'daily', true); $('sceneHint').hidden = true; };
  setScene(S.scene);
  if ($('sceneChip')) $('sceneChip').onclick = () => { $('sheet').hidden = false; };

  function renderFacts() {
    const ks = Object.keys(S.facts); $('facts').hidden = !ks.length;
    $('factsCount').textContent = ks.length; $('factsHead').textContent = t('known', { n: ks.length });
    $('factsBrief').textContent = ks.map(k => (LABEL[k] || k) + ' ' + S.facts[k]).join(' · ');
    $('factsList').innerHTML = '';
    for (const k of ks) { const li = document.createElement('li'); li.textContent = (LABEL[k] || k) + (L.me === 'zh' ? '：' : ': ') + S.facts[k]; $('factsList').appendChild(li); }
  }
  function sugBtn(zh, es, q) {
    const b = document.createElement('button'); if (q) b.className = 'q';
    b.textContent = (q ? t('followup') : '') + zh; const sm = document.createElement('small'); sm.textContent = es; b.appendChild(sm);
    b.setAttribute('aria-label', t(q ? 'qAria' : 'suggAria', { t: zh }));
    b.onpointerdown = (e) => e.preventDefault();   // keep the input focused so the list stays open
    b.onclick = () => { $('typeBox').value = zh; $('typeBox').focus(); };
    return b;
  }
  function renderSugg(r) {
    const box = $('sugg'); box.innerHTML = '';
    for (const s of r.suggestions || []) box.appendChild(sugBtn(s.zh, s.es));
    if (r.question) box.appendChild(sugBtn(r.question.zh, r.question.es, true));
    setHint();
  }
  // suggestions are hidden by default (small screen): shown only while the text box is focused
  function setHint() {
    const n = $('sugg').children.length;
    $('typeBox').placeholder = n ? t('typePhN', { n }) : ($('typeBox').dataset.base || t('typePh', { me: lname(L.me), them: lname(L.them) }));
    $('typeBox').setAttribute('aria-label', n ? t('typeAriaN', { me: lname(L.me), n }) : t('typeAria', { me: lname(L.me) }));
  }
  $('typeBox').addEventListener('focus', () => document.body.classList.add('typing'));
  $('typeBox').addEventListener('blur', () => setTimeout(() => { if (document.activeElement !== $('typeBox')) document.body.classList.remove('typing'); }, 150));
  function addNote(div, terms) {
    div.querySelectorAll('.note').forEach(n => n.remove());
    for (const t of terms || []) { const n = document.createElement('div'); n.className = 'note'; n.textContent = t.term + (L.me === 'zh' ? '：' : ': ') + t.zh; div.appendChild(n); }
  }
  async function runAssist(id) {
    const n = ++S.reqN, t0 = performance.now();
    try {
      const r = await api('assist', { lines: lines(), scene: S.scene, facts: S.facts, manual: S.manual, me: L.me, them: L.them });
      window.__lastAssistMs = performance.now() - t0;
      if (r.error) return;
      if (r.speaker_name && typeof Speakers !== 'undefined') Speakers.setName(id, r.speaker_name);
      S.facts = r.facts || S.facts; renderFacts();
      const el = document.querySelector(`#captions .line[data-id="${id}"]`); if (el) addNote(el, r.terms);
      if (n !== S.reqN) return;   // a newer turn superseded this one
      if (!S.manual && r.scene && r.scene !== S.scene && S.conv.length >= 2) {
        S.prevScene = S.scene; setScene(r.scene);
        S.hintScene = r.scene; $('sceneHintText').textContent = t('sceneSwitched', { s: NAMES[r.scene] }); $('sceneHint').hidden = false;
      }
      renderSugg(r);
      if (r.goodbye) openEnd();
    } catch (e) { /* captions unaffected */ }
  }

  function onFinal(m) {
    const l = { id: m.id, me: isMine(m.lang), orig: m.es, tr: '' }; S.conv.push(l); S.byId[m.id] = l;
    const el = document.querySelectorAll('#captions .line'); el[el.length - 1].dataset.id = m.id;
  }
  function onTranslation(m, mine) {
    const l = S.byId[m.id]; if (!l) return; l.tr = m.zh;
    if (mine) return;
    clearTimeout(S.timers[m.id]);   // other person's turn finished -> assist + optional read-aloud
    S.timers[m.id] = setTimeout(() => {
      if (l.done) return; l.done = true;
      speakTheirs(l.tr); runAssist(m.id);
    }, m.done ? 150 : 700);
  }

  // 打字输入
  $('typeForm').onsubmit = async (e) => {
    e.preventDefault(); const zh = $('typeBox').value.trim(); if (!zh) return;
    $('typeBox').value = ''; $('sugg').innerHTML = ''; setHint();
    $('typeBox').blur(); document.body.classList.remove('typing');
    const id = 'u' + (++S.typedN);
    const m = { type: 'final', id, es: zh, lang: L.me };
    onMsg({ data: JSON.stringify(m) });
    let es = '';
    try { es = (await api('translate', { text: zh, src: L.me, tgt: L.them, lines: lines() })).text || ''; } catch (_) {}
    onMsg({ data: JSON.stringify({ type: 'translation', id, zh: es || t('trFail'), lang: L.them, done: false }) });
    if (es) { spokenIds.add(id); speak(es); }
  };
  function sayEs(zh, es) {
    const id = 'u' + (++S.typedN);
    onMsg({ data: JSON.stringify({ type: 'final', id, es: zh, lang: L.me }) });
    onMsg({ data: JSON.stringify({ type: 'translation', id, zh: es, lang: L.them, done: false }) });
    spokenIds.add(id); requestSpeak(es);   // explicit tap -> always read aloud
  }

  // 还没问
  async function openEnd() {
    if (!$('endSheet').hidden || !$('sumSheet').hidden) return;
    const r = await api('reminders', { scene: S.scene, facts: S.facts, me: L.me, them: L.them }).catch(() => ({ items: [] }));
    const box = $('missingList'); box.innerHTML = '';
    if (!(r.items || []).length) box.textContent = t('missNone');
    for (const it of r.items || []) {
      const name = (I18N[L.me] || {})['i_' + it.key] || it.zh;
      const b = document.createElement('button'); b.textContent = name;
      const sm = document.createElement('small'); sm.textContent = it.es; b.appendChild(sm);
      b.setAttribute('aria-label', t('missAria', { t: name, them: lname(L.them) }));
      b.onclick = () => { unlockSpeech(); sayEs(t('askPrefix') + name, it.es); b.disabled = true; b.style.opacity = .5; };
      box.appendChild(b);
    }
    $('endSheet').hidden = false;
  }
  $('endBtn').onclick = openEnd;
  $('endClose').onclick = () => { $('endSheet').hidden = true; };

  // 纪要
  const esc = (t) => String(t || '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  function renderSummary(r) {
    S.summary = r;
    let h = `<p>${esc(r.summary)}</p>`;
    if ((r.todos || []).length) h += '<h4>' + esc(tr('todos')) + '</h4>' + r.todos.map(t => `<label><input type="checkbox" aria-label="${esc(tr('doneAria', { t: t.text }))}"> ${esc(t.text)}${t.date ? ' <small>' + esc(t.date + ' ' + (t.time || '')) + '</small>' : ''}</label>`).join('');
    if ((r.terms || []).length) h += '<h4>' + esc(tr('terms')) + '</h4>' + r.terms.map(t => `<div><b>${esc(t.term)}</b>${L.me === 'zh' ? '：' : ': '}${esc(t.zh)}</div>`).join('');
    const fk = Object.keys(S.facts); if (fk.length) h += '<h4>' + esc(tr('facts')) + '</h4>' + fk.map(k => `<div>${esc(LABEL[k] || k)}${L.me === 'zh' ? '：' : ': '}${esc(S.facts[k])}</div>`).join('');
    $('sumBody').innerHTML = h;
  }
  function summaryText() {
    const r = S.summary || {}; let t = tr('sumHead', { s: NAMES[S.scene] }) + `\n${r.summary || ''}\n`;
    if ((r.todos || []).length) t += '\n' + tr('todos') + ':\n' + r.todos.map(x => `- ${x.text}${x.date ? '（' + x.date + ' ' + (x.time || '') + '）' : ''}`).join('\n') + '\n';
    if ((r.terms || []).length) t += '\n' + tr('terms') + ':\n' + r.terms.map(x => `- ${x.term}${L.me === 'zh' ? '：' : ': '}${x.zh}`).join('\n') + '\n';
    return t;
  }
  function ics() {
    const pad = (n) => String(n).padStart(2, '0'), now = new Date();
    const stamp = now.toISOString().replace(/[-:]/g, '').slice(0, 15) + 'Z';
    const ev = (S.summary.todos || []).filter(t => /^\d{4}-\d{2}-\d{2}$/.test(t.date || '')).map((t, i) => {
      const d = t.date.replace(/-/g, ''), tm = /^\d{2}:\d{2}$/.test(t.time || '') ? t.time.replace(':', '') + '00' : null;
      const start = tm ? `DTSTART:${d}T${tm}` : `DTSTART;VALUE=DATE:${d}`;
      return ['BEGIN:VEVENT', `UID:escucha-${stamp}-${i}@escucha.local`, `DTSTAMP:${stamp}`, start, `SUMMARY:${t.text.replace(/[,;\n]/g, ' ')}`, 'END:VEVENT'].join('\r\n');
    });
    return ['BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//Escucha//ZH', ...ev, 'END:VCALENDAR'].join('\r\n');
  }
  $('toSummary').onclick = async () => {
    $('endSheet').hidden = true; $('sumSheet').hidden = false; $('sumBody').textContent = t('sumGen');
    try { const r = await api('summary', { lines: lines(), scene: S.scene, facts: S.facts, me: L.me, them: L.them }); if (r.error) throw new Error(r.error); renderSummary(r); }
    catch (e) { $('sumBody').textContent = t('sumFail', { e: e.message }); }
  };
  $('sumClose').onclick = () => { $('sumSheet').hidden = true; };
  $('sumCopy').onclick = () => { navigator.clipboard && navigator.clipboard.writeText(summaryText()); $('sumCopy').textContent = t('copied'); };
  $('sumIcs').onclick = () => {
    if (!S.summary) return;
    const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([ics()], { type: 'text/calendar' }));
    a.download = 'escucha.ics'; a.click();
  };
  function relabel() { setScene(S.scene); renderFacts(); setHint(); if (!$('sceneHint').hidden && S.hintScene) $('sceneHintText').textContent = t('sceneSwitched', { s: NAMES[S.hintScene] }); }
  relabel();
  return { setHint, relabel, onFinal, onTranslation, runAssist, renderSummary, ics, summaryText, openEnd, setScene, state: S };
})();
