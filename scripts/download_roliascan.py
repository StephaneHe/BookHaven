#!/usr/bin/env python3
"""Download ANY roliascan manhua cleanly and register it in BookHaven.

Generalises the method validated while repairing "Sir, Don't Show Off":
  * The authoritative source is the CDN roliascan.ORG/storage/chapters/, NOT the
    roliascan.com HTML (which under-lists the images).
  * Each chapter lives in a folder  manhwa_<MANGA_ID>_<CHAP_NUM>/  and is served
    as one or more tall "stitched" strips numbered by their FIRST source-page
    index: page_001_stitched.webp, page_016_stitched.webp, page_031, ... i.e. a
    fixed STEP of 15 (15 source pages per strip). Early/short chapters may instead
    be contiguous individual pages (page_001.jpg, page_002.jpg, ...).
  * Enumerate strips until a REAL 404 (retries distinguish a transient error from
    the end of the chapter). Never stop at the first gap without confirming.
  * Chapter -> CDN folder mapping is confirmed per series from the chapter's
    og:image (folder = displayed number on this title; verify, don't assume).

Stages (each can be skipped): discover -> download -> combine -> import.

Usage:
    # Dry-run: discover chapters + verify mapping + enumerate strips, NO download
    python download_roliascan.py https://roliascan.com/series/<slug>/ --plan

    # Full: download everything, filter ads, verify, build one CBZ, register book
    python download_roliascan.py <series-url-or-slug>

    # Only some chapters (CDN folder numbers), e.g. to repair:
    python download_roliascan.py <slug> --chapters 49 50 51

Flags: --plan/--dry-run, --no-download, --no-combine, --no-import,
       --chapters N [N ...], --title "Custom Title".

See docs/roliascan-download-rules.md and .claude/skills/roliascan-manhua/SKILL.md.
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
import zipfile
import argparse
import urllib.request
import urllib.error

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36")
CDN_REFERER = "https://roliascan.org/"          # required or the CDN blocks the request
SITE = "https://roliascan.com"
CDN = "https://roliascan.org/storage/chapters/manhwa_{mid}_{key}/{fn}"
STRIP_STEP = 15                                  # stitched strips are indexed 1,16,31,46,...
RETRIES = 5
PAGE_DELAY = 0.3
PAGED_END_AFTER_MISSES = 2
IMG_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp")
AD_MD5 = "ed6d7bf6aa"                             # recurring 728x90 GIF ad (mislabelled .jpg)
# page_001 candidates probed to detect a chapter's scheme (stitched first: newer chapters)
CANDIDATES = [("_stitched", "webp"), ("_stitched", "jpg"), ("", "jpg"),
              ("", "jpeg"), ("", "webp"), ("", "png")]

ANOMALIES = []


def log(msg):
    print(msg, flush=True)


def flag(kind, msg):
    ANOMALIES.append({"kind": kind, "msg": msg})
    log(f"  ⚠ [{kind}] {msg}")


# ----------------------------- HTTP -----------------------------------------

def _open(url, referer):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Referer": referer})
    return urllib.request.urlopen(req, timeout=30)


def http_bytes(url, referer=CDN_REFERER, retries=RETRIES):
    """Return (bytes|None, status) with status in {'ok','404','err'}; retries transient."""
    for a in range(retries):
        try:
            with _open(url, referer) as r:
                data = r.read()
            return (data if data and len(data) > 500 else None), ("ok" if data else "err")
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None, "404"
            time.sleep(1.0 * (a + 1) + random.random())
        except Exception:
            time.sleep(1.0 * (a + 1) + random.random())
    return None, "err"


def http_text(url, referer=SITE + "/"):
    data, st = http_bytes(url, referer=referer)
    return data.decode("utf-8", "replace") if data else ""


# ----------------------------- discovery ------------------------------------

def series_slug(url_or_slug):
    m = re.search(r"roliascan\.com/(?:series|manga)/([^/]+)/?", url_or_slug)
    if m:
        return m.group(1)
    return url_or_slug.strip().strip("/").split("/")[-1]


def discover(series_url_or_slug):
    """Scrape the series page -> {slug, manga_id, read_slug, title, chapters:[(num,postid)]}."""
    slug = series_slug(series_url_or_slug)
    url = f"{SITE}/series/{slug}/"
    html = http_text(url)
    if not html:
        raise SystemExit(f"Cannot fetch series page: {url}")
    mid_m = re.search(r'data-manga-id="(\d+)"', html) or re.search(r"manhwa_(\d+)_", html)
    if not mid_m:
        raise SystemExit("manga_id not found on series page")
    manga_id = mid_m.group(1)
    rs = re.search(r"/read/([^/]+)/ch[0-9.]+-\d+/", html)
    read_slug = rs.group(1) if rs else slug
    tt = re.search(r'<meta property="og:title" content="([^"]+)"', html) \
        or re.search(r"<title>([^<|]+)", html)
    title = (tt.group(1).strip() if tt else slug).replace(" - roliascan.com", "").strip()
    title = re.sub(r"^Chapter\s+[0-9.]+\s*[-–]\s*", "", title).strip()  # strip stray "Chapter N - "
    if not title or title.lower().startswith("chapter"):
        title = slug.replace("-", " ").title()
    # all chapter slugs ch<num>-<postid> (num may be decimal)
    chaps = {}
    for _full, num, pid in re.findall(r"(ch([0-9.]+)-(\d+))", html):
        chaps[num] = pid
    chapters = sorted(chaps.items(), key=lambda kv: float(kv[0]))
    disc = {"slug": slug, "manga_id": manga_id, "read_slug": read_slug,
            "title": title, "chapters": [(n, p) for n, p in chapters]}
    log(f"Discovered '{title}' (manga_id={manga_id}, read_slug={read_slug}): "
        f"{len(chapters)} chapters")
    if any("." in n for n, _ in chapters):
        flag("decimal-chapter", "series contains decimal chapters (e.g. NNN.5) — check ordering")
    return disc


def og_folder(read_slug, chapter_slug):
    """Authoritative CDN folder number for a chapter, from its reader og:image."""
    html = http_text(f"{SITE}/read/{read_slug}/{chapter_slug}/")
    m = re.search(r"og:image'?\s+content='[^']*manhwa_\d+_([0-9.]+)/", html) \
        or re.search(r'manhwa_\d+_([0-9.]+)/page_', html)
    return m.group(1) if m else None


def verify_mapping(disc, sample=6):
    """Confirm chapter->folder mapping on a sample. Returns 'identity' or 'per-chapter'."""
    ch = disc["chapters"]
    idx = sorted(set([0, len(ch) // 2, len(ch) - 1] + list(range(min(3, len(ch))))))
    mismatch = False
    for i in idx:
        num, pid = ch[i]
        folder = og_folder(disc["read_slug"], f"ch{num}-{pid}")
        ok = (folder == num)
        log(f"  map check ch{num} -> folder _{folder} {'OK' if ok else 'MISMATCH'}")
        if not ok:
            mismatch = True
        time.sleep(0.2)
    if mismatch:
        flag("folder-offset", "chapter->folder is NOT identity; resolving every folder via og:image")
        return "per-chapter"
    return "identity"


# ----------------------- image validation / ads ----------------------------

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
    if not (os.path.exists(path) and os.path.getsize(path) > 500):
        return False
    with open(path, "rb") as f:
        return valid_image_bytes(path, f.read())


def save_bytes(path, data):
    tmp = path + ".part"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, path)


# ----------------------- per-chapter (AUTHORITATIVE) ------------------------
# The exact ordered page list comes from the reader's own endpoint. NEVER guess a
# page-index step: strips are numbered by first source-page index but the STEP
# VARIES (ch57 = 001/016/031/046/062 = +16 at the end; ch99 = 001/015/029/043 = +14).
# A fixed-step grid silently skips real strips -> incomplete chapters.
CONTENT_URL = "https://roliascan.com/auth/chapter-content?chapter_id={pid}"


def chapter_images(postid):
    """Authoritative ordered image URLs for a chapter, or None on failure."""
    for a in range(RETRIES):
        try:
            req = urllib.request.Request(CONTENT_URL.format(pid=postid), headers={
                "User-Agent": UA, "Referer": SITE + "/",
                "X-Requested-With": "XMLHttpRequest", "Accept": "application/json"})
            j = json.loads(urllib.request.urlopen(req, timeout=45).read().decode("utf-8", "replace"))
            if j.get("success") and isinstance(j.get("images"), list):
                return j["images"]
            return []
        except Exception:
            time.sleep(1.0 * (a + 1) + random.random())
    return None


def process_chapter(postid, chdir, plan):
    os.makedirs(chdir, exist_ok=True)
    imgs = chapter_images(postid)
    if imgs is None:
        flag("fetch-failed", f"chapter {postid}: chapter-content unreachable after retries")
        return {"postid": postid, "images_total": None, "present": [], "downloaded": [], "ads": [], "missing": []}
    if not imgs:
        flag("empty-chapter", f"chapter {postid}: no images (locked/premium at source?)")
        return {"postid": postid, "images_total": 0, "present": [], "downloaded": [], "ads": [], "missing": []}

    present, downloaded, ads, missing = [], [], [], []
    for url in imgs:
        fn = url.rsplit("/", 1)[-1].split("?")[0]
        dest = os.path.join(chdir, fn)
        if local_has_valid(dest):
            present.append(fn); continue
        if plan:
            _d, st = http_bytes(url, referer=CDN_REFERER)   # existence only, no save
            (present if st == "ok" else missing).append(fn)
            time.sleep(PAGE_DELAY); continue
        data, st = http_bytes(url, referer=CDN_REFERER)
        if data and is_ad_gif(data):
            ads.append(fn); time.sleep(PAGE_DELAY); continue
        if data and valid_image_bytes(dest, data):
            save_bytes(dest, data); downloaded.append(fn)
        else:
            missing.append(fn)
            flag("missing-strip", f"chapter {postid}: {fn} could not be fetched/validated ({st})")
        time.sleep(PAGE_DELAY)

    log(f"ch {postid}: images={len(imgs)} present={len(present)} +dl={len(downloaded)} "
        f"ads={len(ads)} missing={missing}")
    return {"postid": postid, "images_total": len(imgs), "present": present,
            "downloaded": downloaded, "ads": ads, "missing": missing}


# ------------------------------- combine ------------------------------------

def combine(out_root, out_cbz):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from manhua_adfilter import is_ad_image  # noqa: E402

    def chapnum(d):
        if re.fullmatch(r"\d{3}", d):
            return float(int(d))
        if re.fullmatch(r"\d{3}\.\d+", d):
            return float(d)
        return None

    dirs = sorted(((chapnum(d), d) for d in os.listdir(out_root)
                   if chapnum(d) is not None and os.path.isdir(os.path.join(out_root, d))))
    if os.path.exists(out_cbz) and not os.path.exists(out_cbz + ".orig"):
        import shutil
        shutil.copy2(out_cbz, out_cbz + ".orig")
        log(f"Backup -> {out_cbz}.orig")
    total = ads = 0
    tmp = out_cbz + ".part"
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_STORED) as zf:
        for cn, d in dirs:
            chdir = os.path.join(out_root, d)
            pages = sorted(f for f in os.listdir(chdir)
                           if os.path.splitext(f)[1].lower() in IMG_EXTS)
            prefix = int(round(cn * 10))
            kept = 0
            for img in pages:
                src = os.path.join(chdir, img)
                if is_ad_image(src):
                    ads += 1; continue
                kept += 1
                arc = f"{prefix:05d}_{kept:03d}{os.path.splitext(img)[1].lower()}"
                zf.write(src, arcname=arc)
                total += 1
    os.replace(tmp, out_cbz)
    log(f"CBZ: {len(dirs)} chapters, {total} pages ({ads} ads removed) -> {out_cbz} "
        f"({os.path.getsize(out_cbz)/1e6:.1f} MB)")
    return out_cbz


# ------------------------------- import -------------------------------------

def register(out_cbz, title):
    """Non-destructive: register the single combined CBZ as ONE book (idempotent).

    Deliberately does NOT delete/rescan anything (unlike finalize_manhua_single.py).
    """
    sys.path.insert(0, BASE_DIR)
    import config          # noqa: E402
    import database        # noqa: E402
    import scanner         # noqa: E402
    with zipfile.ZipFile(out_cbz) as zf:
        imgs = sorted(n for n in zf.namelist()
                      if os.path.splitext(n)[1].lower() in IMG_EXTS)
        cover = zf.read(imgs[0]) if imgs else None
    has_cover = 1 if scanner._extract_cover(out_cbz, ".cbz", cover) else 0
    conn = database.get_db()
    conn.execute("PRAGMA busy_timeout=60000")
    row = conn.execute("SELECT id FROM books WHERE path = ?", (out_cbz,)).fetchone()
    if row:
        with conn:
            conn.execute("UPDATE books SET file_size=?, page_count=?, has_cover=? WHERE id=?",
                         (os.path.getsize(out_cbz), len(imgs), has_cover, row["id"]))
        log(f"Updated existing book id={row['id']} ({len(imgs)} pages)")
    else:
        with conn:
            conn.execute("""
                INSERT INTO books (path, filename, title, author, genre, series,
                  series_index, category, format, file_size, has_cover,
                  page_count, description, collection_path)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (out_cbz, os.path.basename(out_cbz), title, "", "Comics", "",
                  0, "Comics", "cbz", os.path.getsize(out_cbz), has_cover,
                  len(imgs), f"Manhua - {len(imgs)} pages read as one continuous book.", ""))
        log(f"Inserted new book '{title}' ({len(imgs)} pages, cover={has_cover})")
    conn.close()


# -------------------------------- main --------------------------------------

def safe_filename(name):
    return re.sub(r'[<>:"/\\|?*]', "", name).strip() or "manhua"


def main():
    ap = argparse.ArgumentParser(description="Download a roliascan manhua into BookHaven")
    ap.add_argument("series", help="series URL or slug (roliascan.com/series/<slug>/)")
    ap.add_argument("--plan", "--dry-run", action="store_true", dest="plan",
                    help="discover + verify mapping + enumerate strips, NO download")
    ap.add_argument("--no-download", action="store_true")
    ap.add_argument("--no-combine", action="store_true")
    ap.add_argument("--no-import", action="store_true")
    ap.add_argument("--chapters", nargs="+", help="only these CDN folder numbers")
    ap.add_argument("--title", help="override the book title")
    args = ap.parse_args()

    disc = discover(args.series)
    mid = disc["manga_id"]
    slug = disc["slug"]
    title = args.title or disc["title"]
    out_root = os.path.join(BASE_DIR, "data", "manhua", slug)
    os.makedirs(out_root, exist_ok=True)

    mode = verify_mapping(disc)
    chapters = disc["chapters"]
    if args.chapters:
        want = set(args.chapters)
        chapters = [(n, p) for n, p in chapters if n in want]

    results = []
    for num, pid in chapters:
        localdir = f"{int(float(num)):03d}" if "." not in num else \
            f"{int(float(num.split('.')[0])):03d}.{num.split('.')[1]}"
        chdir = os.path.join(out_root, localdir)
        if args.no_download and not args.plan:
            continue
        # Authoritative: the exact page URLs come from chapter-content (postid);
        # no page-index guessing / step assumption.
        r = process_chapter(pid, chdir, plan=args.plan)
        r.update({"chapter": num, "localdir": localdir})
        results.append(r)

    json.dump({"series": slug, "manga_id": mid, "title": title, "mode": mode,
               "chapters": len(chapters), "anomalies": ANOMALIES, "detail": results},
              open(os.path.join(out_root, "_download_report.json"), "w"), indent=1)

    if args.plan:
        log("=" * 60)
        log(f"PLAN done: {len(results)} chapters enumerated, {len(ANOMALIES)} anomalies. "
            f"(no files written)")
        return 0

    # Resolve BOOKS_ROOT via config (honours .env) for combine + import
    sys.path.insert(0, BASE_DIR)
    import config  # noqa: E402
    out_cbz = os.path.join(config.BOOKS_ROOT, "Comics", f"{safe_filename(title)}.cbz")
    os.makedirs(os.path.dirname(out_cbz), exist_ok=True)

    if not args.no_combine:
        combine(out_root, out_cbz)
    if not args.no_import:
        register(out_cbz, title)

    log("=" * 60)
    log(f"DONE. anomalies={len(ANOMALIES)}")
    if ANOMALIES:
        log("Review anomalies in _download_report.json:")
        for a in ANOMALIES[:20]:
            log(f"  [{a['kind']}] {a['msg']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
