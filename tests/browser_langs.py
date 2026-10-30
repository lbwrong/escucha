"""浏览器测试：语言切换面板 en⇄fr（存储、徽章、互换、对坐标签、打字翻译请求带语言）。
Run: URL=http://127.0.0.1:8799/ python3 tests/browser_langs.py [截图前缀]"""
import os, sys, json
from playwright.sync_api import sync_playwright
URL = os.environ.get("URL", "http://127.0.0.1:8799/"); pre = sys.argv[1] if len(sys.argv) > 1 else None
with sync_playwright() as p:
    b = p.chromium.launch(executable_path="/usr/bin/google-chrome-stable", args=["--no-sandbox"])
    pg = b.new_page(viewport={"width": 375, "height": 667}, device_scale_factor=2, is_mobile=True, has_touch=True)
    pg.goto(URL); pg.evaluate("localStorage.clear()"); pg.reload(); pg.wait_for_timeout(400)
    assert pg.title() == "Escucha" and pg.inner_text(".brand") == "Escucha"
    assert pg.inner_text("#langTxt") == "中⇄西", pg.inner_text("#langTxt")
    if pre:
        M = lambda o: pg.evaluate("o => onMsg({data: JSON.stringify(o)})", o)
        for i, (l, o, t) in enumerate([("es", "Buenos días, ¿en qué le puedo ayudar?", "早上好，有什么可以帮您？"), ("zh", "我想预约", "Quiero pedir cita.")], 1):
            M({"type": "final", "id": i, "es": o, "lang": l}); M({"type": "translation", "id": i, "zh": t, "lang": "es" if l == "zh" else "zh", "done": True})
        pg.wait_for_timeout(800); pg.screenshot(path=pre + "normal.png")
    pg.click("#langBtn"); pg.select_option("#langMe", "en"); pg.select_option("#langThem", "fr")
    if pre: pg.screenshot(path=pre + "lang-sheet.png")
    assert pg.inner_text("#langTxt") == "EN⇄FR"
    pg.select_option("#langThem", "en"); assert not pg.is_hidden("#langWarn") and pg.inner_text("#langTxt") == "EN⇄FR"  # same -> rejected
    pg.select_option("#langThem", "fr")
    pg.click("#langSwap"); assert pg.inner_text("#langTxt") == "FR⇄EN"; pg.click("#langSwap"); assert pg.inner_text("#langTxt") == "EN⇄FR"
    pg.click("#langClose")
    pg.reload(); pg.wait_for_timeout(400)
    assert pg.evaluate("[localStorage.langMe, localStorage.langThem, L.me, L.them].join()") == "en,fr,en,fr"
    assert pg.inner_text("#langTxt") == "EN⇄FR" and pg.get_attribute("#typeBox", "placeholder") == "Type in English; it's translated to French and read aloud"
    assert pg.evaluate("$('newThem').textContent") == "Dernier ↓"
    # captions: French line = theirs, English = mine
    M = lambda o: pg.evaluate("o => onMsg({data: JSON.stringify(o)})", o)
    M({"type": "final", "id": 1, "es": "Bonjour, vous avez rendez-vous mardi.", "lang": "fr"}); M({"type": "translation", "id": 1, "zh": "Hello, you have an appointment on Tuesday.", "lang": "en", "done": True})
    M({"type": "final", "id": 2, "es": "What should I bring?", "lang": "en"}); M({"type": "translation", "id": 2, "zh": "Qu'est-ce que je dois apporter ?", "lang": "fr", "done": True})
    pg.wait_for_timeout(300)
    r = pg.evaluate("[...document.querySelectorAll('#captions .line')].map(l => [l.classList.contains('me'), l.querySelector('.zh').textContent])")
    assert r == [[False, "Hello, you have an appointment on Tuesday."], [True, "Qu'est-ce que je dois apporter ?"]], r
    assert pg.evaluate("__assist.conv.map(l => l.me).join()") == "false,true"
    # requests carry the pair
    reqs = []
    pg.on("request", lambda q: reqs.append(json.loads(q.post_data)) if "/api/" in q.url and q.post_data else None)
    pg.fill("#typeBox", "Thanks"); pg.click("#typeSend"); pg.wait_for_timeout(600)
    tr = [q for q in reqs if "src" in q][0]; assert (tr["src"], tr["tgt"]) == ("en", "fr"), tr
    pg.click("#duoBtn"); pg.wait_for_timeout(300)
    top = pg.evaluate("[...$('duoThem').querySelectorAll('.dl .big')].map(e => e.textContent)")
    assert "Bonjour, vous avez rendez-vous mardi." in top and "Qu'est-ce que je dois apporter ?" in top, top
    assert pg.evaluate("$('duoThem').lang") == "fr"
    if pre: pg.screenshot(path=pre + "duo.png")
    pg.evaluate("localStorage.clear()"); b.close()
print("browser langs tests OK")
