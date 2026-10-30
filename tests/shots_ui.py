"""iPhone 尺寸截图：python3 tests/shots_ui.py 前缀  (普通/对坐/打字 × 375x667, 390x844)"""
import sys
from playwright.sync_api import sync_playwright
pre = sys.argv[1]
CONV = [("es", "Buenos días, ¿en qué le puedo ayudar?", "早上好，有什么可以帮您？"),
        ("zh", "我想给孩子预约看儿科", "Quiero pedir cita para el pediatra."),
        ("es", "Tiene cita el martes a las 13:30 en Ruzafa.", "您预约在周二 13:30，Ruzafa。")]
with sync_playwright() as p:
    b = p.chromium.launch(executable_path="/usr/bin/google-chrome-stable", args=["--no-sandbox"])
    for w, h in [(375, 667), (390, 844)]:
        pg = b.new_page(viewport={"width": w, "height": h}, device_scale_factor=2, is_mobile=True, has_touch=True)
        pg.goto("http://127.0.0.1:8799/"); pg.evaluate("localStorage.clear()"); pg.reload(); pg.wait_for_timeout(500)
        for i, (l, o, t) in enumerate(CONV, 1):
            pg.evaluate("o => onMsg({data: JSON.stringify(o)})", {"type": "final", "id": i, "es": o, "lang": l})
            pg.evaluate("o => onMsg({data: JSON.stringify(o)})", {"type": "translation", "id": i, "zh": t, "lang": "es" if l == "zh" else "zh", "done": True})
        pg.wait_for_timeout(1500)
        pg.screenshot(path=f"{pre}normal-{w}.png")
        pg.click("#typeBox"); pg.wait_for_timeout(400); pg.screenshot(path=f"{pre}typing-{w}.png")
        pg.evaluate("document.activeElement.blur(); document.body.click()"); pg.wait_for_timeout(200)
        pg.click("#duoBtn"); pg.wait_for_timeout(300); pg.screenshot(path=f"{pre}duo-{w}.png")
        pg.click("#duoBtn"); pg.close()
    b.close()
print("shots ok")
