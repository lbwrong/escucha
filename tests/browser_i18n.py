"""浏览器测试：我的语言=英语时，界面（按钮、面板、占位、aria-label、纪要标题…）没有任何中文。
Run: URL=http://127.0.0.1:8799/ python3 tests/browser_i18n.py [截图前缀]"""
import os, sys, json, re
from playwright.sync_api import sync_playwright
URL = os.environ.get("URL", "http://127.0.0.1:8799/"); pre = sys.argv[1] if len(sys.argv) > 1 else None
CJK = re.compile(r"[\u3040-\u30ff\u4e00-\u9fff\uac00-\ud7af]")
ASSIST = {"scene": "doctor", "facts": {"time": "Tuesday 10:30", "place": "Health centre, room 12"}, "terms": [{"term": "cita previa", "zh": "appointment booked in advance"}],
          "suggestions": [{"zh": "Great, I'll bring it.", "es": "Perfecto, lo traeré."}, {"zh": "Do I need to pay anything?", "es": "¿Tengo que pagar algo?"}],
          "question": {"key": "documents", "zh": "What should I bring?", "es": "¿Qué tengo que traer?"}, "goodbye": False}
SUMMARY = {"summary": "Appointment at the health centre on Tuesday at 10:30, room 12. Bring the health card.",
           "todos": [{"text": "Go to the health centre", "date": "2026-11-03", "time": "10:30"}, {"text": "Bring the health card", "date": "", "time": ""}],
           "terms": [{"term": "tarjeta sanitaria", "zh": "health card"}]}
REM = {"items": [{"key": "diagnosis", "zh": "诊断", "es": "¿Qué tiene exactamente?"}, {"key": "medicine", "zh": "药和用量", "es": "¿Qué medicamento tiene que tomar?"}]}
def chrome(pg):
    return pg.evaluate("""() => { const out = [], vis = e => !e.closest('[hidden]') && getComputedStyle(e).display !== 'none';
      const content = '#captions, .note, #duo .half, #sugg, #factsBrief, #factsList, #sumBody p, #sumBody label, #sumBody div, #partial, #ftEs, #ftZh, #fullEs, #fullZh, #missingList small, #langMe, #langThem';
      document.querySelectorAll('[data-t], button, h4, b, .sec, .hint, #status, #mic, #mode, #langTxt, #factsHead, #sceneHintText').forEach(e => {
        if (e.closest(content) && !e.matches('#sumBody h4')) return; if (e.matches('#sugg button, #missingList button')) return;
        out.push(e.id + '|' + (e.childElementCount && e.tagName !== 'BUTTON' ? '' : e.textContent)); });
      document.querySelectorAll('[aria-label]').forEach(e => { if (!e.closest('#sugg, #missingList, #captions')) out.push('aria ' + e.id + '|' + e.getAttribute('aria-label')); });
      document.querySelectorAll('[placeholder]').forEach(e => out.push('ph|' + e.placeholder));
      document.querySelectorAll('#voice option').forEach(e => out.push('voice|' + e.textContent));
      document.querySelectorAll('#captions .note').forEach(e => { if (e.textContent.includes('：')) out.push('note|：'); });
      out.push('lang|' + document.documentElement.lang);
      return out; }""")
def no_cjk(pg, where):
    bad = [x for x in chrome(pg) if CJK.search(x)]
    assert not bad, (where, bad[:12])
with sync_playwright() as p:
    b = p.chromium.launch(executable_path="/usr/bin/google-chrome-stable", args=["--no-sandbox"])
    pg = b.new_page(viewport={"width": 375, "height": 667}, device_scale_factor=2, is_mobile=True, has_touch=True)
    pg.route("**/api/assist", lambda r: r.fulfill(json=ASSIST)); pg.route("**/api/summary", lambda r: r.fulfill(json=SUMMARY))
    pg.route("**/api/reminders", lambda r: r.fulfill(json=REM)); pg.route("**/api/translate", lambda r: r.fulfill(json={"text": "Gracias."}))
    pg.goto(URL); pg.evaluate("localStorage.clear(); localStorage.langMe = 'en'; localStorage.langThem = 'es'"); pg.reload(); pg.wait_for_timeout(500)
    assert pg.evaluate("document.documentElement.lang") == "en" and pg.inner_text("#langTxt") == "EN⇄ES"
    no_cjk(pg, "start")
    M = lambda o: pg.evaluate("o => onMsg({data: JSON.stringify(o)})", o)
    M({"type": "status", "text": "已连接 Soniox 实时双向翻译（西班牙语⇄英语）", "key": "connected", "vars": {"a": "es", "b": "en"}})
    assert pg.inner_text("#status") == "Connected: live two-way translation (Spanish⇄English)", pg.inner_text("#status")
    M({"type": "final", "id": 1, "es": "Tiene cita el martes a las 10:30 en el centro de salud.", "lang": "es"}); M({"type": "translation", "id": 1, "zh": "You have an appointment on Tuesday at 10:30 at the health centre.", "lang": "en", "done": True})
    M({"type": "final", "id": 2, "es": "Great, thank you.", "lang": "en"}); M({"type": "translation", "id": 2, "zh": "Perfecto, gracias.", "lang": "es", "done": True})
    M({"type": "final", "id": 3, "es": "Traiga la tarjeta sanitaria, por favor.", "lang": "es"}); M({"type": "translation", "id": 3, "zh": "Please bring your health card.", "lang": "en", "done": True})
    pg.wait_for_timeout(1500)
    assert pg.inner_text("#sceneChip") == "Doctor" and "Looks like Doctor" in pg.inner_text("#sceneHintText"), pg.inner_text("#sceneHintText")
    assert pg.inner_text("#factsHead").startswith("Known (2)"), pg.inner_text("#factsHead")
    no_cjk(pg, "normal")
    if pre: pg.screenshot(path=pre + "en-normal.png")
    pg.click("#typeBox"); pg.wait_for_timeout(200); assert pg.inner_text("#sugg button.q").startswith("Ask: "); no_cjk(pg, "typing")
    pg.evaluate("$('typeBox').blur()"); pg.wait_for_timeout(250)
    pg.click("#gear"); pg.wait_for_timeout(200); no_cjk(pg, "settings")
    assert pg.inner_text("#scenes button[data-s=gov]") == "Government"
    if pre: pg.screenshot(path=pre + "en-settings.png")
    pg.click("#closeSheet")
    pg.click("#langBtn"); pg.wait_for_timeout(100); no_cjk(pg, "lang sheet")
    opts = pg.evaluate("[...$('langMe').options].map(o => o.textContent)"); assert not any(CJK.search(o) for o in opts if not o.startswith(("Chinese", "Japanese", "Korean"))), opts
    pg.click("#langClose")
    pg.click("#endBtn"); pg.wait_for_timeout(300); no_cjk(pg, "end sheet")
    assert pg.evaluate("[...document.querySelectorAll('#missingList button')].map(b => b.firstChild.textContent)") == ["Diagnosis", "Medicine and dose"]
    pg.click("#toSummary"); pg.wait_for_timeout(400); no_cjk(pg, "summary")
    assert "To-do" in pg.inner_text("#sumBody") and "Known information" in pg.inner_text("#sumBody")
    if pre: pg.screenshot(path=pre + "en-summary.png")
    assert not CJK.search(pg.evaluate("Assist.summaryText()"))
    pg.click("#sumClose"); pg.click("#duoBtn"); pg.wait_for_timeout(200); no_cjk(pg, "duo")
    pg.click("#duoBtn")
    # switch back to Chinese live -> Chinese UI again
    pg.click("#langBtn"); pg.select_option("#langMe", "zh"); pg.wait_for_timeout(100)
    assert pg.inner_text("#langTxt") == "中⇄西" and pg.evaluate("document.documentElement.lang") == "zh-CN" and pg.inner_text("footer #gear span") == "设置"
    pg.evaluate("localStorage.clear()"); b.close()
print("browser i18n (en UI, no CJK) tests OK")
