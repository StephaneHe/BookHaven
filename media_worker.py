"""Background media enrichment worker for BookHaven.

Runs in a separate thread. Processes books missing covers/metadata:
  1. Extract cover from file (PDF/CBR/CBZ/EPUB)
  2. Search online APIs for cover + description (Open Library, Google Books)
  3. Update DB asynchronously

Uses WAL mode for concurrent DB access with the Flask app.
"""
import os
import re
import sys
import time
import hashlib
import sqlite3
import zipfile
import threading
import logging
import urllib.request
import urllib.parse
import json
from io import BytesIO

try:
    import fitz  # PyMuPDF
    HAS_FITZ = True
except ImportError:
    HAS_FITZ = False

try:
    import rarfile
    HAS_RARFILE = True
except ImportError:
    HAS_RARFILE = False

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

import config

logger = logging.getLogger("bookhaven.media")

# Configure unrar tool path for CBR extraction
if HAS_RARFILE and hasattr(config, 'UNRAR_TOOL') and os.path.exists(config.UNRAR_TOOL):
    rarfile.UNRAR_TOOL = config.UNRAR_TOOL
    logger.info(f"UnRAR tool configured: {config.UNRAR_TOOL}")

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"}

# Worker state (read by Flask for status endpoint)
worker_status = {
    "running": False,
    "phase": "idle",
    "processed": 0,
    "total": 0,
    "covers_found": 0,
    "descriptions_found": 0,
    "errors": 0,
    "current_book": "",
}


def _get_conn():
    """Get a DB connection with WAL mode for concurrent access."""
    conn = sqlite3.connect(config.DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def _save_cover(full_path, cover_data):
    """Save cover image as JPEG thumbnail. Returns True on success."""
    if not cover_data or len(cover_data) < 100:
        return False
    try:
        path_hash = hashlib.md5(full_path.encode()).hexdigest()
        cover_path = os.path.join(config.COVER_CACHE_DIR, f"{path_hash}.jpg")
        if os.path.exists(cover_path):
            return True
        os.makedirs(config.COVER_CACHE_DIR, exist_ok=True)
        if HAS_PIL:
            img = Image.open(BytesIO(cover_data))
            img.thumbnail((300, 450), Image.LANCZOS)
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            img.save(cover_path, "JPEG", quality=85)
        else:
            with open(cover_path, "wb") as f:
                f.write(cover_data)
        return True
    except Exception as e:
        logger.debug(f"Cover save error: {e}")
        return False


# ── Local cover extraction ────────────────────────────────────────────────

def _extract_pdf_cover(path):
    """Render first page of PDF as cover image."""
    if not HAS_FITZ:
        return None, 0
    try:
        doc = fitz.open(path)
        if doc.page_count == 0:
            doc.close()
            return None, 0
        page = doc[0]
        mat = fitz.Matrix(150 / 72, 150 / 72)
        pix = page.get_pixmap(matrix=mat)
        data = pix.tobytes("jpeg")
        pages = doc.page_count
        doc.close()
        return data, pages
    except Exception as e:
        logger.debug(f"PDF cover error {path}: {e}")
        return None, 0


def _extract_cbr_cover(path):
    """Extract first image from CBR archive (may be RAR or ZIP format)."""
    # Many CBR files are actually ZIP archives
    try:
        with zipfile.ZipFile(path, "r") as zf:
            images = sorted([
                n for n in zf.namelist()
                if os.path.splitext(n)[1].lower() in IMAGE_EXTS
                and not n.startswith("__MACOSX") and "/." not in n
            ])
            if images:
                return zf.read(images[0]), len(images)
    except zipfile.BadZipFile:
        pass
    except Exception as e:
        logger.debug(f"CBR/ZIP cover error {path}: {e}")

    # Fall back to RAR
    if not HAS_RARFILE:
        return None, 0
    try:
        with rarfile.RarFile(path, "r") as rf:
            images = sorted([
                n for n in rf.namelist()
                if os.path.splitext(n)[1].lower() in IMAGE_EXTS
                and not n.startswith("__MACOSX") and "/." not in n
            ])
            if images:
                return rf.read(images[0]), len(images)
    except Exception as e:
        logger.debug(f"CBR/RAR cover error {path}: {e}")
    return None, 0


def _extract_cbz_cover(path):
    """Extract first image from CBZ (ZIP) archive."""
    try:
        with zipfile.ZipFile(path, "r") as zf:
            images = sorted([
                n for n in zf.namelist()
                if os.path.splitext(n)[1].lower() in IMAGE_EXTS
                and not n.startswith("__MACOSX") and "/." not in n
            ])
            if images:
                return zf.read(images[0]), len(images)
    except Exception as e:
        logger.debug(f"CBZ cover error {path}: {e}")
    return None, 0


def _extract_epub_cover(path):
    """Extract cover from EPUB file."""
    try:
        import xml.etree.ElementTree as ET
        with zipfile.ZipFile(path, "r") as zf:
            opf_path = None
            for name in zf.namelist():
                if name.endswith(".opf"):
                    opf_path = name
                    break
            if not opf_path:
                try:
                    container = ET.fromstring(zf.read("META-INF/container.xml"))
                    ns = {"c": "urn:oasis:names:tc:opendocument:xmlns:container"}
                    rf = container.find(".//c:rootfile", ns)
                    if rf is not None:
                        opf_path = rf.get("full-path")
                except Exception:
                    pass
            if not opf_path:
                return None

            root = ET.fromstring(zf.read(opf_path))
            ns_opf = "http://www.idpf.org/2007/opf"

            # Find cover id
            cover_id = None
            for m in root.findall(f".//{{{ns_opf}}}meta"):
                if m.get("name") == "cover":
                    cover_id = m.get("content")
                    break
            if not cover_id:
                for item in root.findall(f".//{{{ns_opf}}}item"):
                    iid = (item.get("id") or "").lower()
                    href = (item.get("href") or "").lower()
                    mtype = item.get("media-type", "")
                    if ("cover" in iid or "cover" in href) and mtype.startswith("image/"):
                        cover_id = item.get("id")
                        break
            if not cover_id:
                return None

            # Resolve href
            for item in root.findall(f".//{{{ns_opf}}}item"):
                if item.get("id") == cover_id:
                    href = item.get("href")
                    if href:
                        opf_dir = os.path.dirname(opf_path)
                        for try_path in [
                            os.path.join(opf_dir, href).replace("\\", "/"),
                            href,
                        ]:
                            tp = try_path.replace("\\", "/")
                            if tp in zf.namelist():
                                return zf.read(tp)
    except Exception as e:
        logger.debug(f"EPUB cover error {path}: {e}")
    return None


def _extract_local_cover(path, fmt):
    """Try to extract cover from the file itself. Returns (cover_data, page_count)."""
    if fmt == "pdf":
        return _extract_pdf_cover(path)
    elif fmt == "cbr":
        return _extract_cbr_cover(path)
    elif fmt == "cbz":
        return _extract_cbz_cover(path)
    elif fmt == "epub":
        data = _extract_epub_cover(path)
        return data, 0
    return None, 0


# ── Online metadata lookup ────────────────────────────────────────────────

def _clean_title_for_search(title):
    """Clean a title for API search: remove series tags, years, etc."""
    t = re.sub(r"\[.*?\]", "", title)
    t = re.sub(r"\(.*?\)", "", t)
    t = re.sub(r"French\.ebook.*", "", t, flags=re.IGNORECASE)
    t = re.sub(r"\.epub$|\.pdf$|\.cbr$|\.cbz$", "", t, flags=re.IGNORECASE)
    t = re.sub(r"\d{4}", "", t)  # remove years
    t = t.replace(".", " ").replace("_", " ").replace(",", " ")
    t = re.sub(r"\s+", " ", t).strip(" -")
    return t


def _fetch_json(url, timeout=8):
    """Fetch JSON from URL with timeout."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "BookHaven/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None


def _fetch_image(url, timeout=8):
    """Fetch image bytes from URL."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "BookHaven/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except Exception:
        return None


def _search_open_library(title, author):
    """Search Open Library for book metadata.
    Returns dict with 'cover_url', 'description', or empty dict.
    """
    result = {}
    try:
        q = _clean_title_for_search(title)
        if author:
            q += " " + _clean_title_for_search(author)
        params = urllib.parse.urlencode({"q": q, "limit": 3, "fields": "key,title,author_name,cover_i,first_sentence"})
        url = f"https://openlibrary.org/search.json?{params}"
        data = _fetch_json(url)
        if not data or not data.get("docs"):
            return result

        doc = data["docs"][0]

        # Cover
        cover_id = doc.get("cover_i")
        if cover_id:
            result["cover_url"] = f"https://covers.openlibrary.org/b/id/{cover_id}-L.jpg"

        # Try to get description from work detail
        work_key = doc.get("key")
        if work_key:
            work_data = _fetch_json(f"https://openlibrary.org{work_key}.json")
            if work_data:
                desc = work_data.get("description")
                if isinstance(desc, dict):
                    desc = desc.get("value", "")
                if isinstance(desc, str) and len(desc) > 20:
                    result["description"] = desc[:2000]

        # Fallback: first_sentence
        if "description" not in result:
            fs = doc.get("first_sentence")
            if fs:
                if isinstance(fs, list):
                    fs = fs[0] if fs else ""
                if isinstance(fs, str) and len(fs) > 10:
                    result["description"] = fs

    except Exception as e:
        logger.debug(f"Open Library error: {e}")
    return result


def _search_google_books(title, author):
    """Search Google Books for metadata.
    Returns dict with 'cover_url', 'description', or empty dict.
    """
    result = {}
    try:
        q = _clean_title_for_search(title)
        if author:
            a = _clean_title_for_search(author)
            q = f"intitle:{q} inauthor:{a}"
        params = urllib.parse.urlencode({"q": q, "maxResults": 3})
        url = f"https://www.googleapis.com/books/v1/volumes?{params}"
        data = _fetch_json(url)
        if not data or not data.get("items"):
            return result

        vol = data["items"][0].get("volumeInfo", {})

        # Cover
        imgs = vol.get("imageLinks", {})
        cover_url = imgs.get("thumbnail") or imgs.get("smallThumbnail")
        if cover_url:
            # Google returns http, upgrade + remove curl param for better quality
            cover_url = cover_url.replace("http://", "https://")
            cover_url = re.sub(r"&edge=curl", "", cover_url)
            result["cover_url"] = cover_url

        # Description
        desc = vol.get("description", "")
        if desc and len(desc) > 20:
            result["description"] = desc[:2000]

    except Exception as e:
        logger.debug(f"Google Books error: {e}")
    return result


def _search_online(title, author):
    """Search multiple APIs for cover and description.
    Returns (cover_data_bytes_or_None, description_str_or_None).
    """
    cover_data = None
    description = None

    # Try Open Library first (better for French books)
    ol = _search_open_library(title, author)
    if ol.get("description"):
        description = ol["description"]
    if ol.get("cover_url"):
        cover_data = _fetch_image(ol["cover_url"])

    # If still missing, try Google Books
    if not cover_data or not description:
        gb = _search_google_books(title, author)
        if not description and gb.get("description"):
            description = gb["description"]
        if not cover_data and gb.get("cover_url"):
            cover_data = _fetch_image(gb["cover_url"])

    return cover_data, description


# ── Main worker loop ──────────────────────────────────────────────────────

def _run_enrichment():
    """Main enrichment loop. Processes all books needing covers/descriptions."""
    global worker_status
    worker_status["running"] = True
    worker_status["phase"] = "starting"

    conn = _get_conn()

    # Phase 1: Local cover extraction (fast)
    worker_status["phase"] = "local_covers"
    rows = conn.execute(
        "SELECT id, path, format, page_count, title FROM books WHERE has_cover = 0"
    ).fetchall()
    worker_status["total"] = len(rows)
    worker_status["processed"] = 0
    logger.info(f"Media worker: {len(rows)} books need covers (local extraction)")

    for row in rows:
        worker_status["processed"] += 1
        worker_status["current_book"] = (row["title"] or "")[:60]

        if not os.path.exists(row["path"]):
            worker_status["errors"] += 1
            continue

        cover_data, pages = _extract_local_cover(row["path"], row["format"])
        if cover_data and _save_cover(row["path"], cover_data):
            updates = {"has_cover": 1}
            if pages > 0 and row["page_count"] == 0:
                updates["page_count"] = pages
            conn.execute(
                "UPDATE books SET has_cover=?, page_count=? WHERE id=?",
                (1, updates.get("page_count", row["page_count"]), row["id"]),
            )
            worker_status["covers_found"] += 1

        if worker_status["processed"] % 50 == 0:
            conn.commit()

    conn.commit()
    logger.info(f"Local extraction done: {worker_status['covers_found']} covers found")

    # Phase 2: Online enrichment (slower, with rate limiting)
    worker_status["phase"] = "online_enrichment"
    rows = conn.execute(
        "SELECT id, path, title, author, format, has_cover, description FROM books "
        "WHERE (has_cover = 0 OR description = '' OR description IS NULL) "
        "AND format IN ('epub', 'pdf') "
        "ORDER BY has_cover ASC"  # prioritize books without covers
    ).fetchall()
    worker_status["total"] = len(rows)
    worker_status["processed"] = 0
    logger.info(f"Media worker: {len(rows)} books need online enrichment")

    for row in rows:
        worker_status["processed"] += 1
        worker_status["current_book"] = (row["title"] or "")[:60]

        title = row["title"]
        author = row["author"]
        if not title or len(title) < 3:
            continue

        needs_cover = row["has_cover"] == 0
        needs_desc = not row["description"]

        cover_data, description = _search_online(title, author)

        if cover_data and needs_cover and _save_cover(row["path"], cover_data):
            conn.execute("UPDATE books SET has_cover=1 WHERE id=?", (row["id"],))
            worker_status["covers_found"] += 1

        if description and needs_desc:
            conn.execute("UPDATE books SET description=? WHERE id=?", (description, row["id"]))
            worker_status["descriptions_found"] += 1

        if worker_status["processed"] % 20 == 0:
            conn.commit()

        # Rate limit: ~2 requests/sec to be polite to APIs
        time.sleep(0.5)

    conn.commit()
    conn.close()

    worker_status["phase"] = "done"
    worker_status["running"] = False
    logger.info(
        f"Enrichment complete: {worker_status['covers_found']} covers, "
        f"{worker_status['descriptions_found']} descriptions"
    )


def start_worker():
    """Start the enrichment worker in a background daemon thread."""
    t = threading.Thread(target=_run_enrichment, daemon=True, name="media-worker")
    t.start()
    logger.info("Media enrichment worker started")
    return t


def get_status():
    """Return current worker status dict."""
    return dict(worker_status)
