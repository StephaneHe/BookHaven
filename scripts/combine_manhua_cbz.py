#!/usr/bin/env python3
"""Combine all downloaded manhua chapters into ONE continuous CBZ.

The user wants to read the whole manhua as a single book (chapters following
one another), not 217 separate entries. BookHaven's comic reader shows the
pages of one archive in filename order, so we pack every page of every chapter
into one CBZ with sort-safe names:

    <chapter*10 : 05d>_<page : 03d>.<ext>      e.g. 00010_001.jpg  (ch 1, page 1)
                                                    01725_001.webp (ch 172.5)
                                                    02160_006.jpg  (ch 216, page 6)

so the decimal chapter 172.5 sorts between 172 and 173 and everything reads in
order. Output: <BOOKS_ROOT>\\Comics\\Sir, Don't Show Off.cbz
"""
import os
import re
import sys
import shutil
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from manhua_adfilter import is_ad_image   # noqa: E402

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_ROOT = os.path.join(BASE_DIR, "data", "manhua", "sir-dont-show-off")
IMG_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp")
OUT_NAME = "Sir, Don't Show Off.cbz"


def books_root():
    for line in open(os.path.join(BASE_DIR, ".env"), encoding="utf-8"):
        if line.startswith("BOOKS_ROOT="):
            return line.split("=", 1)[1].strip()
    return r"H:\Books"


def chapnum(d):
    if re.fullmatch(r"\d{3}", d):
        return float(int(d))
    if re.fullmatch(r"\d{3}\.\d+", d):
        return float(d)
    return None


def main():
    dest_dir = os.path.join(books_root(), "Comics")
    os.makedirs(dest_dir, exist_ok=True)
    out_path = os.path.join(dest_dir, OUT_NAME)

    dirs = []
    for d in os.listdir(SRC_ROOT):
        cn = chapnum(d)
        if cn is not None and os.path.isdir(os.path.join(SRC_ROOT, d)):
            dirs.append((cn, d))
    dirs.sort()

    # Keep a one-time backup of the pre-clean archive.
    if os.path.exists(out_path) and not os.path.exists(out_path + ".orig"):
        shutil.copy2(out_path, out_path + ".orig")
        print(f"Backed up existing archive -> {out_path}.orig")

    total_pages = 0
    ads_removed = 0
    tmp = out_path + ".part"
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_STORED) as zf:  # images already compressed
        for cn, d in dirs:
            chdir = os.path.join(SRC_ROOT, d)
            pages = sorted(f for f in os.listdir(chdir)
                           if os.path.splitext(f)[1].lower() in IMG_EXTS)
            prefix = int(round(cn * 10))
            kept = 0
            for img in pages:
                src = os.path.join(chdir, img)
                if is_ad_image(src):        # drop ad/watermark banners
                    ads_removed += 1
                    continue
                kept += 1
                ext = os.path.splitext(img)[1].lower()
                arc = f"{prefix:05d}_{kept:03d}{ext}"   # contiguous renumbering
                zf.write(src, arcname=arc)
                total_pages += 1
    os.replace(tmp, out_path)
    size = os.path.getsize(out_path)
    print(f"Combined {len(dirs)} chapters, {total_pages} pages "
          f"({ads_removed} ad/banner pages removed) -> {out_path}")
    print(f"Size: {size/1e6:.1f} MB")


if __name__ == "__main__":
    main()
