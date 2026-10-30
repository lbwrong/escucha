// Run: node tests/echo.test.js
const assert = require('assert');
const { overlap, createEchoGuard } = require('../static/echo.js');
assert.ok(overlap('¿Cuánto cuesta la cuenta?', 'cuanto cuesta la cuenta') === 1);
const g = createEchoGuard();
g.started('¿Cuánto cuesta este menú?', 1000);
assert.ok(g.isEcho('cuanto cuesta este menu', 2000), 'echo while speaking');
assert.ok(!g.isEcho('Perdone, ya cerramos la cocina', 2000), 'interruption kept');
g.ended('¿Cuánto cuesta este menú?', 3000);
assert.ok(g.isEcho('Cuánto cuesta este', 4400), 'echo within 1.5 s tail');
assert.ok(!g.isEcho('Cuánto cuesta este', 4600), 'after tail: real speech');
assert.ok(!g.isEcho('', 2000));
console.log('echo tests OK');

// ---- 'interrupt during playback': mic stays on while TTS plays ----
const { createDucker, classify } = require('../static/echo.js');
{
  const guard = createEchoGuard(), duck = createDucker({ duckTo: 0.3, holdMs: 1500 });
  guard.started('¿Me puede traer la cuenta, por favor?', 10000);       // TTS starts playing
  // 1) the phone's own TTS picked up by the mic -> dropped, no ducking
  let r = classify(guard, duck, 'me puede traer la cuenta por favor', 'es', 10500);
  assert.deepStrictEqual(r, { show: false, duck: false }, 'echo dropped');
  // 2) the other person talks over it -> shown/translated, TTS ducked to 30 %
  r = classify(guard, duck, 'Perdone, la cocina ya está cerrada', 'es', 10800);
  assert.deepStrictEqual(r, { show: true, duck: true }, 'interruption shown + duck');
  assert.strictEqual(duck.level(11000), 0.3);
  assert.strictEqual(duck.level(12400), 1, 'restored after 1.5 s quiet');
  // 3) my own Chinese never ducks, still shown
  assert.deepStrictEqual(classify(guard, duck, '好的谢谢', 'zh', 10900), { show: true, duck: false });
  // 4) after playback + tail: normal speech, no ducking
  guard.ended('¿Me puede traer la cuenta, por favor?', 12000);
  assert.deepStrictEqual(classify(guard, duck, 'La cuenta son veinte euros', 'es', 14000), { show: true, duck: false });
  console.log('interrupt-during-playback tests OK');
}
{ // Chinese TTS echo (朗读对方的话给我) is dropped too; my own different Chinese is kept
  const E = require('../static/echo.js'); const g = E.createEchoGuard(), d = E.createDucker();
  g.started('一共二十欧元，女士', 0);
  if (E.classify(g, d, '一共二十欧元女士', 'zh', 100).show) throw new Error('zh echo not dropped');
  if (!E.classify(g, d, '我想用银行卡付款', 'zh', 100).show) throw new Error('my zh dropped');
  console.log('chinese echo tests OK');
}
// v5: other languages — French / Russian echo + generic ducking with myLang
{
  const E = require('../static/echo.js');
  const g = E.createEchoGuard(), d = E.createDucker();
  g.started("Parfait, qu'est-ce que je dois apporter ?", 0);
  if (!g.isEcho("parfait qu'est-ce que je dois apporter", 100)) throw new Error('fr echo');
  g.started('Здравствуйте, принесите счёт', 0);
  if (!g.isEcho('здравствуйте принесите счёт', 100)) throw new Error('ru echo');
  const c = E.classify(g, d, 'Bonjour madame, une question', 'fr', 200, 'en');
  if (!c.show || !c.duck) throw new Error('fr duck');
  if (E.classify(g, d, 'I have a question about it', 'en', 200, 'en').duck) throw new Error('own en no duck');
  if (!E.looksLike('多少钱', 'zh') || E.looksLike('hola', 'zh') || !E.looksLike('hello', 'en')) throw new Error('looksLike');
  console.log('multilang echo tests OK');
}
