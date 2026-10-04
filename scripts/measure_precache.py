"""Time to first strip of the NEXT webtoon chapter (R98), in a real browser profile with a disk HTTP cache,
Wi-Fi throttled to ~40 Mbit/s. Run against the live server: python scripts/measure_precache.py
Progress saves are swallowed in the page (no Playwright routing: routing disables the HTTP cache)."""
import json, sys, tempfile, time
from playwright.sync_api import sync_playwright
B = "http://127.0.0.1:8097"
INIT = """(() => { const f = window.fetch; window.fetch = (u, o) => (o && o.method === 'PUT' && String(u).includes('/progress')) ? Promise.resolve(new Response('{}')) : f(u, o); })()"""
out = []
with sync_playwright() as p:
    for start in (39614, 39624, 39632):
        prof = tempfile.mkdtemp(prefix="bh-prof-")
        ctx = p.chromium.launch_persistent_context(prof, viewport={"width": 1280, "height": 800})
        pg = ctx.pages[0] if ctx.pages else ctx.new_page()
        pg.add_init_script(INIT)
        cdp = ctx.new_cdp_session(pg); cdp.send("Network.enable")
        cdp.send("Network.emulateNetworkConditions", {"offline": False, "latency": 20, "downloadThroughput": 5_000_000, "uploadThroughput": 2_500_000})
        pg.goto(B + "/"); pg.evaluate("() => localStorage.removeItem('bookhaven.precacheChapters')"); pg.wait_for_timeout(2000)
        pg.evaluate(f"() => openBook({start})")
        pg.wait_for_function("() => document.querySelectorAll('#comic-scroll img').length && [...document.querySelectorAll('#comic-scroll img')].every(i => i.complete && i.naturalHeight)", timeout=120000)
        pg.wait_for_timeout(30000)                                   # reading time
        st = pg.evaluate("() => comicPrecacheStatus()")
        pg.evaluate("() => performance.clearResourceTimings()")
        t0 = time.time()
        pg.evaluate("() => comicChapterStep(1)")
        pg.wait_for_function(f"() => {{ const i = document.querySelector('#comic-scroll img'); return i && i.src.includes('/books/{start + 1}/') && i.complete && i.naturalHeight > 0; }}", timeout=120000)
        dt = time.time() - t0
        pg.wait_for_timeout(1500)
        net = pg.evaluate(f"() => performance.getEntriesByType('resource').filter(e => e.name.includes('/books/{start + 1}/comic-page/')).map(e => e.transferSize)")
        out.append({"next": start + 1 - 39580, "first_strip_s": round(dt, 2), "precached": f"{st['done']}/{st['queued']} of {len(st['books'])} ch",
                    "strips_from_network": sum(1 for x in net if x > 0), "strips_from_cache": sum(1 for x in net if x == 0)})
        ctx.close()
print(json.dumps(out, indent=1))
