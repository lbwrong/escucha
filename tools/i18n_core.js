// t(key, vars): UI text in 我的语言 (L.me); missing key -> English -> key
function t(k, v) {
  let s = (I18N[L.me] || {})[k]; if (s == null) s = I18N.en[k]; if (s == null) s = k;
  return v ? s.replace(/\{(\w+)\}/g, (m, x) => (v[x] != null ? v[x] : m)) : s;
}
// language name shown in my language (Chinese UI keeps the built-in Chinese names)
function lname(c) {
  if (L.me === 'zh') return (LANGS[c] || [c])[0];
  try { const n = new Intl.DisplayNames([L.me], { type: 'language' }).of(c); if (n && n !== c) return n; } catch (_) {}
  return (LANGS[c] || [c, c, c])[2];
}
const shortCode = (c) => (L.me === 'zh' ? LANGS[c][1] : c.toUpperCase());
function applyI18n() {
  document.documentElement.lang = L.me === 'zh' ? 'zh-CN' : L.me;
  document.querySelectorAll('[data-t]').forEach(e => { e.textContent = t(e.dataset.t); });
  document.querySelectorAll('[data-ta]').forEach(e => e.setAttribute('aria-label', t(e.dataset.ta)));
  document.querySelectorAll('#scenes button').forEach(b => b.setAttribute('aria-label', t('sceneAria', { s: t('scene_' + b.dataset.s) })));
}
