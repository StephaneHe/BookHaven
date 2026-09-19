#!/usr/bin/env python3
"""Complete the manhua download using roliascan's AUTHORITATIVE page list.

IMPORTANT — do NOT assume a fixed strip step. roliascan numbers stitched strips
by their first source-page index, but the STEP VARIES per strip (14, 15, 16, ...):
e.g. ch57 = page_001/016/031/046/062 (46->62 is +16), ch99 = page_001/015/029/043
(+14). An earlier version enumerated by a fixed step of 15 and silently skipped
real strips (page_062, page_015, ...), leaving chapters incomplete. NEVER probe a
grid.

Source of truth: the reader's own endpoint
    GET https://roliascan.com/auth/chapter-content?chapter_id=<POSTID>
which returns {"success":true,"images":[<exact ordered image URLs>],"total":N}.
We download exactly those URLs (works for stitched AND paged chapters). The
POSTID per displayed chapter comes from _chapters.json (num -> postid).

Downloads are robust (UA + Referer, retries/backoff, resume: skip files already
valid on disk, polite delays). Trailing ad banners (728x90 GIF mislabelled .jpg)
are recognised and skipped, never saved.

Usage:
    python fetch_manhua_strips.py                 # all chapters in _chapters.json
    python fetch_manhua_strips.py 57 99 172.5     # only these displayed numbers
"""
import os
import re
import sys
import io
import json
import time
import random
import struct
import hashlib
import urllib.request
import urllib.error

MANGA_ID = 319969
SLUG = "sir-dont-show-off"
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_ROOT = os.path.join(BASE_DIR, "data", "manhua", SLUG)
CHAPTERS_JSON = os.path.join(OUT_ROOT, "_chapters.json")
CONTENT_URL = "https://roliascan.com/auth/chapter-content?chapter_id={pid}"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36")
IMG_REFERER = "https://roliascan.org/"     # CDN host for the images
SITE_REFERER = "https://roliascan.com/"    # site host for the content endpoint
RETRIES = 5
PAGE_DELAY = 0.3
AD_MD5 = "ed6d7bf6aa"

ANOMALIES = []


def log(msg):
    print(msg, flush=True)


def flag(kind, msg):
    ANOMALIES.append({"kind": kind, "msg": msg})
    log(f"  ! [{kind}] {msg}")


def _get(url, referer, timeout=45):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA, "Referer": referer,
        "X-Requested-With": "XMLHttpRequest", "Accept": "application/json, */*"})
    return urllib.request.urlopen(req, timeout=timeout)


def fetch_bytes(url, referer=IMG_REFERER):
    """Return (bytes|None, status) where status in {'ok','404','err'}; retries transient."""
    for a in range(RETRIES):
        try:
            with _get(url, referer, timeout=30) as r:
                data = r.read()
            return (data if data and len(data) > 200 else None), ("ok" if data else "err")
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None, "404"
            time.sleep(1.0 * (a + 1) + random.random())
        except Exception:
            time.sleep(1.0 * (a + 1) + random.random())
    return None, "err"


def chapter_images(postid):
    """Authoritative ordered image URLs for a chapter, or None on failure."""
    for a in range(RETRIES):
        try:
            with _get(CONTENT_URL.format(pid=postid), SITE_REFERER) as r:
                j = json.loads(r.read().decode("utf-8", "replace"))
            if j.get("success") and isinstance(j.get("images"), list):
                return j["images"]
            return []                      # success:false / no images (locked?) -> treat as empty
        except Exception:
            time.sleep(1.0 * (a + 1) + random.random())
    return None


# ── image validation / ads ──────────────────────────────────────────────────

def is_ad_gif(data):
    if data[:6] != b"GIF89a":
        return False
    return hashlib.md5(data).hexdigest()[:10] == AD_MD5 or len(data) == 85633


def end_marker_ok(path, data):
    ext = os.path.splitext(path)[1].lower()
    if ext in (".jpg", ".jpeg"):
        return data[-2:] == b"\xff\xd9"
    if ext == ".png":
        return b"IEND" in data[-12:]
    if ext == ".webp":
        if len(data) < 12 or data[:4] != b"RIFF" or data[8:12] != b"WEBP":
            return False
        return abs((struct.unpack("<I", data[4:8])[0] + 8) - len(data)) <= 2
    return True


def valid_image_bytes(path, data):
    if not end_marker_ok(path, data):
        return False
    try:
        from PIL import Image, ImageFile
        ImageFile.LOAD_TRUNCATED_IMAGES = False
        im = Image.open(io.BytesIO(data)); im.load(); im.size
        return True
    except Exception:
        return False


def local_has_valid(path):
    if not (os.path.exists(path) and os.path.getsize(path) > 200):
        return False
    with open(path, "rb") as f:
        return valid_image_bytes(path, f.read())


def save(path, data):
    tmp = path + ".part"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, path)


def dirname_for(num):
    if "." in num:
        w, f = num.split(".", 1)
        return f"{int(w):03d}.{f}"
    return f"{int(num):03d}"


def process_chapter(num, postid):
    chdir = os.path.join(OUT_ROOT, dirname_for(num))
    os.makedirs(chdir, exist_ok=True)
    imgs = chapter_images(postid)
    if imgs is None:
        flag("fetch-failed", f"ch{num} (pid {postid}): chapter-content unreachable after retries")
        return {"chapter": num, "postid": postid, "error": "fetch-failed"}
    if not imgs:
        flag("empty-chapter", f"ch{num} (pid {postid}): no images (locked/premium at source?)")
        return {"chapter": num, "postid": postid, "images_total": 0, "present": [], "downloaded": [], "ads": [], "missing": []}

    present, downloaded, ads, missing = [], [], [], []
    for url in imgs:
        fn = url.rsplit("/", 1)[-1].split("?")[0]
        dest = os.path.join(chdir, fn)
        if local_has_valid(dest):
            present.append(fn); continue
        data, st = fetch_bytes(url, IMG_REFERER)
        if data and is_ad_gif(data):
            ads.append(fn); continue                 # trailing ad banner: excluded, never saved
        if data and valid_image_bytes(dest, data):
            save(dest, data); downloaded.append(fn)
        else:
            missing.append(fn)
            flag("missing-strip", f"ch{num}: {fn} could not be fetched/validated (status={st})")
        time.sleep(PAGE_DELAY)

    real_total = len(imgs) - len(ads)
    have = len(present) + len(downloaded)
    log(f"ch {num:>6} (pid {postid}): CDN={len(imgs)} real={real_total} "
        f"present={len(present)} +dl={len(downloaded)} ads={len(ads)} missing={missing}")
    return {"chapter": num, "postid": postid, "images_total": len(imgs), "real_total": real_total,
            "present": present, "downloaded": downloaded, "ads": ads, "missing": missing}


def main():
    data = json.load(open(CHAPTERS_JSON, encoding="utf-8"))
    by_num = {c["num"]: c for c in data["chapters"]}
    nums = list(by_num.keys())
    if len(sys.argv) > 1:
        want = set(sys.argv[1:])
        nums = [n for n in nums if n in want]
    nums.sort(key=lambda n: float(n))
    log(f"Completing {len(nums)} chapters via authoritative /auth/chapter-content -> {OUT_ROOT}")

    results = []
    for n in nums:
        results.append(process_chapter(n, by_num[n]["postid"]))

    total_dl = sum(len(r.get("downloaded", [])) for r in results)
    total_missing = sum(len(r.get("missing", [])) for r in results)
    incomplete = [r["chapter"] for r in results if r.get("missing")]
    summary = {"chapters": len(nums), "strips_downloaded": total_dl,
               "strips_missing": total_missing, "incomplete_chapters": incomplete,
               "anomalies": ANOMALIES, "detail": results}
    json.dump(summary, open(os.path.join(OUT_ROOT, "_strips_manifest.json"), "w"), indent=1)
    log("=" * 60)
    log(f"DONE: {total_dl} strips downloaded, still-missing={total_missing}, "
        f"{len(ANOMALIES)} anomalies. Incomplete: {incomplete}")


if __name__ == "__main__":
    main()
