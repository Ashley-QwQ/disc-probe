"""Drive-free real HTTP integration capture. Test-only loopback is enabled here.

python tools/verify_news_browser.py --out F:/dp-archive/tmp/faxsource/shots
"""
import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import threading
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from discprobe import news, webui


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", required=True, type=Path)
    p.add_argument("--browser", default="C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe")
    args = p.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="news-capture-", dir=args.out.parent) as temp:
        temp = Path(temp)
        os.environ["TEMP"] = os.environ["TMP"] = str(temp)
        tempfile.tempdir = str(temp)
        requests, results = [], []
        class Mirror(SimpleHTTPRequestHandler):
            def log_message(self, *a):
                pass
            def do_GET(self):
                requests.append(dict(path=self.path, headers=dict(self.headers)))
                super().do_GET()
        mirror = ThreadingHTTPServer(("127.0.0.1", 0), partial(Mirror, directory=str(ROOT / "news")))
        mirror_thread = threading.Thread(target=mirror.serve_forever, daemon=True)
        mirror_thread.start()
        state = {"case": "network", "cache": temp / "network-cache"}
        real_news, real_asset = news.get_news, news.get_asset
        def paper(sources=None):
            source = f"http://127.0.0.1:{mirror.server_port}/" + ("news.json" if state["case"] == "network" else "missing.json")
            answer = real_news(sources or [source], cache=state["cache"], _test_http=True)
            results.append({k: v for k, v in answer.items() if k != "paper"})
            return answer
        def asset(path, source=None):
            return real_asset(path, source, cache=state["cache"], _test_http=True)
        style = re.search(r"<style>([\s\S]*?)</style>", (ROOT / "discprobe/web/home/index.html").read_text(encoding="utf-8"))[1]
        html = '''<!doctype html><html data-theme="paper"><meta charset="utf-8"><base href="/home/">
<style>STYLE</style><body><header class="top"><button id="back" hidden>back</button><span id="wm-ver">v0.1.2.1</span></header>
<section id="lobby"><button id="fax-in-lobby">fax</button></section><pre id="result" hidden>PENDING</pre>
<script type="module">
const q=s=>document.querySelector(s), params=new URL(location.href).searchParams;
document.documentElement.dataset.theme=params.get('theme');
localStorage.clear();localStorage.setItem('dp-fax-seen','1');
const api={$:id=>document.getElementById(id),lang:()=> 'zh',reduce:true,toLobby(){}};
try {
const fax=await import('./faxnews.js');
await fax.start(api,{from:q('#fax-in-lobby')});
for(let i=0;i<1000&&!q('.fx-mast');i++)await new Promise(r=>setTimeout(r,20));
if(!q('.fx-mast'))throw Error('paper missing: '+q('.fx-paper')?.textContent);
const image=q('.fx-art img');
if(image&&!image.complete)await new Promise(r=>{image.onload=r;image.onerror=r});
if(!image?.naturalWidth)throw Error('art did not load');
if(params.get('case')==='bundled'&&!q('.fx-note')?.textContent.includes('自带的样张'))throw Error('sample note missing');
if(params.get('case')==='network'&&q('.fx-note')?.textContent.includes('没连上'))throw Error('unexpected fallback');
document.getElementById('result').textContent='PASS '+params.get('case')+' '+params.get('theme');
}catch(e){document.getElementById('result').textContent='FAIL '+e.stack}
</script></body></html>'''.replace("STYLE", style).encode("utf-8")
        class Handler(webui.Handler):
            def do_GET(self):
                if self.path.startswith("/news-capture.html"):
                    self._allowed()
                    self._send(200, html, "text/html; charset=utf-8")
                else:
                    super().do_GET()
        server = webui.Server(SimpleNamespace(close=lambda: None), 0)
        server.RequestHandlerClass = Handler
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with patch.object(news, "get_news", paper), patch.object(news, "get_asset", asset):
                for case in ("network", "bundled"):
                    state["case"], state["cache"] = case, temp / (case + "-cache")
                    for theme in ("paper", "dark"):
                        name = f"{case}-{theme}"
                        profile = temp / (name + "-profile")
                        result = subprocess.run([args.browser, "--headless=new", "--disable-gpu", "--no-sandbox",
                            "--no-first-run", "--no-default-browser-check", "--user-data-dir=" + str(profile),
                            "--window-size=1440,1000", "--force-device-scale-factor=1", "--hide-scrollbars",
                            "--virtual-time-budget=40000", "--dump-dom", "--screenshot=" + str(args.out / (name + ".png")),
                            f"http://127.0.0.1:{server.server_port}/news-capture.html?theme={theme}&case={case}"],
                            capture_output=True, timeout=60)
                        dom = result.stdout.decode("utf-8", errors="replace")
                        report = re.search(r'<pre id="result"[^>]*>([\s\S]*?)</pre>', dom)
                        (args.out / (name + ".html")).write_text(dom, encoding="utf-8")
                        (args.out / (name + ".stderr")).write_bytes(result.stderr)
                        assert result.returncode == 0 and report and report[1].startswith("PASS"), dom[-2500:]
                        from PIL import Image
                        with Image.open(args.out / (name + ".png")) as im:
                            assert im.size == (1440, 1000), im.size
                        print(report[1], flush=True)
                        # All generated profiles are children of the verified temp directory.
                        assert profile.resolve().is_relative_to(temp.resolve())
                        shutil.rmtree(profile, ignore_errors=True)
        finally:
            server.shutdown()
            server.server_close()
            mirror.shutdown()
            mirror.server_close()
            thread.join()
            mirror_thread.join()
        (args.out / "core-results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        (args.out / "mirror-requests.json").write_text(json.dumps(requests, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
