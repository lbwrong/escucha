// Echo filter: drop recognized Spanish that is just our own TTS playing back through the speaker.
(function (root) {
  function norm(s) {
    const cjk = (s || '').match(/[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]/g);
    if (cjk && cjk.length >= 2) return cjk;   // Chinese / Japanese / Korean: compare by characters
    return (s || '').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '')
      .replace(/[^\p{L}\p{N}\s]/gu, ' ').split(/\s+/).filter(Boolean);   // any script (Latin, Cyrillic, Arabic…)
  }
  // share of the heard words that also appear in the spoken text (0..1)
  function overlap(heard, spoken) {
    const h = norm(heard), sp = new Set(norm(spoken));
    if (!h.length || !sp.size) return 0;
    return h.filter(w => sp.has(w)).length / h.length;
  }
  function createEchoGuard(opts) {
    const o = Object.assign({ tailMs: 1500, threshold: 0.6, keep: 3 }, opts || {});
    const spoken = [];            // {text, until}
    return {
      started(text, now) { spoken.push({ text, until: Infinity }); while (spoken.length > o.keep) spoken.shift(); },
      ended(text, now) { for (const s of spoken) if (s.text === text && s.until === Infinity) s.until = now + o.tailMs; },
      speaking(now) { return spoken.some(s => now <= s.until); },
      isEcho(heard, now) {
        return spoken.some(s => now <= s.until && overlap(heard, s.text) >= o.threshold);
      },
    };
  }
  // Ducking: while our TTS plays, real speech from the other person lowers TTS to duckTo; restores after holdMs quiet.
  function createDucker(opts) {
    const o = Object.assign({ duckTo: 0.3, holdMs: 1500 }, opts || {});
    let last = -Infinity;
    return {
      heard(now) { last = now; return o.duckTo; },
      level(now) { return now - last < o.holdMs ? o.duckTo : 1; },
    };
  }
  // Decide what to do with incoming recognized text (full duplex: mic never stops during TTS).
  // Returns {show: display/translate it?, duck: lower TTS volume now?}
  function classify(guard, ducker, text, lang, now, myLang) {
    if (!text || !text.trim()) return { show: false, duck: false };
    if (guard.isEcho(text, now)) return { show: false, duck: false };  // our own TTS heard back
    const duck = lang !== (myLang || 'zh') && guard.speaking(now) && Echo_norm_len(text) >= 2;
    if (duck) ducker.heard(now);
    return { show: true, duck };
  }
  // rough script check: does this text look like it is written in language `lang`?
  const SCRIPT = { zh: /[\u4e00-\u9fff]/, ja: /[\u3040-\u30ff\u4e00-\u9fff]/, ko: /[\uac00-\ud7af]/, ru: /[\u0400-\u04ff]/, uk: /[\u0400-\u04ff]/,
    ar: /[\u0600-\u06ff]/, hi: /[\u0900-\u097f]/ };
  function looksLike(text, lang) {
    const re = SCRIPT[lang]; if (re) return re.test(text || '');
    return /[a-z]/i.test(text || '') && !Object.values(SCRIPT).some(r => r.test(text || ''));
  }
  function Echo_norm_len(t) { return norm(t).length; }
  const api = { norm, overlap, createEchoGuard, createDucker, classify, looksLike };
  if (typeof module !== 'undefined') module.exports = api; else root.Echo = api;
})(this);
