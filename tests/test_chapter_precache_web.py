"""R98 (web): while a webtoon chapter is read, the next k chapters of the series
are pre-cached in the background -- after the current chapter is loaded, first
strips first, never beyond k, k configurable, cancelled when the reader leaves.

Fake series served through Playwright routes (ids 9200xx); every request is
logged with a timestamp. Nothing reaches the library database.
"""
import io
import json
import re
import time

import pytest
from PIL import Image

SERIES = [920001, 920002, 920003, 920004, 920005, 920006]
PLATES = {b: 6 for b in SERIES}
PLATES[920003] = 30            # long chapters so a cancellation lands mid-way
PLATES[920004] = 30
SIZES = {}                     # bid -> file_size served in series_following (budget test)
BUSY = {}                      # (bid, plate) -> number of 503 answers still to give
LOG = []                       # (time, kind, book, plate)
_PNG = {}


def _png(shade):
    if shade not in _PNG:
        buf = io.BytesIO()
        Image.new("RGB", (40, 240), (shade, 60, 120)).save(buf, "PNG")
        _PNG[shade] = buf.getvalue()
    return _PNG[shade]


def _handler(route):
    req = route.request
    if req.method != "GET":
        return route.fulfill(status=200, content_type="application/json", body="{}")
    m = re.search(r"/api/books/(9200\d\d)(/[^?]*)?", req.url)
    bid, rest = int(m.group(1)), (m.group(2) or "")
    i = SERIES.index(bid)
    if rest == "":
        ref = lambda b: {"id": b, "title": f"Ch {b}", "format": "cbz", "file_size": SIZES.get(b, 1000)}  # noqa: E731
        body = {"id": bid, "title": f"Ch {bid}", "format": "cbz", "progress": None, "webtoon": True,
                "series": "Fake", "file_size": 1, "modified_at": "x",
                "series_prev": ref(SERIES[i - 1]) if i else None,
                "series_next": ref(SERIES[i + 1]) if i + 1 < len(SERIES) else None,
                "series_following": [ref(b) for b in SERIES[i + 1:i + 6]]}
        return route.fulfill(status=200, content_type="application/json", body=json.dumps(body))
    if rest == "/comic-pages":
        LOG.append((time.time(), "list", bid, None))
        pages = [f"p_{k}.png" for k in range(PLATES[bid])]
        return route.fulfill(status=200, content_type="application/json",
                             body=json.dumps({"pages": pages, "total": len(pages), "content_version": f"v{bid}"}))
    pm = re.match(r"/comic-page/(\d+)$", rest)
    if pm and BUSY.get((bid, int(pm.group(1))), 0) > 0:
        BUSY[(bid, int(pm.group(1)))] -= 1
        LOG.append((time.time(), "busy", bid, int(pm.group(1))))
        return route.fulfill(status=503, headers={"Retry-After": "2"}, body="busy")
    if pm:
        LOG.append((time.time(), "page", bid, int(pm.group(1))))
        return route.fulfill(status=200, content_type="image/png", body=_png((int(pm.group(1)) * 7) % 256))
    return route.fulfill(status=200, content_type="application/json", body="{}")


@pytest.fixture
def reader(desktop_page):
    page = desktop_page
    pattern = re.compile(r".*/api/books/9200\d\d(/.*)?$")
    page.route(pattern, _handler)
    LOG.clear()
    SIZES.clear()
    BUSY.clear()
    page.evaluate("() => localStorage.removeItem('bookhaven.precacheChapters')")
    yield page
    page.evaluate("() => { closeReader(); localStorage.removeItem('bookhaven.precacheChapters'); }")
    page.wait_for_timeout(300)
    page.unroute(pattern)


def _open(page, bid):
    page.evaluate(f"() => openBook({bid})")
    page.wait_for_function("() => document.querySelectorAll('#comic-scroll img').length"
                           " && [...document.querySelectorAll('#comic-scroll img')].every(i => i.complete && i.naturalHeight)",
                           timeout=15000)


def _wait_finished(page, timeout=20000):
    page.wait_for_function("() => comicPrecacheStatus().finished", timeout=timeout)


def _pages_of(bid):
    return [(t, p) for (t, kind, b, p) in LOG if kind == "page" and b == bid]


def test_R98_precache_next_k_chapters_after_current_is_loaded(reader):
    page = reader
    _open(page, 920001)
    _wait_finished(page)
    st = page.evaluate("() => comicPrecacheStatus()")
    assert st["books"] == [920002, 920003, 920004]                 # default k = 3
    for b in (920002, 920003, 920004):                             # every strip of each
        assert sorted({p for _, p in _pages_of(b)}) == list(range(PLATES[b])), b
    assert not _pages_of(920005) and not _pages_of(920006)         # nothing beyond k
    # never competes with the chapter being read: starts after its last strip
    last_current = max(t for t, _ in _pages_of(920001))
    first_pre = min(t for (t, kind, b, _) in LOG if b != 920001)
    assert first_pre >= last_current


def test_R98_first_strips_of_every_chapter_come_first(reader):
    page = reader
    _open(page, 920001)
    _wait_finished(page)
    pre = [(b, p) for (_, kind, b, p) in LOG if kind == "page" and b != 920001]
    firsts = [x for x in pre if x[1] < 2]
    assert pre[:len(firsts)] == firsts and len(firsts) == 6        # 2 strips x 3 chapters, first
    rest = [b for (b, p) in pre[len(firsts):]]
    assert rest == sorted(rest, key=SERIES.index)                  # then chapter by chapter


@pytest.mark.parametrize("k,expected", [("1", [920002]), ("0", [])])
def test_R98_precache_depth_is_configurable(reader, k, expected):
    page = reader
    page.evaluate(f"() => localStorage.setItem('bookhaven.precacheChapters', '{k}')")
    _open(page, 920001)
    page.wait_for_timeout(2500)
    touched = sorted({b for (_, kind, b, _) in LOG if b != 920001})
    assert touched == expected


def test_R98_precache_cancelled_when_reader_leaves(reader):
    page = reader
    _open(page, 920002)                                            # next: 920003/920004 = 30 strips each
    page.wait_for_function("() => comicPrecacheStatus().done >= 8", timeout=15000)
    page.evaluate("() => closeReader()")
    n_at_close = len([x for x in LOG if x[2] != 920002])
    page.wait_for_timeout(2000)
    n_after = len([x for x in LOG if x[2] != 920002])
    assert n_after - n_at_close <= 1                               # at most the in-flight request
    assert page.evaluate("() => comicPrecacheStatus().running") is False
    total = sum(PLATES[b] for b in (920003, 920004, 920005)) + 3
    assert n_after < total                                         # it really stopped mid-way


def test_R98_moving_on_restarts_precache_from_the_new_chapter(reader):
    page = reader
    _open(page, 920001)
    _wait_finished(page)
    page.evaluate("() => comicChapterStep(1)")
    page.wait_for_function("() => document.getElementById('reader-title').textContent === 'Ch 920002'")
    _wait_finished(page)
    assert page.evaluate("() => comicPrecacheStatus().books") == [920003, 920004, 920005]


def test_R98_byte_budget_limits_whole_chapters(reader):
    """Oversized upcoming chapters (webtoon tomes) only get their first strips."""
    page = reader
    mb = 1024 * 1024
    SIZES.update({920002: 300 * mb, 920003: 300 * mb, 920004: 50 * mb})    # budget 400 MB
    _open(page, 920001)
    _wait_finished(page)
    assert page.evaluate("() => comicPrecacheStatus().whole") == [920002, 920004]
    assert sorted({p for _, p in _pages_of(920002)}) == list(range(PLATES[920002]))
    assert sorted({p for _, p in _pages_of(920003)}) == [0, 1]             # first strips only
    assert sorted({p for _, p in _pages_of(920004)}) == list(range(PLATES[920004]))


def test_R100_precache_backs_off_when_server_is_busy(reader):
    """A 503 (server shedding load) stops the pre-cache: the chapter being read
    keeps the server to itself."""
    page = reader
    BUSY[(920002, 1)] = 99
    _open(page, 920001)
    page.wait_for_function("() => comicPrecacheStatus().running === false", timeout=15000)
    page.wait_for_timeout(1500)
    pre = [(b, p) for (_, kind, b, p) in LOG if kind in ("page", "busy") and b != 920001]
    assert pre[-1] == (920002, 1)                 # nothing requested after the 503
    assert not [x for x in pre if x[0] in (920003, 920004) and x[1] >= 2]


def test_R100_strip_refused_once_is_retried(reader):
    """A strip answered 503 (server busy) is retried and finally shows."""
    page = reader
    BUSY[(920001, 2)] = 1
    _open(page, 920001)                           # waits until every strip is loaded
    tries = [k for (_, k, b, p) in LOG if b == 920001 and p == 2]
    assert tries[:2] == ["busy", "page"]
