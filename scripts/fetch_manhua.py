#!/usr/bin/env python3
"""Robust, resumable downloader for a roliascan.com manhua (personal offline use).

Images live on a deterministic CDN path:
    https://roliascan.org/storage/chapters/manhwa_<MANGA_ID>_<key>/<pagefile>
where <key> is the chapter number and <pagefile> is EITHER a multi-page series
(page_001.jpg, page_002.jpg, ...) OR a single stitched strip
(page_001_stitched.webp). The filename pattern varies per chapter, so we detect
it per chapter (probe a small candidate set; fall back to the chapter's HTML
JSON-LD for the authoritative first-page URL), then enumerate pages until they
run out.

Built for an UNSTABLE site: realistic headers + Referer, retries with backoff,
resume (skip files already on disk), limited concurrency, polite delays.
Re-run any time — it only fetches what is missing. Reads the chapter list from
_chapters.json (produced separately from the reader's chapter selector).

Usage:
    python fetch_manhua.py                 # all chapters in _chapters.json
    python fetch_manhua.py 37 117 172.5    # only these chapters (relaunch)
"""
import os
import re
import sys
import json
import time
import random
import threading
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed

MANGA_ID = 319969
SLUG = "sir-dont-show-off"
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_ROOT = os.path.join(BASE_DIR, "data", "manhua", SLUG)
CHAPTERS_JSON = os.path.join(OUT_ROOT, "_chapters.json")
STORAGE = "https://roliascan.org/storage/chapters/manhwa_{mid}_{key}/{fn}"
READER = "https://roliascan.com/read/sir-don-t-show-off/{slug}/"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36")
REFERER = "https://roliascan.com/"

# page_001 filename candidates tried in order to auto-detect the chapter's scheme
CANDIDATES = [("", "jpg"), ("", "jpeg"), ("", "webp"), ("", "png"),
              ("_stitched", "webp"), ("_stitched", "jpg")]

WORKERS = 3
PAGE_DELAY = 0.3
RETRIES = 4
MAX_PAGES = 300
END_AFTER_MISSES = 2

_lock = threading.Lock()


def log(msg):
    with _lock:
        print(msg, flush=True)


def dirname_for(num):
    if "." in num:
        w, f = num.split(".", 1)
        return f"{int(w):03d}.{f}"
    return f"{int(num):03d}"


def get(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Referer": REFERER})
    return urllib.request.urlopen(req, timeout=timeout)


def try_get_bytes(url):
    """Return (bytes|None, server_error_bool). None+False means a clean 404."""
    server_error = False
    for attempt in range(RETRIES):
        try:
            with get(url) as r:
                data = r.read()
            return (data if data and len(data) > 100 else None), server_error
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None, server_error
            server_error = True
            time.sleep(1.5 * (attempt + 1) + random.random())
        except Exception:
            server_error = True
            time.sleep(1.5 * (attempt + 1) + random.random())
    return None, server_error


def pagefile(pnum, padw, suffix, ext):
    return f"page_{pnum:0{padw}d}{suffix}.{ext}"


def detect_scheme(num, slug, chdir):
    """Return (key, padw, suffix, ext, page1_bytes_or_None) or None if not found.

    First honours an already-downloaded page_001.* on disk (resume without a
    network probe), then probes the candidate set, then falls back to the
    chapter HTML's JSON-LD first-page URL.
    """
    key = num
    # Resume: reuse an existing page_001 on disk to learn the scheme.
    for fn in sorted(os.listdir(chdir)) if os.path.isdir(chdir) else []:
        m = re.match(r"page_(0*1)([^.]*)\.(jpg|jpeg|webp|png)$", fn)
        if m:
            return key, len(m.group(1)), m.group(2), m.group(3), None
    # Probe candidates at key = chapter number.
    for suffix, ext in CANDIDATES:
        url = STORAGE.format(mid=MANGA_ID, key=key, fn=f"page_001{suffix}.{ext}")
        data, _ = try_get_bytes(url)
        if data:
            return key, 3, suffix, ext, data
        time.sleep(0.15)
    # Fallback: authoritative first-page URL from the chapter page's JSON-LD.
    if slug:
        html_bytes, _ = try_get_bytes(READER.format(slug=slug))
        if html_bytes:
            html = html_bytes.decode("utf-8", errors="replace")
            m = re.search(
                r"manhwa_%d_([0-9.]+)/(page_(\d+)([^\"'/>]*?)\.(jpg|jpeg|png|webp))" % MANGA_ID,
                html)
            if m:
                rkey, padw, suffix, ext = m.group(1), len(m.group(3)), m.group(4), m.group(5)
                url = STORAGE.format(mid=MANGA_ID, key=rkey, fn=m.group(2))
                data, _ = try_get_bytes(url)
                if data:
                    return rkey, padw, suffix, ext, data
    return None


def download_chapter(entry):
    num, slug = entry["num"], entry.get("slug", "")
    chdir = os.path.join(OUT_ROOT, dirname_for(num))
    os.makedirs(chdir, exist_ok=True)

    scheme = detect_scheme(num, slug, chdir)
    if not scheme:
        log(f"ch {num:>6}: NO IMAGES FOUND (pattern undetected)")
        return {"chapter": num, "pages": 0, "downloaded": 0, "skipped": 0,
                "bytes": 0, "failed_pages": [], "undetected": True}
    key, padw, suffix, ext, page1 = scheme

    pages = downloaded = skipped = total = 0
    failed = []
    misses = 0
    p = 1
    while p <= MAX_PAGES:
        dest = os.path.join(chdir, pagefile(p, padw, suffix, ext))
        if os.path.exists(dest) and os.path.getsize(dest) > 0:
            pages += 1; skipped += 1; total += os.path.getsize(dest); misses = 0; p += 1
            continue
        if p == 1 and page1 is not None:
            data, server_error = page1, False
        else:
            url = STORAGE.format(mid=MANGA_ID, key=key, fn=pagefile(p, padw, suffix, ext))
            data, server_error = try_get_bytes(url)
        if data:
            tmp = dest + ".part"
            with open(tmp, "wb") as f:
                f.write(data)
            os.replace(tmp, dest)
            pages += 1; downloaded += 1; total += len(data); misses = 0
        elif server_error:
            failed.append(p)                  # transient error, not end-of-chapter
        else:
            misses += 1
            if misses >= END_AFTER_MISSES:
                break
        p += 1
        time.sleep(PAGE_DELAY)

    log(f"ch {num:>6}: {pages} pages (+{downloaded} new, {skipped} cached, "
        f"{len(failed)} failed) {total/1e6:.1f}MB  [{suffix or 'multi'}.{ext}]")
    return {"chapter": num, "pages": pages, "downloaded": downloaded,
            "skipped": skipped, "bytes": total, "failed_pages": failed}


def main():
    data = json.load(open(CHAPTERS_JSON, encoding="utf-8"))
    by_num = {c["num"]: c for c in data["chapters"]}
    if len(sys.argv) > 1:
        targets = [by_num[a] for a in sys.argv[1:] if a in by_num]
    else:
        targets = data["chapters"]
    log(f"Downloading {len(targets)} chapters -> {OUT_ROOT}")

    results = []
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = {ex.submit(download_chapter, e): e["num"] for e in targets}
        for fut in as_completed(futs):
            try:
                results.append(fut.result())
            except Exception as e:
                log(f"ch {futs[fut]}: WORKER ERROR {e}")
                results.append({"chapter": futs[fut], "error": str(e), "pages": 0})

    results.sort(key=lambda r: float(r["chapter"]))
    summary = {
        "manga_id": MANGA_ID, "slug": SLUG,
        "chapters_requested": len(targets),
        "chapters_with_pages": sum(1 for r in results if r.get("pages", 0) > 0),
        "total_pages": sum(r.get("pages", 0) for r in results),
        "total_mb": round(sum(r.get("bytes", 0) for r in results) / 1e6, 1),
        "empty_chapters": [r["chapter"] for r in results if r.get("pages", 0) == 0],
        "failed": {r["chapter"]: r["failed_pages"] for r in results if r.get("failed_pages")},
    }
    json.dump(summary, open(os.path.join(OUT_ROOT, "_manifest.json"), "w"), indent=2)
    log("=" * 60)
    log(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
