"""浏览器测试：场合/小清单/术语/建议/打字/还没问/纪要 + 对坐镜像、上半屏可滚动、反复切换无残留。
需要：假 LLM (tests/fake_llm.py 8798) + 服务器 LLM_BASE_URL=http://127.0.0.1:8798/v1 PORT=8799
Run: URL=http://127.0.0.1:8799/ python3 tests/browser_v2.py [截图前缀]"""
import os, sys, json
from playwright.sync_api import sync_playwright
URL = os.environ.get("URL", "http://127.0.0.1:8799/")
pre = sys.argv[1] if len(sys.argv) > 1 else None
CONV = [("es", "Buenos días, ¿en qué le puedo ayudar?", "早上好，有什么可以帮您？"),
        ("zh", "我想给孩子预约看儿科", "Quiero pedir cita para el pediatra para mi hijo."),
        ("es", "Tiene cita previa el martes 3 de noviembre a las 13:30 en el centro de salud de Ruzafa, consulta 12.", "您预约在 11 月 3 日周二 13:30，Ruzafa 卫生中心 12 号诊室。"),
        ("zh", "好的，谢谢", "Vale, gracias."),
        ("es", "Ese día tiene que traer la tarjeta sanitaria y el libro de vacunas.", "那天要带医保卡和疫苗本。")]
with sync_playwright() as p:
    b = p.chromium.launch(executable_path="/usr/bin/google-chrome-stable", args=["--no-sandbox", "--autoplay-policy=no-user-gesture-required"])
    pg = b.new_page(viewport={"width": 393, "height": 852}, device_scale_factor=3, is_mobile=True, has_touch=True)
    pg.goto(URL); pg.evaluate("localStorage.clear()"); pg.reload(); pg.wait_for_timeout(500)
    M = lambda o: pg.evaluate("o => onMsg({data: JSON.stringify(o)})", o)
    for i, (lang, orig, tr) in enumerate(CONV, 1):
        M({"type": "final", "id": i, "es": orig, "lang": lang})
        M({"type": "translation", "id": i, "zh": tr, "lang": "zh" if lang == "es" else "es", "done": True})
        pg.wait_for_timeout(500)
    pg.wait_for_timeout(800)
    r = pg.evaluate("""() => ({ scene: document.querySelector('#scenes .on').textContent, hint: $('sceneHint').hidden ? '' : $('sceneHintText').textContent,
      facts: $('factsBrief').textContent, notes: [...document.querySelectorAll('.note')].map(e => e.textContent),
      suggHidden: getComputedStyle($('sugg')).display === 'none', ph: $('typeBox').placeholder,
      sugg: [...document.querySelectorAll('#sugg button')].map(e => e.textContent), ms: window.__lastAssistMs,
      labels: [...document.querySelectorAll('button,input,select')].filter(e => !e.getAttribute('aria-label') && !e.closest('#sugg') && !e.closest('#missingList')).map(e => e.id || e.outerHTML.slice(0, 60)) })""")
    print(json.dumps(r, ensure_ascii=False))
    assert r["scene"] == "看医生" and "看医生" in r["hint"]
    assert "13:30" in r["facts"] and "疫苗本" in r["facts"]
    assert any("cita previa" in n for n in r["notes"])
    assert len(r["sugg"]) == 3 and r["sugg"][2].startswith("追问") and "几点" not in r["sugg"][2]
    assert not r["labels"], f"missing aria-label: {r['labels']}"
    assert r["suggHidden"] and "3 条建议" in r["ph"], r
    if pre: pg.screenshot(path=pre + "main.png")
    pg.click("#typeBox"); assert pg.evaluate("getComputedStyle($('sugg')).display") != "none"
    if pre: pg.screenshot(path=pre + "typing.png")
    pg.evaluate("$('typeBox').blur()"); pg.wait_for_timeout(250); assert pg.evaluate("getComputedStyle($('sugg')).display") == "none"
    # manual scene is not overridden
    pg.click("#sceneChip"); pg.click("#scenes button[data-s=school]"); pg.click("#closeSheet")
    M({"type": "final", "id": 6, "es": "¿Algo más?", "lang": "es"}); M({"type": "translation", "id": 6, "zh": "还有别的吗？", "lang": "zh", "done": True})
    pg.wait_for_timeout(600)
    assert pg.evaluate("document.querySelector('#scenes .on').dataset.s") == "school"
    pg.click("#gear"); pg.click("#scenes button[data-s=doctor]")
    assert pg.evaluate("$('sceneChip').textContent") == "看医生"; pg.click("#closeSheet")
    # tap suggestion -> fills box; typed input -> my line + Spanish
    pg.click("#typeBox"); pg.click("#sugg button >> nth=0")
    assert pg.input_value("#typeBox") == "好的，那天我会带上"
    pg.fill("#typeBox", "好的，那天我会带上疫苗本"); pg.click("#typeSend"); pg.wait_for_timeout(500)
    assert pg.evaluate("getComputedStyle($('sugg')).display") == "none", "suggestions hidden after send"
    last = pg.evaluate("[...document.querySelectorAll('#captions .line.me')].pop().innerText")
    assert "Vale, la traeré" in last and "疫苗本" in last, last
    # goodbye -> 还没问
    M({"type": "final", "id": 7, "es": "Muy bien, hasta luego.", "lang": "es"}); M({"type": "translation", "id": 7, "zh": "好的，再见。", "lang": "zh", "done": True})
    pg.wait_for_timeout(800)
    miss = pg.evaluate("$('endSheet').hidden ? null : [...document.querySelectorAll('#missingList button')].map(e => e.innerText)")
    print("还没问", miss)
    assert miss and any("复诊" in m for m in miss) and not any(m.startswith("时间") for m in miss)
    if pre: pg.screenshot(path=pre + "missing.png")
    pg.click("#toSummary"); pg.wait_for_timeout(800)
    s = pg.evaluate("$('sumBody').innerText"); print(s[:120])
    assert "Ruzafa" in s and pg.evaluate("document.querySelectorAll('#sumBody input[type=checkbox]').length") == 2
    ics = pg.evaluate("Assist.ics()"); assert "DTSTART:20261103T133000" in ics
    if pre: pg.screenshot(path=pre + "summary.png")
    pg.click("#sumClose")
    # ---- 对坐: many lines, mirrored, both halves scroll, toggle clean ----
    for i in range(10, 39):
        lang = "es" if i % 3 else "zh"
        M({"type": "final", "id": i, "es": (f"Frase número {i} del médico" if lang == "es" else f"我的第 {i} 句话"), "lang": lang})
        M({"type": "translation", "id": i, "zh": (f"医生的第 {i} 句" if lang == "es" else f"Mi frase número {i}"), "lang": "zh", "done": False})
    for k in range(3):
        pg.click("#duoBtn"); pg.wait_for_timeout(200)
        d = pg.evaluate("""() => { const T = $('duoThem'), E = $('duoMe');
          const topItem = T.querySelector('.dl'), meLast = [...E.querySelectorAll('.dl')].pop();
          return { tScroll: T.scrollHeight > T.clientHeight, eScroll: E.scrollHeight > E.clientHeight,
            tTop: T.scrollTop, eAtEnd: E.scrollHeight - E.scrollTop - E.clientHeight < 5,
            topBig: topItem.querySelector('.big').textContent, topSmall: topItem.querySelector('.small'), topOwn: topItem.classList.contains('own'),
            meBig: meLast.querySelector('.big').textContent, meOwn: meLast.classList.contains('own'),
            nThem: T.querySelectorAll('.dl').length, nMe: E.querySelectorAll('.dl').length } }""")
        assert d["tScroll"] and d["eScroll"] and d["tTop"] == 0 and d["eAtEnd"], d
        assert d["nThem"] == d["nMe"] and d["nThem"] >= 35, d
        if k == 0: assert d["topBig"] == "Frase número 38 del médico" and d["topSmall"] is None and d["topOwn"], d
        if k == 0: assert d["meBig"] == "医生的第 38 句" and not d["meOwn"], d
        # scroll back on the top half: a new line must not yank, '最新' button appears
        pg.evaluate("$('duoThem').scrollTop = 400")
        M({"type": "final", "id": 100 + k, "es": "我想再问一下", "lang": "zh"}); M({"type": "translation", "id": 100 + k, "zh": "Quería preguntar otra cosa", "lang": "es", "done": False})
        st = pg.evaluate("({ t: $('duoThem').scrollTop, btn: !$('newThem').hidden })")
        assert st["t"] > 300 and st["btn"], st
        mine = pg.evaluate("(() => { const x = $('duoThem').querySelector('.dl'); return [x.querySelector('.big').textContent, x.querySelector('.small').textContent, x.classList.contains('own')] })()")
        assert mine == ["Quería preguntar otra cosa", "我想再问一下", False], mine
        pg.click("#newThem"); assert pg.evaluate("$('duoThem').scrollTop") == 0
        if pre and k == 0: pg.wait_for_timeout(100); pg.screenshot(path=pre + "duo.png")
        pg.click("#duoBtn"); pg.wait_for_timeout(200)
        n = pg.evaluate("""() => { const vis = (el) => { const r = el.getBoundingClientRect(); return getComputedStyle(el).display !== 'none' && r.height > 0; };
          const C = $('captions'); return { duoVis: vis($('duo')), forThem: vis($('forThem')), full: vis($('full')),
            capTop: C.getBoundingClientRect().top, capScroll: C.scrollHeight > C.clientHeight,
            lines: C.querySelectorAll('.line:not(.echo)').length } }""")
        assert not n["duoVis"] and not n["forThem"] and not n["full"] and n["capScroll"] and n["capTop"] < 250, n
    print("normal/duo toggle x3 clean")
    b.close()
print("browser v2 tests OK")
