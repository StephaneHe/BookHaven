#!/usr/bin/env python3
"""Complete the manhua download: fetch the MISSING stitched strips per chapter.

Root cause of the earlier gap: roliascan serves each stitched chapter as several
tall strips numbered by their FIRST source-page index — page_001_stitched.webp
(source pages 1-15), page_016_stitched.webp (16-30), page_031 (31-45), ... i.e.
a fixed STEP of 15. The original fetch_manhua.py enumerated page_001, page_002,
... and stopped at the first 404 (page_002), so it kept ONLY the first strip of
every stitched chapter. This script enumerates the real strip indices (step 15)
and downloads whatever is missing. Paged (early jpg) chapters are re-verified
contiguously. The CDN roliascan.org/storage/.../manhwa_<id>_<K>/ is authoritative;
local dir 0K maps 1:1 to CDN folder _K (verified byte-identical page_001).

Robust for an unstable site: realistic headers + Referer, retries with backoff,
resume (skip files already valid on disk), polite delays. Re-run any time.

Usage:
    python fetch_manhua_strips.py                # all chapters
    python fetch_manhua_strips.py 49 50 51       # only these CDN folder numbers
"""
import os
import sys
import re
import json
import time
import random
import struct
import urllib.request
import urllib.error

MANGA_ID = 319969
SLUG = "sir-dont-show-off"
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_ROOT = os.path.join(BASE_DIR, "data", "manhua", SLUG)
STORAGE = "https://roliascan.org/storage/chapters/manhwa_{mid}_{key}/{fn}"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36")
REFERER = "https://roliascan.org/"

STRIP_STEP = 15          # stitched strips are indexed 1, 16, 31, 46, ... (step 15)
RETRIES = 5
PAGE_DELAY = 0.3
PAGED_END_AFTER_MISSES = 2   # early jpg chapters use contiguous numbering
IMG_EXTS = (".jpg", ".jpeg", ".png", ".webp")


ANOMALIES = []


def log(msg):
    print(msg, flush=True)


def flag(kind, msg):
    ANOMALIES.append({"kind": kind, "msg": msg})
    log(f"  ! [{kind}] {msg}")


def fetch(url):
    """Return (bytes|None, status) where status in {'ok','404','err'}."""
    for a in range(RETRIES):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Referer": REFERER})
            with urllib.request.urlopen(req, timeout=30) as r:
                data = r.read()
            return (data if data and len(data) > 500 else None), ("ok" if data else "err")
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None, "404"
            time.sleep(1.0 * (a + 1) + random.random())
        except Exception:
            time.sleep(1.0 * (a + 1) + random.random())
    return None, "err"


AD_MD5 = "ed6d7bf6aa"   # the recurring 728x90 GIF ad roliascan appends as trailing .jpg pages


def is_ad_gif(data):
    import hashlib
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
        riff = struct.unpack("<I", data[4:8])[0]
        return abs((riff + 8) - len(data)) <= 2
    return True


def valid_image_bytes(path, data):
    if not end_marker_ok(path, data):
        return False
    try:
        from PIL import Image, ImageFile
        ImageFile.LOAD_TRUNCATED_IMAGES = False
        import io
        im = Image.open(io.BytesIO(data)); im.load(); im.size
        return True
    except Exception:
        return False


def local_has_valid(path):
    if not (os.path.exists(path) and os.path.getsize(path) > 500):
        return False
    with open(path, "rb") as f:
        return valid_image_bytes(path, f.read())


def save(path, data):
    tmp = path + ".part"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, path)


def cdn_key(localdir):
    """local '050' -> '50', '172.5' -> '172.5'."""
    if re.fullmatch(r"\d{3}", localdir):
        return str(int(localdir))
    if re.fullmatch(r"\d{3}\.\d+", localdir):
        w, f = localdir.split(".")
        return f"{int(w)}.{f}"
    return localdir


def detect_regime(chdir):
    """'stitched' | 'paged' from an existing page_001.* on disk."""
    for fn in sorted(os.listdir(chdir)) if os.path.isdir(chdir) else []:
        m = re.match(r"page_0*1(_stitched)?\.(jpg|jpeg|webp|png)$", fn)
        if m:
            return ("stitched", "_stitched", m.group(2)) if m.group(1) else ("paged", "", m.group(2))
    return None


def process_chapter(localdir):
    chdir = os.path.join(OUT_ROOT, localdir)
    os.makedirs(chdir, exist_ok=True)
    key = cdn_key(localdir)
    reg = detect_regime(chdir)
    if not reg:
        return {"chapter": localdir, "regime": "unknown", "skipped": True}
    regime, suffix, ext = reg

    expected, present, downloaded, missing404, bad = [], [], [], [], []
    ad_slots = []

    if regime == "stitched":
        # Strips are numbered 1,16,31,... (step 15). End = TWO consecutive 404s, so a
        # single missing strip in the middle (a real source gap) is recorded as a gap
        # and we keep going instead of truncating the chapter at the first 404.
        idx = 1
        consec404 = 0
        seen404 = []           # every 404 index (trailing ones trimmed after the loop)
        while idx <= 600:
            fn = f"page_{idx:03d}{suffix}.{ext}"
            dest = os.path.join(chdir, fn)
            if local_has_valid(dest):
                present.append(idx); expected.append(idx); consec404 = 0; idx += STRIP_STEP; continue
            data, st = fetch(STORAGE.format(mid=MANGA_ID, key=key, fn=fn))
            if st == "ok" and data:
                expected.append(idx)
                if valid_image_bytes(dest, data):
                    save(dest, data); downloaded.append(idx)
                else:
                    bad.append(idx)
                    flag("truncated", f"_{key}/{fn} downloaded but failed integrity")
                consec404 = 0
            elif st == "404":
                seen404.append(idx)
                consec404 += 1
                if consec404 >= 2:
                    break
            else:                               # transient err after retries
                bad.append(idx)
                flag("transient", f"_{key}/{fn} transient error after {RETRIES} retries")
            idx += STRIP_STEP
            time.sleep(PAGE_DELAY)
        last_real = max(expected) if expected else 0
        gaps = [i for i in seen404 if i < last_real]          # real mid-chapter holes
        missing404 = [i for i in seen404 if i >= last_real]   # past-end (the true end)
        if gaps:
            flag("source-gap", f"_{key}: missing strip(s) at {gaps} before the last strip page_{last_real:03d}")
    else:  # paged (contiguous jpg)
        p = 1
        misses = 0
        while p <= 300:
            fn = f"page_{p:03d}.{ext}"
            dest = os.path.join(chdir, fn)
            if local_has_valid(dest):
                present.append(p); expected.append(p); misses = 0; p += 1; continue
            data, st = fetch(STORAGE.format(mid=MANGA_ID, key=key, fn=fn))
            if st == "ok" and data and is_ad_gif(data):
                ad_slots.append(p)          # trailing ad banner => end of real content
                break
            if st == "ok" and data:
                expected.append(p)
                if valid_image_bytes(dest, data):
                    save(dest, data); downloaded.append(p)
                else:
                    bad.append(p)
                misses = 0
            elif st == "404":
                misses += 1
                if misses >= PAGED_END_AFTER_MISSES:
                    break
            else:
                bad.append(p)
            p += 1
            time.sleep(PAGE_DELAY)

    log(f"ch {localdir:>6} [{regime:>8}] key={key:>6}: expected={len(expected)} "
        f"present={len(present)} +downloaded={len(downloaded)} "
        f"missing404={missing404} ad_slots={ad_slots} bad={bad}")
    return {"chapter": localdir, "regime": regime, "key": key,
            "expected": expected, "present_before": present,
            "downloaded": downloaded, "cdn_404_beyond_end": missing404,
            "ad_slots": ad_slots, "bad": bad}


def main():
    dirs = sorted((d for d in os.listdir(OUT_ROOT)
                   if os.path.isdir(os.path.join(OUT_ROOT, d)) and re.match(r"\d", d)),
                  key=lambda d: float(d) if re.fullmatch(r"\d{3}(\.\d+)?", d) else 1e9)
    if len(sys.argv) > 1:
        want = set(sys.argv[1:])
        dirs = [d for d in dirs if cdn_key(d) in want or d in want]
    log(f"Completing {len(dirs)} chapters from CDN (step={STRIP_STEP}) -> {OUT_ROOT}")
    results = [process_chapter(d) for d in dirs]
    total_dl = sum(len(r.get("downloaded", [])) for r in results)
    total_bad = sum(len(r.get("bad", [])) for r in results)
    summary = {"chapters": len(dirs), "strips_downloaded": total_dl, "strips_bad": total_bad,
               "anomalies": ANOMALIES, "detail": results}
    json.dump(summary, open(os.path.join(OUT_ROOT, "_strips_manifest.json"), "w"), indent=1)
    log("=" * 60)
    log(f"DONE: {total_dl} strips downloaded, {total_bad} bad/transient, "
        f"{len(ANOMALIES)} anomalies. Manifest -> _strips_manifest.json")
    for a in ANOMALIES[:40]:
        log(f"  [{a['kind']}] {a['msg']}")


if __name__ == "__main__":
    main()
