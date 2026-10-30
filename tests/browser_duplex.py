"""Browser test (headless Chrome): interrupt during TTS playback + 对坐模式 + screenshot.
Run: URL=http://127.0.0.1:8799/ python3 tests/browser_duplex.py [screenshot.png]"""
import os, sys, json
from playwright.sync_api import sync_playwright
URL = os.environ.get("URL", "http://127.0.0.1:8799/")
shot = sys.argv[1] if len(sys.argv) > 1 else None
with sync_playwright() as p:
    b = p.chromium.launch(executable_path="/usr/bin/google-chrome-stable", args=["--no-sandbox", "--autoplay-policy=no-user-gesture-required"])
    pg = b.new_page(viewport={"width": 393, "height": 852}, device_scale_factor=3, is_mobile=True, has_touch=True)
    pg.goto(URL); pg.wait_for_timeout(600)
    pg.evaluate("localStorage.duo='0'")
    r = pg.evaluate("""() => {
      ensurePlayCtx();
      const spoken = 'Perdone, ¿me puede traer la cuenta, por favor?';
      echo.started(spoken, Date.now());                       // our TTS is playing
      const M = (o) => onMsg({ data: JSON.stringify(o) });
      M({type:'final', id:1, es:'Quiero pagar, ¿cuánto es?', lang:'es'});
      M({type:'translation', id:1, zh:'我想付钱，多少钱？', lang:'zh', done:true});
      M({type:'final', id:2, es:'me puede traer la cuenta por favor', lang:'es'});   // echo of our TTS
      M({type:'final', id:3, es:'Son veinte euros, señora', lang:'es'});             // interruption
      M({type:'translation', id:3, zh:'一共二十欧元，女士', lang:'zh', done:true});
      const vis = [...document.querySelectorAll('#captions .line:not(.echo) .zh')].map(e => e.textContent);
      return { vis, ducked: window.__ducked || 0, gain: ttsGain.gain.value };
    }""")
    print(json.dumps(r, ensure_ascii=False))
    assert "一共二十欧元，女士" in r["vis"] and len(r["vis"]) == 2, "interruption shown, echo dropped"
    assert r["ducked"] >= 1, "TTS ducked"
    # 对坐模式
    pg.click("#duoBtn")
    pg.evaluate("""() => { echo.ended('Perdone, ¿me puede traer la cuenta, por favor?', 0);
      const M = (o) => onMsg({ data: JSON.stringify(o) });
      M({type:'final', id:4, es:'我下周二上午可以来复诊吗？', lang:'zh'});
      M({type:'translation', id:4, zh:'¿Puedo volver a revisión el martes por la mañana?', lang:'es', done:true});
      M({type:'final', id:5, es:'Sí, a las diez y media. Traiga la tarjeta sanitaria.', lang:'es'});
      M({type:'translation', id:5, zh:'可以，十点半。请带上医保卡。', lang:'zh', done:true}); }""")
    d = pg.evaluate("""() => ({ duo: document.body.classList.contains('duo'), saved: localStorage.duo,
      me: [...document.querySelectorAll('#duoMe .big')].map(e=>e.textContent),
      them: [...document.querySelectorAll('#duoThem .big')].map(e=>e.textContent) })""")
    print(json.dumps(d, ensure_ascii=False))
    assert d["duo"] and d["saved"] == "1"
    assert d["me"][-1] == "可以，十点半。请带上医保卡。" and d["them"][0].startswith("Sí, a las diez")
    assert d["them"][1].startswith("¿Puedo volver") and d["me"][-2].startswith("我下周二")
    pg.wait_for_timeout(300)
    if shot: pg.screenshot(path=shot)
    pg.reload(); pg.wait_for_timeout(500)
    assert pg.evaluate("document.body.classList.contains('duo')"), "toggle remembered"
    b.close()
print("browser duplex + 对坐 tests OK")
