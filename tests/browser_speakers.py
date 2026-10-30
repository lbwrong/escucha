"""浏览器测试：说话人标签（模拟 Meta 的 speaker 事件），标签晚到也能补上；语言判不准的行按说话人归属。
Run: URL=http://127.0.0.1:8799/ python3 tests/browser_speakers.py [截图路径]"""
import os, sys
from playwright.sync_api import sync_playwright
URL = os.environ.get("URL", "http://127.0.0.1:8799/"); shot = sys.argv[1] if len(sys.argv) > 1 else None
with sync_playwright() as p:
    b = p.chromium.launch(executable_path="/usr/bin/google-chrome-stable", args=["--no-sandbox"])
    pg = b.new_page(viewport={"width": 375, "height": 667}, device_scale_factor=2, is_mobile=True, has_touch=True)
    sent = []
    def api(r):
        body = r.request.post_data_json or {}; sent.append((r.request.url, body))
        intro = any("Soy la doctora García" in (l.get("orig") or "") for l in body.get("lines") or [])
        r.fulfill(json={"speaker_name": "García 医生"} if "/api/assist" in r.request.url and intro else {})
    pg.route("**/api/**", api)
    pg.goto(URL); pg.evaluate("localStorage.clear()"); pg.reload(); pg.wait_for_timeout(400)
    M = lambda o: pg.evaluate("o => onMsg({data: JSON.stringify(o)})", o)
    tags = lambda: pg.evaluate("[...document.querySelectorAll('#captions .line:not(.echo)')].map(l => [l.querySelector('.spk') ? l.querySelector('.spk').textContent : '', l.classList.contains('me')])")
    # speaker span arrives BEFORE the caption
    M({"type": "speaker", "label": "A", "startMs": 0, "endMs": 2100})
    M({"type": "final", "id": 1, "es": "Buenos días, ¿en qué le puedo ayudar?", "lang": "es", "startMs": 100, "endMs": 2000})
    M({"type": "translation", "id": 1, "zh": "早上好，有什么可以帮您？", "lang": "zh", "done": True})
    # caption arrives first, tag LATER (Meta lagging) -> caption not delayed, tag fills in
    M({"type": "final", "id": 2, "es": "我想预约", "lang": "zh", "startMs": 2600, "endMs": 3500})
    assert tags()[1] == ["", True], tags()
    M({"type": "speaker", "label": "B", "startMs": 2500, "endMs": 3600})
    M({"type": "translation", "id": 2, "zh": "Quiero pedir cita.", "lang": "es", "done": True})
    M({"type": "final", "id": 3, "es": "Claro, ¿para cuándo?", "lang": "es", "startMs": 4000, "endMs": 5000}); M({"type": "speaker", "label": "A", "startMs": 3900, "endMs": 5100})
    M({"type": "final", "id": 4, "es": "下周二可以吗", "lang": "zh", "startMs": 5500, "endMs": 6400}); M({"type": "speaker", "label": "B", "startMs": 5400, "endMs": 6500})
    M({"type": "final", "id": 5, "es": "Sí, a las diez.", "lang": "es", "startMs": 7000, "endMs": 7900}); M({"type": "speaker", "label": "A", "startMs": 6900, "endMs": 8000})
    pg.wait_for_timeout(100)
    t = tags()
    assert [x[0] for x in t] == ["对方", "我", "对方", "我", "对方"], t
    assert [x[1] for x in t] == [False, True, False, True, False], t
    # ambiguous language (English, not in the zh/es pair) spoken by B (= me so far) -> attributed to me
    M({"type": "final", "id": 6, "es": "OK, thank you", "lang": "en", "startMs": 8500, "endMs": 9200})
    assert tags()[5] == ["", False], tags()   # before the tag: language fallback (theirs)
    M({"type": "speaker", "label": "B", "startMs": 8400, "endMs": 9300}); pg.wait_for_timeout(50)
    assert tags()[5] == ["我", True], tags()
    assert pg.evaluate("__assist.byId[6] ? __assist.byId[6].me : null") in (True, None)
    # tags follow UI language
    pg.evaluate("setLangs('en', 'es')"); pg.wait_for_timeout(100)
    assert tags()[0][0] == "Them" and tags()[1][0] == "Me", tags()
    pg.evaluate("setLangs('zh', 'es')"); pg.wait_for_timeout(100)
    # a second other person (label C) -> 对方 2; raw A/B/C never shown
    M({"type": "final", "id": 7, "es": "Hola, soy la enfermera.", "lang": "es", "startMs": 9800, "endMs": 10800}); M({"type": "speaker", "label": "C", "startMs": 9700, "endMs": 10900})
    pg.wait_for_timeout(50); assert tags()[6][0] == "对方 2", tags()
    # self-introduction -> the assist reply carries speaker_name -> every line of that speaker renamed
    M({"type": "final", "id": 8, "es": "Soy la doctora García.", "lang": "es", "startMs": 11500, "endMs": 12500}); M({"type": "speaker", "label": "A", "startMs": 11400, "endMs": 12600})
    M({"type": "translation", "id": 8, "zh": "我是 García 医生。", "lang": "zh", "done": True})
    pg.wait_for_function("[...document.querySelectorAll('.spk')].some(e => e.textContent === 'García 医生')", timeout=8000)
    t = tags(); assert [x[0] for i, x in enumerate(t) if i in (0, 2, 4, 7)] == ["García 医生"] * 4, t
    assert t[1][0] == "我" and t[6][0] == "对方 2", t
    # tap a tag -> manual rename applies to all that speaker's lines, and wins over later auto names
    pg.once("dialog", lambda d: d.accept("护士 Ana"))
    pg.locator("#captions .line:not(.echo)").nth(6).locator(".spk").click(); pg.wait_for_timeout(50)
    assert tags()[6][0] == "护士 Ana", tags()
    pg.evaluate("Speakers.setName(7, 'X')"); assert tags()[6][0] == "护士 Ana", tags()
    # the summary request carries the names
    sent.clear(); pg.evaluate("fetch('/api/x')")  # no-op warmup
    lines = pg.evaluate("__assist.conv.map(l => l.id)")
    who = pg.evaluate("__assist.conv.filter(l => !l.me).map(l => Speakers.who(l.id))")
    assert "García 医生" in who and "护士 Ana" in who, who
    if shot: pg.screenshot(path=shot)
    # no speaker events at all (Meta off) -> captions work, no tags
    pg.evaluate("localStorage.clear()"); b.close()
print("browser speakers tests OK")
