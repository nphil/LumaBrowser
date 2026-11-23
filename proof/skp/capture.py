#!/usr/bin/env python3
"""R2 picture round trip: Chromium-side experiments (see docs/research/skp-roundtrip.md).

Drives stock /usr/bin/chromium over DevTools (pipe or websocket), serves local test pages,
and runs the capture methods, layer, input, extension and snapshot experiments.
Artifacts go under $LB_SKP_OUT (default: ./out next to this file, git-ignored).

    python3 capture.py site            # write test pages + assets, print the file list
    python3 capture.py methods         # 3 capture methods x pages, 20 calls each
    python3 capture.py layers          # LayerTree layer fields on the mix page
    python3 capture.py input           # scroll / click / wheel / insertText / beginFrame
    python3 capture.py range           # how far beyond the viewport printToSkPicture records (long article)
    python3 capture.py transport       # --remote-debugging-pipe vs websocket: startup + call latency
    python3 capture.py tracebuf        # tracing categories / buffer sizes / delivery modes: which picture snapshots arrive
    python3 capture.py ext             # AdGuard MV3 A/B (--ext DIR, unpacked chrome-mv3.zip of AdGuard 5.5.4)
    python3 capture.py snap            # layer SKPs + manifest + screenshot, input of replay/ (skp-replay)
    python3 capture.py all

Options: --calls N (timed repetitions), --pages a,b, --transport pipe|ws, --ext DIR, --only A,B,C,D, --wait S.
"""
import argparse
import base64
import collections
import http.server
import json
import os
import random
import re
import select
import shutil
import signal
import statistics
import struct
import subprocess
import sys
import threading
import time

CHROMIUM = os.environ.get("LB_CHROMIUM", "/usr/bin/chromium")
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.environ.get("LB_SKP_OUT") or os.path.join(HERE, "out")
VIEW_W, VIEW_H = 1280, 720

# Live pages (reachable from this host; recorded in the report with the run date).
LIVE_ARTICLE = "https://en.wikipedia.org/wiki/Linux"
LIVE_NEWS = "https://www.bbc.com/news"


class CDPError(Exception):
    pass


# --------------------------------------------------------------------------------------
# DevTools transports and a small synchronous client
# --------------------------------------------------------------------------------------
class PipeConn:
    """--remote-debugging-pipe: NUL-terminated JSON on fd 3 (to Chromium) and fd 4 (from it)."""

    def __init__(self, wfd, rfd):
        self.wfd, self.rfd, self.buf = wfd, rfd, bytearray()

    def send(self, text):
        data = text.encode() + b"\0"
        while data:
            n = os.write(self.wfd, data)
            data = data[n:]

    def recv(self, timeout):
        while True:
            i = self.buf.find(b"\0")
            if i >= 0:
                msg = bytes(self.buf[:i])
                del self.buf[: i + 1]
                return msg.decode()
            ready, _, _ = select.select([self.rfd], [], [], timeout)
            if not ready:
                return None
            chunk = os.read(self.rfd, 1 << 20)
            if not chunk:
                raise CDPError("pipe closed by Chromium")
            self.buf += chunk

    def close(self):
        for fd in (self.wfd, self.rfd):
            try:
                os.close(fd)
            except OSError:
                pass


class WsConn:
    def __init__(self, url):
        from websockets.sync.client import connect

        self.ws = connect(url, max_size=None, compression=None, ping_interval=None, open_timeout=30)

    def send(self, text):
        self.ws.send(text)

    def recv(self, timeout):
        try:
            return self.ws.recv(timeout=timeout)
        except TimeoutError:
            return None

    def close(self):
        try:
            self.ws.close()
        except Exception:
            pass


BASE_FLAGS = [
    "--headless=new",
    "--no-sandbox",  # the host runs everything as root
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-dev-shm-usage",  # /dev/shm is 64 MB here
    "--hide-scrollbars",  # layout width == viewport width
    "--force-color-profile=srgb",
    "--window-size=%d,%d" % (VIEW_W, VIEW_H + 80),
    "--enable-gpu-benchmarking",  # exposes chrome.gpuBenchmarking.printToSkPicture
]


class Browser:
    """One headless Chromium process and its browser-level DevTools connection."""

    def __init__(self, name, flags=(), transport="pipe", base_flags=None, log_dir=None):
        self.name, self.transport = name, transport
        self.profile = os.path.join(OUT, "profiles", "%s-%d" % (name, os.getpid()))
        shutil.rmtree(self.profile, ignore_errors=True)
        os.makedirs(self.profile)
        log_dir = log_dir or os.path.join(OUT, "logs")
        os.makedirs(log_dir, exist_ok=True)
        self.log = open(os.path.join(log_dir, "chromium-%s.log" % name), "wb")
        args = [CHROMIUM] + list(BASE_FLAGS if base_flags is None else base_flags)
        args += ["--user-data-dir=" + self.profile] + list(flags)
        if transport == "pipe":
            args.append("--remote-debugging-pipe")
            c2b_r, c2b_w = os.pipe()
            b2c_r, b2c_w = os.pipe()

            def pre():
                os.dup2(c2b_r, 3)
                os.dup2(b2c_w, 4)

            self.proc = subprocess.Popen(
                args + ["about:blank"], stdin=subprocess.DEVNULL, stdout=self.log, stderr=subprocess.STDOUT,
                start_new_session=True, close_fds=False, preexec_fn=pre,
            )
            os.close(c2b_r)
            os.close(b2c_w)
            self.conn = PipeConn(c2b_w, b2c_r)
        else:
            args.append("--remote-debugging-port=0")
            self.proc = subprocess.Popen(
                args + ["about:blank"], stdin=subprocess.DEVNULL, stdout=self.log, stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            self.conn = WsConn(self._ws_url())
        self.args = args
        self.id = 0
        self.events = collections.deque()
        self.responses = {}
        self.version = self.send("Browser.getVersion")

    def _ws_url(self, timeout=60):
        path = os.path.join(self.profile, "DevToolsActivePort")
        end = time.time() + timeout
        while time.time() < end:
            if self.proc.poll() is not None:
                raise CDPError("Chromium exited early (see logs)")
            if os.path.exists(path):
                lines = open(path).read().split("\n")
                if len(lines) >= 2 and lines[1]:
                    return "ws://127.0.0.1:%s%s" % (lines[0], lines[1])
            time.sleep(0.05)
        raise CDPError("timed out waiting for DevToolsActivePort")

    # -- protocol plumbing ---------------------------------------------------------------
    def _take(self, timeout):
        raw = self.conn.recv(timeout)
        if raw is None:
            return False
        m = json.loads(raw)
        if "id" in m:
            self.responses[m["id"]] = m
        else:
            m["_t"] = time.perf_counter()
            self.events.append(m)
        return True

    def send(self, method, params=None, session=None, timeout=120):
        self.id += 1
        mid = self.id
        msg = {"id": mid, "method": method, "params": params or {}}
        if session:
            msg["sessionId"] = session
        self.conn.send(json.dumps(msg))
        end = time.time() + timeout
        while mid not in self.responses:
            left = end - time.time()
            if left <= 0:
                raise CDPError("timeout waiting for %s" % method)
            self._take(min(left, 1.0))
        m = self.responses.pop(mid)
        if "error" in m:
            raise CDPError("%s: %s" % (method, json.dumps(m["error"])))
        return m.get("result", {})

    def pump(self, seconds):
        end = time.time() + seconds
        while time.time() < end:
            self._take(min(0.1, max(0.0, end - time.time())))

    def wait_event(self, method, session=None, timeout=30, pred=None):
        end = time.time() + timeout
        while True:
            for i, m in enumerate(self.events):
                if m.get("method") == method and (session is None or m.get("sessionId") == session) and (
                    pred is None or pred(m.get("params", {}))
                ):
                    del self.events[i]
                    return m
            left = end - time.time()
            if left <= 0:
                raise CDPError("timeout waiting for event " + method)
            self._take(min(left, 0.5))

    def drain(self, method=None, session=None):
        keep, out = collections.deque(), []
        for m in self.events:
            if (method is None or m.get("method") == method) and (session is None or m.get("sessionId") == session):
                out.append(m)
            else:
                keep.append(m)
        self.events = keep
        return out

    def new_page(self, url="about:blank"):
        tid = self.send("Target.createTarget", {"url": url})["targetId"]
        sid = self.send("Target.attachToTarget", {"targetId": tid, "flatten": True})["sessionId"]
        return Page(self, tid, sid)

    def close(self):
        """Stop only this browser's own process group (other Chromium instances may be running)."""
        try:
            self.conn.close()
        except Exception:
            pass
        try:
            os.killpg(self.proc.pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            pass
        try:
            self.proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(self.proc.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
            self.proc.wait()
        self.log.close()
        shutil.rmtree(self.profile, ignore_errors=True)


class Page:
    def __init__(self, browser, target_id, session):
        self.b, self.tid, self.sid = browser, target_id, session

    def send(self, method, params=None, timeout=120):
        return self.b.send(method, params, self.sid, timeout)

    def eval(self, expr, await_promise=False, timeout=120):
        r = self.send(
            "Runtime.evaluate",
            {"expression": expr, "returnByValue": True, "awaitPromise": await_promise}, timeout,
        )
        if "exceptionDetails" in r:
            raise CDPError("eval failed: %s" % json.dumps(r["exceptionDetails"])[:400])
        return r["result"].get("value")

    def wait_event(self, method, timeout=30, pred=None):
        return self.b.wait_event(method, self.sid, timeout, pred)

    def drain(self, method=None):
        return self.b.drain(method, self.sid)

    def frames(self, n=2):
        """Wait n animation frames in the page."""
        self.eval(
            "new Promise(r=>{let n=%d;const f=()=>--n?requestAnimationFrame(f):r(1);requestAnimationFrame(f)})" % n,
            True,
        )

    def setup(self, dsf=1, w=VIEW_W, h=VIEW_H):
        for d in ("Page", "Runtime", "Network"):
            self.send(d + ".enable")
        self.send("Page.setLifecycleEventsEnabled", {"enabled": True})
        self.send(
            "Emulation.setDeviceMetricsOverride",
            {"width": w, "height": h, "deviceScaleFactor": dsf, "mobile": False},
        )

    def goto(self, url, settle=1.0, timeout=60, net_idle=False):
        self.send("Page.navigate", {"url": url})
        self.wait_event("Page.loadEventFired", timeout)
        if net_idle:
            try:
                self.wait_event("Page.lifecycleEvent", timeout=15, pred=lambda p: p.get("name") == "networkIdle")
            except CDPError:
                pass
        self.eval("document.fonts.ready.then(()=>1)", True, timeout)
        self.frames(3)
        time.sleep(settle)
        self.frames(2)


def cpu_load():
    return open("/proc/loadavg").read().split()[:3]


def med(xs):
    return round(statistics.median(xs), 3) if xs else None


def stats(xs):
    xs = list(xs)
    if not xs:
        return {}
    return {"n": len(xs), "median": med(xs), "min": round(min(xs), 3), "max": round(max(xs), 3),
            "mean": round(statistics.fmean(xs), 3)}


# --------------------------------------------------------------------------------------
# Local test site
# --------------------------------------------------------------------------------------
WORDS = (
    "the of and to in is that for it as was with be by on not he this are or his from at which but have an had "
    "they you were their one all we can her has there been if more when will would who so no she other its may "
    "these two time up about out than into only over new some could them see other then now like our also after "
    "first system software kernel memory driver window browser page layer picture glyph raster frame tile scroll "
    "network protocol server client packet latency render paint compose texture shader pixel colour curve path "
    "engine library version release build module thread process buffer cache stream codec format record replay"
).split()


def sentence(rnd, n):
    ws = [rnd.choice(WORDS) for _ in range(n)]
    ws[0] = ws[0].capitalize()
    return " ".join(ws) + "."


def paragraph(rnd, sentences=5):
    return " ".join(sentence(rnd, rnd.randint(8, 18)) for _ in range(sentences))


def make_photo(path, w, h, seed, fmt="JPEG"):
    from PIL import Image, ImageChops, ImageDraw, ImageFilter

    rnd = random.Random(seed)
    top = tuple(rnd.randrange(40, 230) for _ in range(3))
    bot = tuple(rnd.randrange(20, 200) for _ in range(3))
    grad = Image.linear_gradient("L").resize((w, h))
    im = Image.composite(Image.new("RGB", (w, h), bot), Image.new("RGB", (w, h), top), grad)
    layer = Image.new("RGB", (w, h))
    d = ImageDraw.Draw(layer)
    for _ in range(26):
        x, y = rnd.randrange(-w // 4, w), rnd.randrange(-h // 4, h)
        r = rnd.randrange(w // 12, w // 3)
        d.ellipse([x, y, x + r, y + r * rnd.uniform(0.5, 1.2)], fill=tuple(rnd.randrange(0, 255) for _ in range(3)))
    layer = layer.filter(ImageFilter.GaussianBlur(max(4, w // 90)))
    im = Image.blend(im, layer, 0.55)
    noise = Image.effect_noise((w, h), 22).convert("RGB")
    im = ImageChops.add(im, noise, scale=2.0, offset=-64)
    kw = {"quality": 84} if fmt == "JPEG" else ({"quality": 80} if fmt == "WEBP" else {})
    im.save(path, fmt, **kw)


def font_source():
    for p in ("/usr/share/fonts/truetype/liberation/LiberationSans-BoldItalic.ttf",
              "/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf"):
        if os.path.exists(p):
            return p
    raise SystemExit("no Liberation TTF found for the local web font")


def article_html():
    rnd = random.Random(11)
    parts = []
    for s in range(24):
        parts.append("<h2>%s</h2>" % sentence(rnd, 5).rstrip("."))
        for p in range(6):
            parts.append("<p>%s <a href='#x'>%s</a> %s</p>" % (paragraph(rnd, 3), sentence(rnd, 3).rstrip("."), paragraph(rnd, 2)))
        if s % 4 == 1:
            parts.append("<figure><img src='/img/photo%d.jpg' width='720' height='405'><figcaption>%s</figcaption></figure>"
                         % (1 + s % 6, sentence(rnd, 9)))
    return """<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Long article</title><style>
html,body{margin:0}body{font:18px/1.65 "Liberation Serif",Georgia,serif;color:#1d1d1d;background:#fff}
article{width:720px;margin:0 auto;padding:24px 0 80px}h1{font:700 44px/1.15 "Liberation Sans",sans-serif;margin:24px 0}
h2{font:700 26px/1.3 "Liberation Sans",sans-serif;margin:36px 0 10px}p{margin:0 0 16px}a{color:#0b57d0}
figure{margin:20px 0}figcaption{font:14px "Liberation Sans";color:#555}</style></head><body><article>
<h1>A long article for picture capture</h1>%s</article></body></html>""" % "\n".join(parts)


def news_html():
    rnd = random.Random(23)
    cards = []
    for i in range(12):
        cards.append("""<article class="c"><img src="/img/news%d.jpg" width="400" height="225"><h3>%s</h3><p>%s</p>
<span class="m">%d min ago · %s</span></article>""" % (i + 1, sentence(rnd, 9).rstrip("."), sentence(rnd, 20), 4 + i * 7, rnd.choice(WORDS).capitalize()))
    nav = "".join("<a href='#'>%s</a>" % w.capitalize() for w in WORDS[40:52])
    return """<!doctype html><html lang="en"><head><meta charset="utf-8"><title>News front page</title><style>
@font-face{font-family:LBWeb;src:url(/fonts/lbweb.ttf) format("truetype");font-weight:700}
html,body{margin:0}body{font:16px/1.45 "Liberation Sans",Arial,sans-serif;background:#f6f6f4;color:#1a1a1a}
header{background:#b80000;color:#fff;padding:14px 32px;display:flex;align-items:center;gap:28px}
header b{font:700 40px LBWeb,serif}header a{color:#fff;text-decoration:none;font-weight:700}
.hero{display:grid;grid-template-columns:2fr 1fr;gap:24px;padding:24px 32px}.hero img{width:100%%;height:auto;border-radius:6px}
.hero h1{font:700 44px/1.1 LBWeb,serif;margin:0 0 12px}.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:24px;padding:0 32px 48px}
.c{background:#fff;border-radius:8px;overflow:hidden;box-shadow:0 1px 4px rgba(0,0,0,.2);padding-bottom:12px}
.c img{width:100%%;height:auto;display:block}.c h3{font:700 22px/1.2 LBWeb,serif;margin:12px 14px 6px}.c p{margin:0 14px 8px;color:#444}
.m{margin:0 14px;color:#888;font-size:13px}</style></head><body>
<header><b>LumaNews 📰</b>%s</header>
<section class="hero"><div><img src="/img/news-hero.jpg" width="960" height="540"></div>
<div><h1>%s</h1><p>%s</p><p>%s</p></div></section><section class="grid">%s</section></body></html>""" % (
        nav, sentence(rnd, 11).rstrip("."), paragraph(rnd, 3), paragraph(rnd, 3), "".join(cards))


def mix_html():
    rnd = random.Random(5)
    scroll_rows = "".join("<div>Inner scroller line %d — %s</div>" % (i, sentence(rnd, 6)) for i in range(40))
    filler = "".join("<p>%s</p>" % paragraph(rnd, 4) for _ in range(14))
    return """<!doctype html><html lang="en"><head><meta charset="utf-8"><title>mix</title><style>
@font-face{font-family:LBWeb;src:url(/fonts/lbweb.ttf) format("truetype");font-weight:700}
*{box-sizing:border-box}html,body{margin:0}
body{font:16px/1.5 "Liberation Sans",Arial,sans-serif;color:#222;background:#f3efe6}
#hdr{position:fixed;top:0;left:0;right:0;height:56px;background:#12355b;color:#fff;z-index:10;display:flex;align-items:center;
 padding:0 24px;font:700 24px LBWeb,sans-serif;box-shadow:0 2px 10px rgba(0,0,0,.45)}
#hdr small{margin-left:auto;font:400 14px "Liberation Sans"}
main{width:1000px;margin:0 auto;padding-top:72px}h2{font:700 30px LBWeb,serif;margin:28px 0 8px}
#wrap{height:700px;border-left:4px solid #bbb;padding-left:12px}
#sticky{position:sticky;top:64px;background:#ffd54a;padding:10px 14px;border-radius:8px;box-shadow:0 1px 6px rgba(0,0,0,.3);width:420px;font-weight:700}
#scroller{width:520px;height:220px;overflow:auto;border:2px solid #345;background:#fff;margin:12px 0}
#scroller div{height:30px;line-height:30px;padding:0 10px;border-bottom:1px solid #eee}
#opa{position:relative;height:150px;margin:12px 0;background:repeating-linear-gradient(90deg,#c33 0 20px,#fff 20px 40px)}
#opa .g{position:absolute;left:30px;top:20px;width:420px;height:110px;opacity:.55;background:#16a;color:#fff;border-radius:12px;padding:10px}
#opa .g b{position:absolute;right:-40px;bottom:-30px;width:160px;height:90px;background:#e91;border-radius:50%%}
.rc{width:300px;height:200px;border-radius:36px;overflow:hidden;display:inline-block;margin:6px;vertical-align:top}
.rc img{width:100%%;height:100%%;object-fit:cover}.circ{width:200px;height:200px;border-radius:50%%;margin:6px;vertical-align:top;object-fit:cover}
.emoji{font-size:34px}#web{font:700 30px LBWeb,serif}
#spin{display:inline-block;width:90px;height:90px;background:#2a9d8f;will-change:transform;animation:s 4s linear infinite}
@keyframes s{to{transform:rotate(360deg)}}
#wc{display:inline-block;vertical-align:top;will-change:opacity;opacity:.7;background:#264653;color:#fff;padding:8px;width:220px}
#filler p{margin:0 0 12px}</style></head><body>
<div id="hdr">LumaBrowser mix test — fixed 😀<small id="stat">scroll 0</small></div><main>
<h2>Sticky</h2><div id="wrap"><div id="sticky">Sticky bar (top:64px)</div><p>%s</p></div>
<h2>Inner scroller</h2><div id="scroller">%s</div>
<h2>Opacity group</h2><div id="opa"><div class="g">Group at 55%% opacity<b></b></div></div>
<h2>Rounded clipped image</h2><div class="rc"><img src="/img/photo1.jpg"></div><img class="circ" src="/img/photo2.jpg">
<div class="rc"><img src="/img/photo3.webp"></div>
<h2>Web font</h2><p id="web">Web font — The quick brown fox jumps over the lazy dog</p>
<h2>Emoji</h2><p class="emoji">😀 🚀 🌍 👩‍💻 🇳🇴 🎉</p>
<h2>Controls</h2><button id="btn">Click me</button> <span id="clicks">0</span>
<input id="txt" value="" placeholder="type here"> <span id="val"></span>
<h2>Composited layers</h2><div id="spin"></div> <div id="wc">will-change: opacity, .7</div>
<h2>Inline SVG</h2><svg width="240" height="80" viewBox="0 0 240 80"><rect x="2" y="2" width="236" height="76" rx="14" fill="#fde" stroke="#a36" stroke-width="3"/>
<text x="20" y="48" font-size="26" fill="#603" font-family="Liberation Serif">SVG text</text></svg>
<div id="filler">%s</div></main>
<script>
const ev=window.__ev={scroll:0,innerscroll:0,wheel:0,click:0,input:0,last:''};
const note=(k,extra)=>{ev[k]++;if(window.__lbEvent)window.__lbEvent(JSON.stringify({k,t:performance.now(),y:scrollY,extra}))};
addEventListener('scroll',()=>{note('scroll');document.getElementById('stat').textContent='scroll '+Math.round(scrollY)},{passive:true});
document.getElementById('scroller').addEventListener('scroll',e=>note('innerscroll',e.target.scrollTop),{passive:true});
addEventListener('wheel',e=>note('wheel',e.deltaY),{passive:true});
document.getElementById('btn').addEventListener('click',()=>{note('click');document.getElementById('clicks').textContent=ev.click});
document.getElementById('txt').addEventListener('input',e=>{note('input');document.getElementById('val').textContent=e.target.value});
</script></body></html>""" % (paragraph(rnd, 6), scroll_rows, filler)


def ad_html():
    """Page that requests well-known ad/tracker URLs (for the extension A/B)."""
    ads = [
        "https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js",
        "https://securepubads.g.doubleclick.net/tag/js/gpt.js",
        "https://www.googletagservices.com/tag/js/gpt.js",
        "https://ads.pubmatic.com/AdServer/js/showad.js",
        "https://c.amazon-adsystem.com/aax2/apstag.js",
    ]
    scripts = "".join("<script src='%s' async></script>" % u for u in ads)
    return "<!doctype html><meta charset=utf-8><title>ads</title><body><h1>ad test</h1>%s</body>" % scripts


def write_site(root):
    os.makedirs(os.path.join(root, "img"), exist_ok=True)
    os.makedirs(os.path.join(root, "fonts"), exist_ok=True)
    shutil.copy(font_source(), os.path.join(root, "fonts", "lbweb.ttf"))
    for i in range(1, 7):
        make_photo(os.path.join(root, "img", "photo%d.jpg" % i), 1280, 720, i)
    make_photo(os.path.join(root, "img", "photo3.webp"), 800, 450, 33, "WEBP")
    make_photo(os.path.join(root, "img", "news-hero.jpg"), 960, 540, 100)
    for i in range(1, 13):
        make_photo(os.path.join(root, "img", "news%d.jpg" % i), 800, 450, 200 + i)
    pages = {"article.html": article_html(), "news.html": news_html(), "mix.html": mix_html(), "ads.html": ad_html()}
    for name, html in pages.items():
        with open(os.path.join(root, name), "w") as f:
            f.write(html)
    return sorted(os.listdir(root))


class Site:
    """Threaded local HTTP server for the generated pages."""

    def __init__(self, root):
        self.hits = []
        hits = self.hits

        class H(http.server.SimpleHTTPRequestHandler):
            def __init__(self, *a, **k):
                super().__init__(*a, directory=root, **k)

            def log_message(self, fmt, *args):
                hits.append(self.path)

        self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.port = self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def url(self, name):
        return "http://127.0.0.1:%d/%s" % (self.port, name)

    def stop(self):
        self.httpd.shutdown()


def ensure_site():
    root = os.path.join(OUT, "site")
    if not os.path.exists(os.path.join(root, "mix.html")):
        write_site(root)
    return root


# --------------------------------------------------------------------------------------
# SKP container parsing (stock Chromium output, Skia picture version 110)
# --------------------------------------------------------------------------------------
def rp(buf, pos):
    """Skia packed uint: <=0xFD literal, 0xFE + u16, 0xFF + u32."""
    b = buf[pos]
    if b <= 0xFD:
        return b, pos + 1
    if b == 0xFE:
        return struct.unpack_from("<H", buf, pos + 1)[0], pos + 3
    return struct.unpack_from("<I", buf, pos + 1)[0], pos + 5


def fourcc(v):
    return struct.pack("<I", v)[::-1].decode("latin1")


def parse_typeface(buf, pos):
    """SkFontDescriptor record: returns (info dict, next position)."""
    info = {"offset": pos, "factory": None, "family": None, "index": 0}
    style, pos = rp(buf, pos)
    info["weight"] = style >> 16
    while True:
        i, pos = rp(buf, pos)
        if i == 0xFF:
            break
        if i in (0x01, 0x04, 0x06):
            n, pos = rp(buf, pos)
            s = bytes(buf[pos:pos + n]).decode("utf-8", "replace")
            pos += n
            info[{1: "family", 4: "full", 6: "postscript"}[i]] = s
        elif i in (0x10, 0x11, 0x12, 0x13):
            pos += 4
        elif i == 0xFA:
            n, pos = rp(buf, pos)
            pos += 8 * n
            info["variation_axes"] = n
        elif i == 0xF9:
            n, pos = rp(buf, pos)
            for _ in range(n):
                _, pos = rp(buf, pos)
                pos += 4
        elif i in (0xFD, 0xF8, 0xFC):
            v, pos = rp(buf, pos)
            if i == 0xFC:
                info["factory"] = fourcc(v)
            elif i == 0xFD:
                info["index"] = v
        elif i in (0xF6, 0xF7):
            pass
        else:
            raise ValueError("unknown font descriptor id 0x%x" % i)
    n, pos = rp(buf, pos)
    info["data_bytes"] = n
    info["data_offset"] = pos
    return info, pos + n


def skp_parse(buf):
    """Walk the top-level chunks. Returns header, chunk list, typefaces (with embedded size), nested pictures."""
    assert buf[:8] == b"skiapict", "not an SKP"
    ver = struct.unpack_from("<I", buf, 8)[0]
    cull = struct.unpack_from("<4f", buf, 12)
    out = {"bytes": len(buf), "version": ver, "cull": cull, "chunks": [], "typefaces": [], "nested": 0}

    def walk(pos, depth):
        while pos + 4 <= len(buf):
            tag = fourcc(struct.unpack_from("<I", buf, pos)[0])
            pos += 4
            if tag == "eof ":
                out["chunks"].append((depth, tag, pos - 4, 0))
                return pos
            n = struct.unpack_from("<I", buf, pos)[0]
            pos += 4
            if tag in ("read", "fact", "aray"):
                out["chunks"].append((depth, tag, pos - 8, n))
                pos += n
            elif tag == "tpfc":
                start = pos
                for _ in range(n):
                    tf, pos = parse_typeface(buf, pos)
                    tf["depth"] = depth
                    out["typefaces"].append(tf)
                out["chunks"].append((depth, tag, start - 8, pos - start))
            elif tag == "pctr":
                out["chunks"].append((depth, tag, pos - 8, n))
                for _ in range(n):
                    out["nested"] += 1
                    pos = walk(pos, depth + 1)
            else:
                raise ValueError("unknown chunk %r at %d" % (tag, pos - 8))
        return pos

    walk(29, 0)
    return out


IMAGE_MAGIC = {
    "jpeg": re.compile(rb"\xff\xd8\xff[\xe0\xe1\xdb\xc0\xc2\xee]"),
    "png": re.compile(rb"\x89PNG\r\n\x1a\n"),
    "webp": re.compile(rb"RIFF....WEBP", re.S),
}


def skp_images(buf, info):
    """Locate encoded image payloads in the 'aray' buffer by magic number; returns [(kind, offset)]."""
    found = []
    for depth, tag, off, n in info["chunks"]:
        if tag != "aray":
            continue
        seg = bytes(buf[off + 8: off + 8 + n])
        for kind, rx in IMAGE_MAGIC.items():
            for m in rx.finditer(seg):
                found.append((kind, off + 8 + m.start()))
    return sorted(found, key=lambda x: x[1])


def summarize_skp(path):
    buf = open(path, "rb").read()
    info = skp_parse(buf)
    imgs = skp_images(buf, info)
    return {
        "file": os.path.basename(path), "bytes": len(buf), "version": info["version"],
        "cull": [round(x, 2) for x in info["cull"]], "nested_pictures": info["nested"],
        "typefaces": [{k: tf.get(k) for k in ("family", "factory", "data_bytes", "weight")} for tf in info["typefaces"]],
        "typeface_bytes": sum(tf["data_bytes"] for tf in info["typefaces"]),
        "image_payloads": collections.Counter(k for k, _ in imgs),
        "chunks": [(t, n) for d, t, o, n in info["chunks"] if d == 0],
    }


# --------------------------------------------------------------------------------------
# Experiments
# --------------------------------------------------------------------------------------
def results_dir():
    d = os.path.join(OUT, "results")
    os.makedirs(d, exist_ok=True)
    return d


def save_result(name, obj):
    path = os.path.join(results_dir(), name + ".json")
    with open(path, "w") as f:
        json.dump(obj, f, indent=1, default=str)
    return path


def dir_bytes(d):
    return sum(os.path.getsize(os.path.join(d, f)) for f in os.listdir(d))


def png_dims(buf, off):
    """IHDR width/height of a PNG that starts at buf[off]."""
    w, h = struct.unpack_from(">II", buf, off + 16)
    return w, h


def analyze_pictures(d):
    """Per-layer summary of a printToSkPicture directory."""
    out = []
    for f in sorted(os.listdir(d), key=lambda x: int(re.findall(r"\d+", x)[0])):
        buf = open(os.path.join(d, f), "rb").read()
        info = skp_parse(buf)
        imgs = skp_images(buf, info)
        pngs = [png_dims(buf, o) for k, o in imgs if k == "png"]
        out.append({
            "file": f, "bytes": len(buf), "version": info["version"], "cull": [round(x, 1) for x in info["cull"]],
            "typefaces": [(t["family"], t["factory"], t["data_bytes"]) for t in info["typefaces"]],
            "typeface_bytes": sum(t["data_bytes"] for t in info["typefaces"]),
            "images": dict(collections.Counter(k for k, _ in imgs)), "png_dims": pngs,
            "nested": info["nested"],
        })
    return out


PAGE_SPECS = [
    ("mix", "local", "mix.html"),
    ("article", "local", "article.html"),
    ("news", "local", "news.html"),
    ("wikipedia", "live", LIVE_ARTICLE),
    ("bbc", "live", LIVE_NEWS),
]

DIRTY_JS = """((n)=>{const r=document.documentElement;r.style.outline='1px solid rgba(0,0,0,0.0'+(n%%9+1)+')';
const s=document.getElementById('stat');if(s)s.textContent='tick '+n;
const w=document.getElementById('web');if(w)w.textContent='Web font run '+n;})(%d)"""


def open_page(b, site, spec, dsf=1, settle=1.0):
    name, kind, target = spec
    p = b.new_page()
    p.setup(dsf=dsf)
    url = site.url(target) if kind == "local" else target
    p.goto(url, settle=settle if kind == "local" else 3.0, net_idle=(kind == "live"))
    return p, url


def dirty(p, n):
    p.eval(DIRTY_JS % n)
    p.frames(3)


def print_skp(p, d):
    shutil.rmtree(d, ignore_errors=True)
    os.makedirs(d)
    t = time.perf_counter()
    inner = p.eval("(()=>{const t=performance.now();chrome.gpuBenchmarking.printToSkPicture(%s);return performance.now()-t})()" % json.dumps(d))
    return inner, (time.perf_counter() - t) * 1000


def method_pictures(b, p, name, calls, keep_dir):
    """chrome.gpuBenchmarking.printToSkPicture: first call kept for analysis, then `calls` timed calls."""
    base = os.path.join(OUT, "tmp", "pts-" + name)
    shutil.rmtree(base, ignore_errors=True)
    os.makedirs(base)
    inner0, outer0 = print_skp(p, keep_dir)
    layers = analyze_pictures(keep_dir)
    inner, outer, sizes = [], [], []
    for i in range(calls):
        d = os.path.join(base, str(i))
        a, o = print_skp(p, d)
        inner.append(a)
        outer.append(o)
        sizes.append(dir_bytes(d))
        shutil.rmtree(d, ignore_errors=True)
    return {
        "first_call_ms": round(inner0, 1), "inner_ms": stats(inner), "outer_ms": stats(outer), "bytes": stats(sizes),
        "layers": len(layers), "layer_files": layers,
    }


def read_stream(b, handle, chunk=1 << 20):
    parts = []
    while True:
        r = b.send("IO.read", {"handle": handle, "size": chunk})
        parts.append(r["data"] if not r.get("base64Encoded") else base64.b64decode(r["data"]).decode("utf-8", "replace"))
        if r.get("eof"):
            break
    b.send("IO.close", {"handle": handle})
    return "".join(parts)


def trace_call(b, p, cats, n, trigger=True):
    t0 = time.perf_counter()
    b.send("Tracing.start", {
        "traceConfig": {"recordMode": "recordAsMuchAsPossible", "includedCategories": cats},
        "transferMode": "ReturnAsStream", "streamFormat": "json"})
    if trigger:
        dirty(p, n)
    b.send("Tracing.end")
    ev = b.wait_event("Tracing.tracingComplete", timeout=180)
    blob = read_stream(b, ev["params"]["stream"])
    dt = (time.perf_counter() - t0) * 1000
    return blob, dt, bool(ev["params"].get("dataLossOccurred"))


def trace_snapshots(blob):
    """Picture snapshots in a trace: list of (decoded skp bytes, layer_rect)."""
    out = []
    for e in json.loads(blob)["traceEvents"]:
        if e.get("name") == "cc::DisplayItemList:snapshot" and e.get("args"):
            snap = e["args"]["snapshot"]
            out.append((base64.b64decode(snap["skp64"]), snap["params"].get("layer_rect")))
    return out


def method_tracing(b, p, name, calls):
    res = {}
    for label, cats in (("display_items", ["disabled-by-default-cc.debug.display_items"]),
                        ("picture", ["disabled-by-default-cc.debug.picture"]),
                        ("timeline_picture", ["disabled-by-default-devtools.timeline.layers",
                                              "disabled-by-default-devtools.timeline.picture"])):
        ms, tb, nsn, skb, loss = [], [], [], [], []
        k = calls if label == "display_items" else min(calls, 5)
        for i in range(k):
            blob, dt, lost = trace_call(b, p, cats, i)
            snaps = trace_snapshots(blob)
            ms.append(dt)
            tb.append(len(blob))
            nsn.append(len(snaps))
            skb.append(sum(len(s) for s, _ in snaps))
            loss.append(lost)
        res[label] = {"calls": k, "wall_ms": stats(ms), "trace_bytes": stats(tb), "picture_snapshots": stats(nsn),
                      "picture_bytes": stats(skb), "data_loss_calls": sum(loss)}
    return res


def method_layertree(b, p, name, calls):
    p.send("LayerTree.enable")
    dirty(p, 1)
    b.pump(0.3)
    evs = b.drain("LayerTree.layerTreeDidChange", p.sid)
    layers = [L for L in evs[-1]["params"]["layers"] if L.get("drawsContent") and L["width"] > 0] if evs else []
    usable, nopic = [], []  # an iframe layer answers makeSnapshot with "Layer does not produce picture"
    for L in layers:
        try:
            p.send("LayerTree.releaseSnapshot", {"snapshotId": p.send("LayerTree.makeSnapshot", {"layerId": L["layerId"]})["snapshotId"]})
            usable.append(L)
        except CDPError as e:
            nopic.append({"layerId": L["layerId"], "size": [L["width"], L["height"]], "error": str(e)[-70:]})
    layers = usable
    log_ms, log_bytes, rep_ms, rep_bytes = [], [], [], []
    per_layer = []
    for i in range(calls):
        t = time.perf_counter()
        nbytes = 0
        for L in layers:
            sid = p.send("LayerTree.makeSnapshot", {"layerId": L["layerId"]})["snapshotId"]
            cl = p.send("LayerTree.snapshotCommandLog", {"snapshotId": sid})["commandLog"]
            nbytes += len(json.dumps(cl))
            p.send("LayerTree.releaseSnapshot", {"snapshotId": sid})
            if i == 0:
                per_layer.append({"layerId": L["layerId"], "size": [L["width"], L["height"]], "commands": len(cl),
                                  "methods": dict(collections.Counter(c["method"] for c in cl).most_common(6))})
        log_ms.append((time.perf_counter() - t) * 1000)
        log_bytes.append(nbytes)
    for i in range(min(calls, 5)):
        t = time.perf_counter()
        nbytes = 0
        for L in layers:
            sid = p.send("LayerTree.makeSnapshot", {"layerId": L["layerId"]})["snapshotId"]
            r = p.send("LayerTree.replaySnapshot", {"snapshotId": sid, "scale": 1.0})
            nbytes += len(r["dataURL"])
            p.send("LayerTree.releaseSnapshot", {"snapshotId": sid})
        rep_ms.append((time.perf_counter() - t) * 1000)
        rep_bytes.append(nbytes)
    p.send("LayerTree.disable")
    return {"drawing_layers": len(layers), "command_log": {"wall_ms": stats(log_ms), "json_bytes": stats(log_bytes)},
            "replay_png": {"calls": len(rep_ms), "wall_ms": stats(rep_ms), "dataurl_bytes": stats(rep_bytes)},
            "layers": per_layer, "layers_without_picture": nopic}


TRACE_DISPLAY = "disabled-by-default-cc.debug.display_items"
TRACE_PICTURE = "disabled-by-default-cc.debug.picture"


def trace_variant(b, p, n, cat, buffer_kb, transfer):
    """One trace with a category / buffer size / transfer mode; returns (snapshot details, trace size, wall ms, data loss)."""
    cfg = {"recordMode": "recordAsMuchAsPossible", "includedCategories": [cat]}
    if buffer_kb:
        cfg["traceBufferSizeInKb"] = buffer_kb
    params = {"traceConfig": cfg, "transferMode": transfer}
    if transfer == "ReturnAsStream":
        params["streamFormat"] = "json"
    b.drain("Tracing.dataCollected")
    t0 = time.perf_counter()
    b.send("Tracing.start", params)
    dirty(p, n)
    b.send("Tracing.end")
    ev = b.wait_event("Tracing.tracingComplete", timeout=240)
    if transfer == "ReturnAsStream":
        blob = read_stream(b, ev["params"]["stream"])
        events, size = json.loads(blob)["traceEvents"], len(blob)
    else:
        events = [e for m in b.drain("Tracing.dataCollected") for e in m["params"]["value"]]
        size = len(json.dumps(events))
    dt = (time.perf_counter() - t0) * 1000
    rows = []
    for e in events:
        if e.get("name") == "cc::DisplayItemList:snapshot" and e.get("args"):
            s = e["args"]["snapshot"]
            buf = base64.b64decode(s["skp64"])
            info = skp_parse(buf)
            rows.append({"bytes": len(buf), "layer_rect": s["params"].get("layer_rect"), "version": info["version"], "cull": [round(x) for x in info["cull"]],
                         "typeface_bytes": sum(t["data_bytes"] for t in info["typefaces"]),
                         "images": dict(collections.Counter(k for k, _ in skp_images(buf, info)))})
    return rows, size, dt, bool(ev["params"].get("dataLossOccurred"))


def exp_tracebuf(args):
    """Which tracing category / buffer size / delivery mode brings picture snapshots through, and what do they contain?"""
    ensure_site()
    site = Site(os.path.join(OUT, "site"))
    b = Browser("tracebuf", transport=args.transport)
    out = {"chromium": b.version["product"], "load": cpu_load(), "pages": {}}
    variants = (("display_items stream default-buffer", TRACE_DISPLAY, None, "ReturnAsStream"),
                ("display_items stream 1GB-buffer", TRACE_DISPLAY, 1048576, "ReturnAsStream"),
                ("display_items events 1GB-buffer", TRACE_DISPLAY, 1048576, "ReportEvents"),
                ("picture stream default-buffer", TRACE_PICTURE, None, "ReturnAsStream"),
                ("picture stream 1GB-buffer", TRACE_PICTURE, 1048576, "ReturnAsStream"))
    try:
        for spec in PAGE_SPECS:
            if spec[0] not in (args.pages or ["mix", "article"]):
                continue
            p, url = open_page(b, site, spec)
            res = {}
            for label, cat, kb, transfer in variants:
                rows = [trace_variant(b, p, i, cat, kb, transfer) for i in range(args.calls)]
                with_pics = [r for r in rows if r[0]]
                res[label] = {"calls": len(rows), "wall_ms": stats([r[2] for r in rows]), "trace_bytes": stats([r[1] for r in rows]),
                              "snapshots": stats([len(r[0]) for r in rows]), "picture_bytes": stats([sum(s["bytes"] for s in r[0]) for r in rows]),
                              "data_loss_calls": sum(r[3] for r in rows), "calls_with_snapshots": len(with_pics),
                              "snapshot_details": with_pics[-1][0] if with_pics else []}
                print("%s %-36s %s" % (spec[0], label, json.dumps({k: res[label][k] for k in ("calls_with_snapshots", "data_loss_calls")}) + " snaps=" +
                                       json.dumps([(s["bytes"], s["typeface_bytes"], s["images"]) for s in res[label]["snapshot_details"]])[:200]), flush=True)
            out["pages"][spec[0]] = res
            b.send("Target.closeTarget", {"targetId": p.tid})
    finally:
        save_result("tracebuf", out)
        b.close()
        site.stop()
    return out


def exp_methods(args):
    ensure_site()
    site = Site(os.path.join(OUT, "site"))
    b = Browser("methods", transport=args.transport)
    out = {"chromium": b.version["product"], "transport": args.transport, "load_before": cpu_load(), "pages": {}}
    try:
        for spec in PAGE_SPECS:
            if args.pages and spec[0] not in args.pages:
                continue
            p, url = open_page(b, site, spec)
            info = p.eval("[document.documentElement.scrollHeight, document.documentElement.scrollWidth]")
            keep = os.path.join(OUT, "tmp", "keep-" + spec[0])
            print("== %s %s doc=%s" % (spec[0], url, info), flush=True)
            r = {"url": url, "doc": info}
            r["printToSkPicture"] = method_pictures(b, p, spec[0], args.calls, keep)
            print("   printToSkPicture", json.dumps({k: r["printToSkPicture"][k] for k in ("layers", "inner_ms", "bytes")}), flush=True)
            r["layertree"] = method_layertree(b, p, spec[0], args.calls)
            print("   LayerTree", json.dumps({k: r["layertree"][k] for k in ("drawing_layers", "command_log")}), flush=True)
            r["tracing"] = method_tracing(b, p, spec[0], args.calls)
            print("   tracing", json.dumps(r["tracing"]["display_items"]), flush=True)
            out["pages"][spec[0]] = r
            b.send("Target.closeTarget", {"targetId": p.tid})
            save_result("methods", out)
    finally:
        out["load_after"] = cpu_load()
        save_result("methods", out)
        b.close()
        site.stop()
    return out


# ---- layer metadata -----------------------------------------------------------------
def layer_events(b, p, tweak):
    """Force a repaint and return the newest LayerTree.layerTreeDidChange layer list."""
    b.drain("LayerTree.layerTreeDidChange", p.sid)
    dirty(p, tweak)
    b.pump(0.4)
    evs = b.drain("LayerTree.layerTreeDidChange", p.sid)
    return evs[-1]["params"]["layers"] if evs else []


def trace_metadata(blob):
    """Per-layer cc.debug snapshot + property trees out of a `disabled-by-default-cc.debug` trace."""
    snap, trees = None, None
    for e in json.loads(blob)["traceEvents"]:
        n = e.get("name")
        if n == "LayerTreeHostImpl:snapshot" and e.get("args"):
            snap = e["args"]["snapshot"]
        elif n == "PropertyTreeLayerListDelegate::UpdatePropertyTreesIfNeeded_ReceivedPropertyTrees" and e.get("args"):
            trees = e["args"]["property_trees"]
    return snap, trees


def exp_layers(args):
    ensure_site()
    site = Site(os.path.join(OUT, "site"))
    b = Browser("layers", transport=args.transport)
    out = {"chromium": b.version["product"], "load": cpu_load()}
    try:
        p, url = open_page(b, site, ("mix", "local", "mix.html"))
        p.send("LayerTree.enable")
        p.eval("document.getAnimations().forEach(a=>a.pause())")
        rects_js = ("(()=>{const o={};for(const id of ['hdr','sticky','scroller','spin','wc','opa','web']){"
                    "const r=document.getElementById(id).getBoundingClientRect();o[id]=[r.left,r.top,r.width,r.height]}return o})()")
        states = {}
        for label, (sy, st) in {"scroll0": (0, 0), "scroll300": (300, 0), "scroll1200_inner100": (1200, 100)}.items():
            p.eval("scrollTo(0,%d);document.getElementById('scroller').scrollTop=%d" % (sy, st))
            p.frames(4)
            time.sleep(0.4)
            lay = layer_events(b, p, 3 + len(states))
            states[label] = {"scrollY": p.eval("scrollY"), "dom_rects": p.eval(rects_js), "layers": lay}
        out["states"] = states
        fields = collections.Counter()
        for L in states["scroll300"]["layers"]:
            fields.update(L.keys())
        out["layertree_fields"] = dict(fields)
        out["parent_ids"] = sorted({L.get("parentLayerId") for L in states["scroll300"]["layers"]}, key=str)
        # tracing: per-layer cc.debug snapshot and property trees (one start/stop cycle, repaint inside)
        t_ms = []
        for i in range(args.calls):
            blob, dt, lost = trace_call(b, p, ["disabled-by-default-cc.debug"], 20 + i)
            t_ms.append(dt)
            if i == 0:
                snap, trees = trace_metadata(blob)
                out["trace_cc_debug"] = {"trace_bytes": len(blob), "data_loss": lost}
                lay0 = snap["active_tree"]["layers"] if snap else []
                out["trace_cc_debug"]["layer_keys"] = sorted(lay0[0].keys()) if lay0 else []
                out["trace_cc_debug"]["layers"] = lay0
                out["trace_cc_debug"]["property_trees"] = trees
                out["trace_cc_debug"]["property_tree_keys"] = {k: (sorted(v["nodes"][0].keys()) if isinstance(v, dict) and v.get("nodes") else None)
                                                               for k, v in (trees or {}).items() if isinstance(v, dict)}
        out["trace_cc_debug"]["wall_ms"] = stats(t_ms)
        p.send("LayerTree.disable")
    finally:
        save_result("layers", out)
        b.close()
        site.stop()
    return out


# ---- input and scroll -----------------------------------------------------------------
def binding_event(p, kinds, timeout=5):
    """Wait for a page-side __lbEvent of one of `kinds`; returns (arrival time, payload)."""
    m = p.wait_event("Runtime.bindingCalled", timeout, pred=lambda q: json.loads(q["payload"])["k"] in kinds)
    return m["_t"], json.loads(m["params"]["payload"])


def center(p, sel):
    return p.eval("(()=>{const r=document.querySelector(%s).getBoundingClientRect();return [r.left+r.width/2,r.top+r.height/2]})()" % json.dumps(sel))


def exp_input(args):
    ensure_site()
    site = Site(os.path.join(OUT, "site"))
    b = Browser("input", transport=args.transport)
    out = {"chromium": b.version["product"], "transport": args.transport, "load": cpu_load()}
    n = args.calls
    try:
        p, url = open_page(b, site, ("mix", "local", "mix.html"))
        p.send("Runtime.addBinding", {"name": "__lbEvent"})
        p.eval("document.getAnimations().forEach(a=>a.pause())")

        # 1. absolute scroll offset through Runtime.evaluate
        lat, ok = [], 0
        for i in range(n):
            y = 400 + 100 * (i % 7)
            p.eval("scrollTo(0,0)")
            p.frames(2)
            p.drain("Runtime.bindingCalled")
            t0 = time.perf_counter()
            p.eval("scrollTo(0,%d)" % y)
            t1, ev = binding_event(p, ("scroll",))
            lat.append((t1 - t0) * 1000)
            ok += int(abs(ev["y"] - y) < 1)
        out["scrollTo_eval"] = {"latency_ms": stats(lat), "scroll_listener_fired": ok, "trials": n}

        # 2. wheel events through Input.dispatchMouseEvent
        lat, disp, dys = [], [], []
        for i in range(n):
            p.eval("scrollTo(0,0)")
            p.frames(2)
            p.drain("Runtime.bindingCalled")
            t0 = time.perf_counter()
            p.send("Input.dispatchMouseEvent", {"type": "mouseWheel", "x": 900, "y": 400, "deltaX": 0, "deltaY": 120})
            disp.append((time.perf_counter() - t0) * 1000)
            t1, ev = binding_event(p, ("scroll",))
            lat.append((t1 - t0) * 1000)
            time.sleep(0.25)
            dys.append(p.eval("scrollY"))
        out["wheel_dispatchMouseEvent"] = {"dispatch_return_ms": stats(disp), "to_scroll_event_ms": stats(lat),
                                           "scrollY_after_deltaY_120": stats(dys), "wheel_events_in_page": p.eval("__ev.wheel")}

        # 3. synthesizeScrollGesture and gpuBenchmarking.smoothScrollBy
        res = {}
        for label, call in {
            "synthesizeScrollGesture_mouse": lambda: p.send("Input.synthesizeScrollGesture", {"x": 900, "y": 400, "yDistance": -300, "gestureSourceType": "mouse", "speed": 4000}),
            "synthesizeScrollGesture_touch": lambda: p.send("Input.synthesizeScrollGesture", {"x": 900, "y": 400, "yDistance": -300, "gestureSourceType": "touch", "speed": 4000}),
        }.items():
            ts, ys, cnt = [], [], []
            for i in range(min(n, 10)):
                p.eval("scrollTo(0,0)")
                p.frames(2)
                before = p.eval("__ev.scroll")
                t0 = time.perf_counter()
                try:
                    call()
                except CDPError as e:
                    res[label] = {"error": str(e)[:200]}
                    break
                ts.append((time.perf_counter() - t0) * 1000)
                time.sleep(0.2)
                ys.append(p.eval("scrollY"))
                cnt.append(p.eval("__ev.scroll") - before)
            else:
                res[label] = {"call_ms": stats(ts), "scrollY": stats(ys), "scroll_events": stats(cnt)}
        ts, ys = [], []
        for i in range(min(n, 10)):
            p.eval("scrollTo(0,0)")
            p.frames(2)
            t0 = time.perf_counter()
            p.eval("new Promise(r=>chrome.gpuBenchmarking.smoothScrollBy(300,()=>r(1),900,400))", True)
            ts.append((time.perf_counter() - t0) * 1000)
            ys.append(p.eval("scrollY"))
        res["gpuBenchmarking_smoothScrollBy_300"] = {"call_ms": stats(ts), "scrollY": stats(ys)}
        out["gestures"] = res

        # 4. inner scroller (wheel over it), scrollTop applied directly
        p.eval("scrollTo(0,500)")
        p.frames(3)
        x, y = center(p, "#scroller")
        p.drain("Runtime.bindingCalled")
        t0 = time.perf_counter()
        p.send("Input.dispatchMouseEvent", {"type": "mouseWheel", "x": x, "y": y, "deltaX": 0, "deltaY": 90})
        t1, ev = binding_event(p, ("innerscroll",))
        time.sleep(0.2)
        out["inner_scroller"] = {"wheel_to_innerscroll_ms": round((t1 - t0) * 1000, 1), "scrollTop": p.eval("document.getElementById('scroller').scrollTop"),
                                 "window_scrollY_unchanged": p.eval("scrollY") == 500}
        p.eval("document.getElementById('scroller').scrollTop=250")
        t1, ev = binding_event(p, ("innerscroll",))
        out["inner_scroller"]["scrollTop_assign_fires_listener"] = ev["extra"] == 250

        # 5. click on a button, text input
        p.eval("document.getElementById('btn').scrollIntoView({block:'center'})")
        p.frames(3)
        x, y = center(p, "#btn")
        lat = []
        before = p.eval("__ev.click")
        for i in range(min(n, 10)):
            p.drain("Runtime.bindingCalled")
            t0 = time.perf_counter()
            p.send("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x, "y": y})
            p.send("Input.dispatchMouseEvent", {"type": "mousePressed", "x": x, "y": y, "button": "left", "buttons": 1, "clickCount": 1})
            p.send("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": x, "y": y, "button": "left", "buttons": 0, "clickCount": 1})
            t1, ev = binding_event(p, ("click",))
            lat.append((t1 - t0) * 1000)
        out["click"] = {"press_release_to_click_ms": stats(lat), "clicks_counted": p.eval("__ev.click") - before, "sent": min(n, 10)}
        x, y = center(p, "#txt")
        p.send("Input.dispatchMouseEvent", {"type": "mousePressed", "x": x, "y": y, "button": "left", "buttons": 1, "clickCount": 1})
        p.send("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": x, "y": y, "button": "left", "buttons": 0, "clickCount": 1})
        text = "héllo wörld \U0001F600"
        p.drain("Runtime.bindingCalled")
        t0 = time.perf_counter()
        p.send("Input.insertText", {"text": text})
        t1, ev = binding_event(p, ("input",))
        out["insertText"] = {"to_input_event_ms": round((t1 - t0) * 1000, 1), "value": p.eval("document.getElementById('txt').value"),
                             "matches": p.eval("document.getElementById('txt').value") == text,
                             "focused": p.eval("document.activeElement.id")}
        # key events for comparison
        p.send("Input.dispatchKeyEvent", {"type": "keyDown", "key": "a", "code": "KeyA", "text": "a"})
        p.send("Input.dispatchKeyEvent", {"type": "keyUp", "key": "a", "code": "KeyA"})
        out["insertText"]["after_key_a"] = p.eval("document.getElementById('txt').value")[-3:]

        # 6. HeadlessExperimental.beginFrame (page session and browser session)
        he = {}
        for label, call in {
            "page_enable": lambda: p.send("HeadlessExperimental.enable"),
            "page_beginFrame": lambda: p.send("HeadlessExperimental.beginFrame", {"frameTimeTicks": 1000, "interval": 16.666}),
            "browser_beginFrame": lambda: b.send("HeadlessExperimental.beginFrame", {}),
        }.items():
            try:
                he[label] = {"ok": call()}
            except CDPError as e:
                he[label] = {"error": str(e)}
        out["headlessexperimental"] = he
        # Domain presence
        try:
            doms = b.send("Schema.getDomains")["domains"]
            out["domains_total"] = len(doms)
            out["domains_headless_experimental"] = [d for d in doms if "Headless" in d["name"]]
        except CDPError as e:
            out["domains_error"] = str(e)
    finally:
        save_result("input", out)
        b.close()
        site.stop()
    return out


def exp_scroll_range(args):
    """How far beyond the viewport the recorded picture reaches, versus scroll position."""
    ensure_site()
    site = Site(os.path.join(OUT, "site"))
    b = Browser("range", transport=args.transport)
    out = {"chromium": b.version["product"], "rows": []}
    try:
        p, url = open_page(b, site, ("article", "local", "article.html"))
        p.send("LayerTree.enable")
        for sy in (0, 200, 1000, 3000, 6000, 10000, 20000, 24000):
            p.eval("scrollTo(0,%d)" % sy)
            p.frames(4)
            time.sleep(0.5)
            lay = [L for L in layer_events(b, p, sy % 9) if L.get("drawsContent") and L["width"] > 0]
            ys = []
            for L in lay:
                sid = p.send("LayerTree.makeSnapshot", {"layerId": L["layerId"]})["snapshotId"]
                log = p.send("LayerTree.snapshotCommandLog", {"snapshotId": sid})["commandLog"]
                p.send("LayerTree.releaseSnapshot", {"snapshotId": sid})
                ys += [c["params"]["y"] for c in log if c["method"] == "drawTextBlob"]
            d = os.path.join(OUT, "tmp", "range-%d" % sy)
            inner, outer = print_skp(p, d)
            info = analyze_pictures(d)
            out["rows"].append({"scrollY": p.eval("scrollY"), "viewport_h": VIEW_H, "text_y_min": min(ys) if ys else None,
                                "text_y_max": max(ys) if ys else None, "skp_bytes": sum(x["bytes"] for x in info),
                                "skp_cull": info[0]["cull"], "png_images": sum(x["images"].get("png", 0) for x in info),
                                "call_ms": round(inner, 1)})
            shutil.rmtree(d, ignore_errors=True)
            print(out["rows"][-1], flush=True)
    finally:
        save_result("scroll_range", out)
        b.close()
        site.stop()
    return out


def exp_transport(args):
    """Pipe versus WebSocket: smoke test and round-trip cost."""
    out = {}
    for tr in ("pipe", "ws"):
        b = Browser("tr-" + tr, transport=tr)
        try:
            p = b.new_page()
            p.send("Runtime.enable")
            lat = []
            for _ in range(200):
                t = time.perf_counter()
                p.eval("1")
                lat.append((time.perf_counter() - t) * 1000)
            big = []
            for _ in range(5):
                t = time.perf_counter()
                v = p.eval("'x'.repeat(8*1024*1024)")
                big.append((time.perf_counter() - t) * 1000)
            out[tr] = {"version": b.version["product"], "roundtrip_ms": stats(lat), "8MB_reply_ms": stats(big), "reply_len": len(v),
                       "cmdline_has": [a for a in b.args if "remote-debugging" in a]}
        finally:
            b.close()
    save_result("transport", out)
    return out


# ---- ad-block extension A/B ------------------------------------------------------------
AD_HOSTS = ("googlesyndication", "doubleclick", "googletagservices", "pubmatic", "amazon-adsystem")


def ad_network(p, window):
    """Collect Network events for `window` seconds; returns per-ad-URL outcome."""
    p.b.pump(window)
    urls, outcome = {}, {}
    for m in p.drain():
        q = m.get("params", {})
        if m["method"] == "Network.requestWillBeSent":
            urls[q["requestId"]] = q["request"]["url"]
        elif m["method"] == "Network.loadingFailed":
            outcome[q["requestId"]] = q.get("errorText", "?") + ("/" + q["blockedReason"] if q.get("blockedReason") else "")
        elif m["method"] == "Network.responseReceived":
            outcome[q["requestId"]] = "HTTP %d" % q["response"]["status"]
    return {urls[r][:80]: outcome.get(r, "pending") for r in urls if any(h in urls[r] for h in AD_HOSTS)}


def ext_run(label, flags, site, ext_dir, wait=75, dynamic=False):
    t_start = time.perf_counter()
    b = Browser("ext-" + label, flags=flags, transport="pipe")
    res = {"label": label, "flags": [f for f in flags if "load-extension" in f or "disable-features" in f or "unsafe" in f],
           "product": b.version["product"]}
    try:
        if dynamic:
            try:
                res["loadUnpacked"] = b.send("Extensions.loadUnpacked", {"path": ext_dir})
            except CDPError as e:
                res["loadUnpacked"] = {"error": str(e)}
        sw = None
        if "--load-extension" in " ".join(flags) or dynamic:
            end = time.time() + 40
            while time.time() < end and not sw:
                for t in b.send("Target.getTargets")["targetInfos"]:
                    if t["type"] == "service_worker" and t["url"].startswith("chrome-extension://"):
                        sw = t
                        break
                time.sleep(0.5)
            res["service_worker"] = {"url": sw["url"], "seconds_after_start": round(time.perf_counter() - t_start, 1)} if sw else None
            if sw:
                sid = b.send("Target.attachToTarget", {"targetId": sw["targetId"], "flatten": True})["sessionId"]
                try:
                    r = b.send("Runtime.evaluate", {"expression": "chrome.declarativeNetRequest.getEnabledRulesets()", "awaitPromise": True,
                                                    "returnByValue": True}, session=sid, timeout=20)
                    res["enabled_rulesets_at_sw_attach"] = r.get("result", {}).get("value")
                except CDPError as e:
                    res["enabled_rulesets_at_sw_attach"] = "error: " + str(e)[:120]
        attempts = []
        first_block = None
        p = b.new_page()
        p.setup()
        deadline = time.time() + (wait if sw else 12)
        while True:
            p.drain()
            p.send("Page.navigate", {"url": site.url("ads.html") + "?r=%d" % len(attempts)})
            p.wait_event("Page.loadEventFired", 60)
            net = ad_network(p, 4.0)
            blocked = sum(1 for v in net.values() if "ERR_BLOCKED_BY_CLIENT" in v)
            attempts.append({"t": round(time.perf_counter() - t_start, 1), "blocked": blocked, "requests": len(net)})
            if blocked and first_block is None:
                first_block = attempts[-1]["t"]
                res["outcome"] = net
                break
            res["outcome"] = net
            if time.time() > deadline:
                break
            time.sleep(2.0)
        res["attempts"] = attempts
        res["first_block_seconds_after_start"] = first_block
        if sw:
            try:
                r = b.send("Runtime.evaluate", {"expression": "chrome.declarativeNetRequest.getEnabledRulesets()", "awaitPromise": True,
                                                "returnByValue": True}, session=sid, timeout=20)
                res["enabled_rulesets_at_end"] = r.get("result", {}).get("value")
            except CDPError as e:
                res["enabled_rulesets_at_end"] = "error: " + str(e)[:120]
    finally:
        b.close()
    return res


def exp_ext(args):
    ensure_site()
    site = Site(os.path.join(OUT, "site"))
    ext = args.ext
    out = {"extension_dir": ext, "manifest": json.load(open(os.path.join(ext, "manifest.json"))).get("version"), "runs": []}
    try:
        runs = [
            ("A_with_ext_flag_plus_disable_feature", ["--load-extension=" + ext, "--disable-features=DisableLoadExtensionCommandLineSwitch"], False),
            ("B_no_extension", [], False),
            ("C_with_ext_flag_without_disable_feature", ["--load-extension=" + ext], False),
            ("D_dynamic_Extensions_loadUnpacked", ["--enable-unsafe-extension-debugging"], True),
        ]
        for label, flags, dyn in runs:
            if args.only and label[0] not in args.only:
                continue
            r = ext_run(label, flags, site, ext, wait=args.wait, dynamic=dyn)
            out["runs"].append(r)
            print(label, "blocked-first-at", r.get("first_block_seconds_after_start"), "sw", bool(r.get("service_worker")), flush=True)
            save_result("ext", out)
    finally:
        save_result("ext", out)
        site.stop()
    return out


# ---- capture bundles for the replay tool ---------------------------------------------
SNAP_CASES = [  # (page, device scale factor, scrollY, native)  native = --force-device-scale-factor, no emulation
    ("mix", 1, 0, False), ("mix", 2, 0, False), ("mix", 1, 300, False), ("mix", 1, 800, False), ("mix", 1, 1400, False),
    ("mix", 1, 1900, False), ("mix", 2, 0, True), ("mix", 2, 1400, True),
    ("article", 1, 0, False), ("article", 2, 0, False), ("article", 1, 10000, False), ("article", 2, 0, True),
    ("news", 1, 0, False), ("news", 2, 0, False),
    ("wikipedia", 1, 0, False), ("bbc", 1, 0, False),
]


def snap_name(page, dsf, sy, native=False):
    return "%s@%s%d_y%d" % (page, "n" if native else "", dsf, sy)


def match_layers(pics, layers, dsf):
    """Pair each picture (in file order) with the next drawing LayerTree layer of the same size."""
    out, j = [], 0
    for pic in pics:
        cw, ch = pic["cull"][2] - pic["cull"][0], pic["cull"][3] - pic["cull"][1]
        found = None
        for k in range(j, len(layers)):
            L = layers[k]
            if any(abs(cw - L["width"] * s) <= 3 and abs(ch - L["height"] * s) <= 3 for s in (1, dsf)):
                found, j = k, k + 1
                break
        out.append(layers[found]["layerId"] if found is not None else None)
    return out


def mix_hints(p):
    """Clip and opacity the stock layer pictures lack, taken from DOM geometry (mix page only)."""
    root = p.send("DOM.getDocument", {"depth": 0})["root"]["nodeId"]

    def backend(sel):
        nid = p.send("DOM.querySelector", {"nodeId": root, "selector": sel})["nodeId"]
        return p.send("DOM.describeNode", {"nodeId": nid})["node"]["backendNodeId"]

    clip = p.eval("(()=>{const e=document.getElementById('scroller'),b=e.getBoundingClientRect();"
                  "return [b.left+e.clientLeft,b.top+e.clientTop,b.left+e.clientLeft+e.clientWidth,b.top+e.clientTop+e.clientHeight]})()")
    return {"clip": {str(backend("#scroller")): clip}, "opacity": {str(backend("#wc")): 0.7}}


def snap_case(b, site, page, dsf, sy, root, native=False):
    spec = [s for s in PAGE_SPECS if s[0] == page][0]
    name = snap_name(page, dsf, sy, native)
    d = os.path.join(root, name)
    shutil.rmtree(d, ignore_errors=True)
    os.makedirs(d)
    p, url = open_page(b, site, spec, dsf=0 if native else dsf)
    p.send("LayerTree.enable")
    p.eval("document.getAnimations().forEach(a=>a.pause())")
    if sy:
        p.eval("scrollTo(0,%d)" % sy)
        p.frames(4)
        time.sleep(0.6)
    lay = layer_events(b, p, 7)
    drawing = [L for L in lay if L.get("drawsContent") and L["width"] > 0]
    metrics = p.send("Page.getLayoutMetrics")
    shot = base64.b64decode(p.send("Page.captureScreenshot", {"format": "png"})["data"])
    with open(os.path.join(d, "screenshot.png"), "wb") as f:
        f.write(shot)
    pd = os.path.join(d, "pictures")
    inner, outer = print_skp(p, pd)
    pics = analyze_pictures(pd)
    ids = match_layers(pics, drawing, dsf)
    byid = {L["layerId"]: L for L in lay}
    hints = mix_hints(p) if page == "mix" else {"clip": {}, "opacity": {}}
    layers = []
    for pic, lid in zip(pics, ids):
        L = byid.get(lid) or {}
        node = str(L.get("backendNodeId"))
        layers.append({"file": "pictures/" + pic["file"], "layerId": lid, "size": [L.get("width"), L.get("height")],
                       "cull": pic["cull"], "transform": L.get("transform") or [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1],
                       "offset": [L.get("offsetX", 0), L.get("offsetY", 0)], "backendNodeId": L.get("backendNodeId"),
                       "clip": hints["clip"].get(node), "opacity": hints["opacity"].get(node, 1.0),
                       "bytes": pic["bytes"], "typeface_bytes": pic["typeface_bytes"], "images": pic["images"]})
    unmatched = {}  # layers that draw but wrote no picture: which DOM node owns them
    for L in drawing:
        if L["layerId"] not in ids and L.get("backendNodeId"):
            try:
                n = p.send("DOM.describeNode", {"backendNodeId": L["backendNodeId"]})["node"]
                unmatched[L["layerId"]] = {"nodeName": n.get("nodeName"), "frameId": n.get("frameId"), "attributes": (n.get("attributes") or [])[:8]}
            except Exception as e:  # noqa: BLE001 - record and carry on
                unmatched[L["layerId"]] = {"error": str(e)[:120]}
    manifest = {
        "name": name, "page": page, "url": url, "dsf": dsf, "native_dsf": native, "scrollY": p.eval("scrollY"), "viewport_css": [VIEW_W, VIEW_H],
        "screenshot": "screenshot.png", "screenshot_bytes": len(shot), "css_layout_viewport": metrics.get("cssLayoutViewport"),
        "content_css": metrics.get("cssContentSize"), "skp_call_ms": round(inner, 1), "layers": layers,
        "drawing_layers_without_picture": [L["layerId"] for L in drawing if L["layerId"] not in ids],
        "drawing_layers_without_picture_nodes": unmatched,
        "all_layertree_layers": lay, "load": cpu_load(),
    }
    with open(os.path.join(d, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=1)
    b.send("Target.closeTarget", {"targetId": p.tid})
    return manifest


def exp_snap(args):
    ensure_site()
    site = Site(os.path.join(OUT, "site"))
    root = os.path.join(OUT, "captures")
    os.makedirs(root, exist_ok=True)
    b = Browser("snap", transport=args.transport)
    bn = None
    done = []
    try:
        for page, dsf, sy, native in SNAP_CASES:
            if args.pages and page not in args.pages:
                continue
            if native and bn is None:
                bn = Browser("snapn", flags=["--force-device-scale-factor=%d" % dsf], transport=args.transport)
            m = snap_case(bn if native else b, site, page, dsf, sy, root, native)
            print("%-22s layers=%d bytes=%d shot=%s skp_call=%sms unmatched=%s" % (
                m["name"], len(m["layers"]), sum(x["bytes"] for x in m["layers"]), m["screenshot_bytes"], m["skp_call_ms"],
                m["drawing_layers_without_picture"]), flush=True)
            done.append(m["name"])
    finally:
        b.close()
        if bn:
            bn.close()
        site.stop()
    return done


def main():
    ap = argparse.ArgumentParser(description="LumaBrowser R2: stock Chromium picture capture experiments")
    ap.add_argument("cmd", choices=["site", "methods", "layers", "input", "range", "transport", "tracebuf", "ext", "snap", "all"])
    ap.add_argument("--calls", type=int, default=20, help="timed repetitions per measurement")
    ap.add_argument("--pages", default="", help="comma separated subset of mix,article,news,wikipedia,bbc")
    ap.add_argument("--transport", default="pipe", choices=["pipe", "ws"])
    ap.add_argument("--ext", default=os.environ.get("LB_EXT_DIR", ""), help="unpacked MV3 ad-block extension directory")
    ap.add_argument("--only", default="", help="ext: run subset of A,B,C,D")
    ap.add_argument("--wait", type=int, default=75, help="ext: seconds to wait for the first blocked request")
    args = ap.parse_args()
    args.pages = [x for x in args.pages.split(",") if x]
    os.makedirs(OUT, exist_ok=True)
    if args.cmd == "site":
        print("\n".join(ensure_site() and sorted(os.listdir(os.path.join(OUT, "site")))))
        return
    fn = {"methods": exp_methods, "layers": exp_layers, "input": exp_input, "range": exp_scroll_range,
          "transport": exp_transport, "tracebuf": exp_tracebuf, "ext": exp_ext, "snap": exp_snap}
    if args.cmd == "all":
        for name in ("snap", "methods", "layers", "input", "range", "transport"):
            print("=== " + name, flush=True)
            fn[name](args)
        if args.ext:
            fn["ext"](args)
    else:
        fn[args.cmd](args)


if __name__ == "__main__":
    main()
