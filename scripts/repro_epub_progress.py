"""Reproduce the EPUB reader progress bug on the LIVE web reader (port 8097).

`const state` is module-scoped (not on window), so we cannot read it from an
injected script. Instead we drive the reader through its GLOBAL functions
(openBook / epubNext / epubFontInc) and observe the ONLY thing that matters for
the bug: the position persisted via the /progress API.

Two scenarios on the same book, progress reset before each:
  A) read forward WITHOUT changing font size
  B) read forward AFTER a font-size change
For each we report whether the saved current_location advances as we read.
"""
import sys
import time
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8097"
BOOK = int(sys.argv[1]) if len(sys.argv) > 1 else 29841
USER = sys.argv[2] if len(sys.argv) > 2 else "steph"
PIN = "1111"


def api_login(page):
    page.goto(BASE)
    st = page.evaluate("""async ({u, p}) => (await fetch('/api/auth/login',{
        method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({username:u, pin:p})})).status""", {"u": USER, "p": PIN})
    assert st == 200, f"login status {st}"


def saved(page):
    return page.evaluate(f"async () => (await fetch('/api/books/{BOOK}/progress')).json()")


def reset(page):
    page.evaluate(f"async () => (await fetch('/api/books/{BOOK}/progress',{{method:'DELETE'}}))")


def open_and_wait(page):
    page.evaluate(f"() => openBook({BOOK})")
    # Ready == seekbar enabled (locations loaded) OR at least first page displayed.
    page.wait_for_function(
        "() => { const s = document.getElementById('epub-seekbar');"
        " return s && s.disabled === false; }", timeout=90000)


def turn(page, n):
    for _ in range(n):
        page.evaluate("() => epubNext()")
        page.wait_for_timeout(600)


def scenario(page, change_font):
    reset(page)
    open_and_wait(page)
    time.sleep(1.0)
    turn(page, 3)
    time.sleep(3.4)                      # flush the 3s debounce
    start = saved(page)

    if change_font:
        page.evaluate("() => { epubFontInc(); epubFontInc(); epubFontInc(); }")
        page.wait_for_timeout(1000)

    turn(page, 4)
    time.sleep(3.4)
    end = saved(page)

    page.evaluate("() => closeReader()")
    page.wait_for_timeout(800)
    return {
        "start_loc": (start or {}).get("current_location", ""),
        "end_loc": (end or {}).get("current_location", ""),
        "start_prog": (start or {}).get("progress"),
        "end_prog": (end or {}).get("progress"),
    }


def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.on("dialog", lambda d: d.dismiss())
        api_login(page)
        out = {
            "A_no_font_change": scenario(page, change_font=False),
            "B_font_change": scenario(page, change_font=True),
        }
        browser.close()

    for name, v in out.items():
        advanced = v["start_loc"] != v["end_loc"] and bool(v["end_loc"])
        print(f"\n=== {name} ===")
        print(f"  saved start : {v['start_prog']}%  {v['start_loc'][:64]}")
        print(f"  saved end   : {v['end_prog']}%  {v['end_loc'][:64]}")
        print(f"  -> saved position ADVANCED while reading : {advanced}")


if __name__ == "__main__":
    run()
