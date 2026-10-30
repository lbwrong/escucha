// Headless check: page loads, fake mic streams PCM, demo captions appear.
// Run: NODE_PATH=$(npm root -g) node tests/headless_demo.mjs
import { chromium } from 'playwright-core';
const b = await chromium.launch({ executablePath: '/usr/bin/google-chrome-stable',
  args: ['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream', '--no-sandbox'] });
const p = await b.newPage();
await p.goto(process.env.URL || 'http://127.0.0.1:8765/');
await p.waitForTimeout(800);
await p.click('#go');
await p.waitForTimeout(14000);
const r = await p.evaluate(() => ({
  mode: document.getElementById('mode').textContent,
  lines: [...document.querySelectorAll('.line')].map(l => l.querySelector('.zh').textContent),
  mic: document.getElementById('mic').textContent,
  serverMic: window.__serverMicSeconds }));
console.log(JSON.stringify(r, null, 1));
await p.screenshot({ path: 'tests/screenshot.png' });
await b.close();
