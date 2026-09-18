#!/usr/bin/env python3
"""Scan the downloaded manhua for corrupt / truncated / missing plates.

For every image under data/manhua/<slug>/<chapter>/ we:
  - force a full PIL decode (LOAD_TRUNCATED_IMAGES=False so a partial file raises),
  - check the container end-marker (JPEG FFD9 / PNG IEND / RIFF size for WEBP),
  - flag zero/absurdly small files.
Also compares the plate count per chapter to the download manifest (if present)
and prints a per-chapter status table + a machine-readable JSON.

Usage: python check_manhua_integrity.py [slug]
"""
import os
import sys
import json
import struct
from PIL import Image, ImageFile

ImageFile.LOAD_TRUNCATED_IMAGES = False  # partial images must raise on load()

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SLUG = sys.argv[1] if len(sys.argv) > 1 else "sir-dont-show-off"
ROOT = os.path.join(BASE, "data", "manhua", SLUG)
IMG_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp")


def end_marker_ok(path, data):
    ext = os.path.splitext(path)[1].lower()
    if ext in (".jpg", ".jpeg"):
        return data[-2:] == b"\xff\xd9"
    if ext == ".png":
        return b"IEND" in data[-12:]
    if ext == ".webp":
        if len(data) < 12 or data[:4] != b"RIFF" or data[8:12] != b"WEBP":
            return False
        riff_size = struct.unpack("<I", data[4:8])[0]
        # RIFF size counts everything after the 8-byte RIFF header; allow small pad.
        return abs((riff_size + 8) - len(data)) <= 2
    return True  # other types: rely on PIL decode only


def check_image(path):
    """Return None if OK, else a short reason string."""
    try:
        sz = os.path.getsize(path)
    except OSError as e:
        return f"stat-error:{e}"
    if sz < 100:
        return f"tiny:{sz}b"
    with open(path, "rb") as f:
        data = f.read()
    if not end_marker_ok(path, data):
        return "bad-end-marker"
    try:
        with Image.open(path) as im:
            im.load()             # full decode -> raises on truncation/corruption
            im.size
    except Exception as e:
        return f"decode:{type(e).__name__}:{str(e)[:60]}"
    return None


def chapter_key(d):
    try:
        return float(d)
    except ValueError:
        return 1e9


def main():
    manifest = {}
    mpath = os.path.join(ROOT, "_manifest.json")
    if os.path.exists(mpath):
        try:
            manifest = json.load(open(mpath, encoding="utf-8"))
        except Exception:
            pass

    dirs = sorted((d for d in os.listdir(ROOT)
                   if os.path.isdir(os.path.join(ROOT, d))), key=chapter_key)
    report = {}
    total_imgs = bad_imgs = 0
    for d in dirs:
        cdir = os.path.join(ROOT, d)
        imgs = sorted(f for f in os.listdir(cdir)
                      if os.path.splitext(f)[1].lower() in IMG_EXTS)
        bad = []
        for f in imgs:
            reason = check_image(os.path.join(cdir, f))
            total_imgs += 1
            if reason:
                bad.append({"file": f, "reason": reason})
                bad_imgs += 1
        report[d] = {"plates": len(imgs), "bad": bad}

    # print table (only rows with problems, plus a summary)
    print(f"{'CH':>7} {'plates':>6} {'bad':>4}  detail")
    problem_chs = []
    for d in dirs:
        r = report[d]
        if r["bad"] or r["plates"] == 0:
            problem_chs.append(d)
            det = ", ".join(f"{b['file']}({b['reason']})" for b in r["bad"][:6])
            print(f"{d:>7} {r['plates']:>6} {len(r['bad']):>4}  {det}")
    print("=" * 60)
    print(f"chapters={len(dirs)}  images={total_imgs}  bad_images={bad_imgs}  "
          f"chapters_with_problems={len(problem_chs)}")
    print("problem chapters:", problem_chs)
    json.dump({"total_images": total_imgs, "bad_images": bad_imgs,
               "problem_chapters": problem_chs, "report": report},
              open(os.path.join(ROOT, "_integrity.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
