#!/usr/bin/env python3
"""Package downloaded manhua chapters into per-chapter CBZ files for BookHaven.

BookHaven already reads CBZ comics (config.SUPPORTED_FORMATS) and groups them
into a series by their parent folder, ordering chapters by series_index (parsed
from a leading "NNN - " in the filename). So we drop one CBZ per chapter into

    <BOOKS_ROOT>\\Comics\\Sir, Don't Show Off\\NNN - Chapter N.cbz

The decimal chapter 172.5 is named "172 - Chapter 172.5.cbz": it gets the same
series_index as 172, and the (series_index, title) sort places "Chapter 172.5"
right after "Chapter 172" and before 173 — correct order without touching the DB.

Idempotent: rewrites a chapter's CBZ only when its page set changed.
"""
import os
import re
import sys
import json
import zipfile

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_ROOT = os.path.join(BASE_DIR, "data", "manhua", "sir-dont-show-off")
SERIES_DIR_NAME = "Sir, Don't Show Off"
IMG_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp")


def books_root():
    # Read BOOKS_ROOT from the app config (honours .env) without importing Flask.
    for line in open(os.path.join(BASE_DIR, ".env"), encoding="utf-8"):
        if line.startswith("BOOKS_ROOT="):
            return line.split("=", 1)[1].strip()
    return r"H:\Books"


def chapter_from_dirname(d):
    """'001' -> ('1', '001'), '172.5' -> ('172.5', '172.5')."""
    if re.fullmatch(r"\d{3}", d):
        return str(int(d)), d
    if re.fullmatch(r"\d{3}\.\d+", d):
        whole, frac = d.split(".")
        return f"{int(whole)}.{frac}", d
    return None, d


def cbz_name(num):
    if "." in num:
        whole = num.split(".")[0]
        return f"{int(whole):03d} - Chapter {num}.cbz"
    return f"{int(num):03d} - Chapter {num}.cbz"


def page_images(chdir):
    return sorted(f for f in os.listdir(chdir)
                  if os.path.splitext(f)[1].lower() in IMG_EXTS)


def needs_rebuild(cbz_path, images):
    if not os.path.exists(cbz_path):
        return True
    try:
        with zipfile.ZipFile(cbz_path) as zf:
            return zf.namelist() != images
    except Exception:
        return True


def main():
    dest_dir = os.path.join(books_root(), "Comics", SERIES_DIR_NAME)
    os.makedirs(dest_dir, exist_ok=True)
    built = skipped = empty = 0
    total_pages = 0
    report = []

    dirs = sorted(d for d in os.listdir(SRC_ROOT)
                  if os.path.isdir(os.path.join(SRC_ROOT, d)))
    for d in dirs:
        num, _pad = chapter_from_dirname(d)
        if num is None:
            continue
        chdir = os.path.join(SRC_ROOT, d)
        images = page_images(chdir)
        if not images:
            empty += 1
            report.append({"chapter": num, "pages": 0, "cbz": None})
            continue
        cbz_path = os.path.join(dest_dir, cbz_name(num))
        total_pages += len(images)
        if not needs_rebuild(cbz_path, images):
            skipped += 1
            report.append({"chapter": num, "pages": len(images),
                           "cbz": os.path.basename(cbz_path), "status": "cached"})
            continue
        tmp = cbz_path + ".part"
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_STORED) as zf:  # images already compressed
            for img in images:
                zf.write(os.path.join(chdir, img), arcname=img)
        os.replace(tmp, cbz_path)
        built += 1
        report.append({"chapter": num, "pages": len(images),
                       "cbz": os.path.basename(cbz_path), "status": "built"})
        print(f"ch {num:>6}: {len(images):>3} pages -> {os.path.basename(cbz_path)}", flush=True)

    summary = {"dest": dest_dir, "chapters_built": built, "chapters_cached": skipped,
               "chapters_empty": empty, "total_pages": total_pages,
               "empty_chapters": [r["chapter"] for r in report if r["pages"] == 0]}
    json.dump({"summary": summary, "chapters": report},
              open(os.path.join(SRC_ROOT, "_cbz_manifest.json"), "w"), indent=2)
    print("=" * 60)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
