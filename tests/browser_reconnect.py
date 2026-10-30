"""浏览器端到端：网络/识别服务断线自动重连。假 Soniox + 真服务器 + 真浏览器（假麦克风）。
Run: python3 tests/browser_reconnect.py"""
import asyncio, json, os, subprocess, sys, threading, time, pathlib
from aiohttp import web
import aiohttp
from playwright.sync_api import sync_playwright
ROOT = pathlib.Path(__file__).resolve().parents[1]
FAKE_PORT, APP_PORT = 8811, 8812
state = {"conns": 0, "utt": 0, "drop": False, "dead": False, "ws": None}

async def soniox(req):
    if state["dead"]: return web.Response(status=503)
    w = web.WebSocketResponse(); await w.prepare(req); state["conns"] += 1; state["ws"] = w
    await w.receive()   # config
    async for m in w:
        if state["drop"]:
            state["drop"] = False; await w.close(); break
        if m.type == aiohttp.WSMsgType.BINARY and state.get("say"):
            say = state.pop("say"); state["utt"] += 1
            await w.send_json({"tokens": [{"text": say, "is_final": True, "language": "es", "start_ms": 100, "end_ms": 800},
                                          {"text": "<end>", "is_final": True}]})
            await w.send_json({"tokens": [{"text": "Dice: " + say, "is_final": True, "translation_status": "translation"}]})
    return w

def run_fake():
    async def main():
        app = web.Application(); app.router.add_get("/", soniox)
        r = web.AppRunner(app); await r.setup(); await web.TCPSite(r, "127.0.0.1", FAKE_PORT).start()
        state["runner"] = r; await asyncio.Event().wait()
    loop = asyncio.new_event_loop(); state["loop"] = loop; loop.run_until_complete(main())
threading.Thread(target=run_fake, daemon=True).start(); time.sleep(0.5)
env = dict(os.environ, PORT=str(APP_PORT), PROVIDER="soniox", SONIOX_API_KEY="fake", SONIOX_URL=f"ws://127.0.0.1:{FAKE_PORT}/", META_API_KEY="", DIARIZE="0", ESCUCHA_PASSCODE="")
srv = subprocess.Popen([sys.executable, "server.py"], cwd=ROOT, env=env, stdout=open("/tmp/esc_srv.log","w"), stderr=subprocess.STDOUT)
time.sleep(1.5)
try:
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path="/usr/bin/google-chrome-stable", args=["--no-sandbox", "--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream"])
        pg = b.new_context(permissions=["microphone"]).new_page()
        pg.goto(f"http://127.0.0.1:{APP_PORT}/"); pg.evaluate("localStorage.clear()"); pg.reload(); pg.wait_for_timeout(500)
        assert pg.evaluate("live"), "server should be live"
        status = lambda: pg.inner_text("#status")
        ids = lambda: pg.evaluate("Object.keys(lines).map(Number)")
        state["say"] = "Hola uno"; pg.click("#go"); pg.wait_for_function("Object.keys(lines).length >= 1", timeout=8000)
        assert ids() == [1], ids()
        # 1) 浏览器 <-> 服务器断线：自动重连，字幕编号接着走，旧字幕保留
        pg.evaluate("ws.close()"); pg.wait_for_function("document.querySelector('#status').textContent.includes('Reconnecting') || document.querySelector('#status').textContent.includes('重连')", timeout=3000)
        pg.wait_for_function("document.querySelector('#status').textContent.includes('Soniox') || document.querySelector('#status').textContent.includes('已连接') || document.querySelector('#status').textContent.includes('Connected')", timeout=8000)
        state["say"] = "Hola dos"; pg.wait_for_function("Object.keys(lines).length >= 2", timeout=8000)
        assert ids() == [1, 2], ids(); assert pg.evaluate("running"), "still running"
        print("browser-ws drop: reconnected, ids", ids(), "soniox conns", state["conns"])
        # 2) Soniox 掉线：服务器自动重连并提示
        n0 = state["conns"]; state["drop"] = True
        pg.wait_for_function("window.__x = 1", timeout=500)
        pg.wait_for_function("1", timeout=100)
        deadline = time.time() + 10
        while state["conns"] == n0 and time.time() < deadline: time.sleep(0.2)
        assert state["conns"] > n0, "server did not reconnect to soniox"
        state["say"] = "Hola tres"; pg.wait_for_function("Object.keys(lines).length >= 3", timeout=8000)
        assert ids() == [1, 2, 3], ids(); print("soniox drop: server reconnected, ids", ids())
        # 3) Soniox 彻底连不上：6 次重试后给出明确错误，不是静默
        state["dead"] = True; state["drop"] = True
        pg.wait_for_function("document.querySelector('#status').textContent.includes('⚠️')", timeout=25000)
        print("soniox dead ->", status())
        assert "⚠️" in status() and len(status()) > 10
        b.close()
    print("OK")
finally:
    srv.terminate()
