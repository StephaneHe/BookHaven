"""BookHaven - Book reader web server for Jellyfin integration."""
import os
import re
import sys
import json
import time
import uuid
import shutil
import zipfile
import hashlib
import logging
import threading
import mimetypes
import traceback
from functools import wraps
from io import BytesIO

from flask import (
    Flask, request, jsonify, send_file, send_from_directory,
    render_template, session, abort, Response
)

try:
    import rarfile
    HAS_RARFILE = True
except ImportError:
    HAS_RARFILE = False

try:
    import requests as http_requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

import config
import database
import scanner
import media_worker

__version__ = "1.2.47"

# Configure unrar tool for CBR support
if HAS_RARFILE:
    import config as _cfg
    if hasattr(_cfg, 'UNRAR_TOOL') and os.path.exists(_cfg.UNRAR_TOOL):
        rarfile.UNRAR_TOOL = _cfg.UNRAR_TOOL

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(os.path.join(os.path.dirname(__file__), "bookhaven.log"), encoding="utf-8"),
    ]
)
logger = logging.getLogger("bookhaven")

# ── Flask App ────────────────────────────────────────────────────────────────
app = Flask(__name__, static_folder="static", template_folder="templates")
app.secret_key = config.SECRET_KEY
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Test mode: bypass Jellyfin auth for automated testing
TEST_MODE = os.environ.get("BOOKHAVEN_TEST_MODE", "0") == "1"
if TEST_MODE:
    logger.warning("** TEST MODE ACTIVE - auth bypass enabled **")

@app.route("/isAlive")
def is_alive():
    """Liveness probe for the dashboard service monitor."""
    return jsonify({"ok": True, "service": "bookhaven", "ts": int(time.time())}), 200

@app.route("/api/test-login", methods=["POST"])
def test_login():
    """Test-only endpoint to establish a session without Jellyfin."""
    if not TEST_MODE:
        return jsonify({"error": "Not in test mode"}), 403
    session["user_id"] = "test-user"
    session["user_name"] = "TestUser"
    return jsonify({"ok": True, "user": "TestUser"})

# Image extensions for comic page serving
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"}

# Characters that are illegal in a Windows filename, plus control chars.
_UNSAFE_FILENAME_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
# Device names Windows reserves regardless of extension.
_WINDOWS_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def _safe_filename(name):
    """Return a filesystem-safe basename, or '' if nothing usable remains.

    werkzeug's secure_filename() is not usable here: it ASCII-folds the name,
    which reduces non-Latin titles (CJK, Cyrillic, Greek) to an empty string
    and makes those uploads impossible. We only need to neutralise path
    traversal and illegal characters, so Unicode is preserved as-is.
    """
    if not name:
        return ""
    # Drop any directory component, whichever separator was used.
    name = name.replace("\\", "/").split("/")[-1]
    name = _UNSAFE_FILENAME_RE.sub("_", name)
    # Windows silently strips trailing dots/spaces; do it explicitly so the
    # name we validate is the name that lands on disk.
    name = name.strip(" .")
    # Nothing but replacement characters left means the name carried no
    # usable content at all.
    if not name or not name.strip("_"):
        return ""
    if os.path.splitext(name)[0].upper() in _WINDOWS_RESERVED:
        name = "_" + name
    return name[:200]

# Scan state (simple in-memory tracking)
scan_state = {"running": False, "current": 0, "total": 0, "message": "", "cancel": False}

# Pending uploads awaiting confirmation (upload_id -> upload_info)
_pending_uploads = {}

# No-cover SVG placeholder (served inline, no file needed)
NO_COVER_SVG = '''<svg xmlns="http://www.w3.org/2000/svg" width="200" height="300" viewBox="0 0 200 300">
<rect width="200" height="300" fill="#2a2a3e"/>
<text x="100" y="140" text-anchor="middle" fill="#666" font-family="Arial" font-size="16">No Cover</text>
<text x="100" y="180" text-anchor="middle" fill="#555" font-family="Arial" font-size="40">📖</text>
</svg>'''

def _resolve_book_path(path):
    """Return the real filesystem path for a book.

    Paths stored before the standalone migration used ``/books`` as the root.
    This function remaps those legacy paths to the current BOOKS_ROOT.
    WSL paths of the form /mnt/X/... are translated to X:\... for Windows.
    If the path already exists on disk it is returned unchanged.
    """
    if not path:
        return path
    if os.path.exists(path):
        return path
    # Translate WSL DrvFs paths (/mnt/h/...) to Windows paths (H:\...) when
    # running under Windows Python with a DB populated from WSL.
    import re as _re
    _wsl = _re.match(r'^/mnt/([a-zA-Z])(/.*)$', path)
    if _wsl:
        candidate = _wsl.group(1).upper() + ":" + _wsl.group(2).replace("/", os.sep)
        if os.path.exists(candidate):
            return candidate
    _LEGACY_PREFIX = "/books"
    if path.startswith(_LEGACY_PREFIX + "/") or path == _LEGACY_PREFIX:
        suffix = path[len(_LEGACY_PREFIX):]  # starts with "/"
        candidate = config.BOOKS_ROOT.rstrip("/\\") + suffix.replace("/", os.sep)
        if os.path.exists(candidate):
            return candidate
    return path


def _migrate_legacy_paths():
    """Update any /books/... DB paths to current BOOKS_ROOT paths in-place.

    Also renames cover cache files from the old /books/... hash to the new
    BOOKS_ROOT hash so covers remain visible after migration.
    """
    _LEGACY_PREFIX = "/books"
    conn = database.get_db()
    rows = conn.execute(
        "SELECT id, path FROM books WHERE path LIKE ?", (_LEGACY_PREFIX + "/%",)
    ).fetchall()
    updated = 0
    covers_renamed = 0
    for row in rows:
        new_path = _resolve_book_path(row["path"])
        if new_path != row["path"] and os.path.exists(new_path):
            conn.execute("UPDATE books SET path = ? WHERE id = ?", (new_path, row["id"]))
            updated += 1
            # Rename the cover cache file to match new path hash
            old_hash = hashlib.md5(row["path"].encode()).hexdigest()
            new_hash = hashlib.md5(new_path.encode()).hexdigest()
            old_cover = os.path.join(config.COVER_CACHE_DIR, f"{old_hash}.jpg")
            new_cover = os.path.join(config.COVER_CACHE_DIR, f"{new_hash}.jpg")
            if os.path.exists(old_cover) and not os.path.exists(new_cover):
                try:
                    os.rename(old_cover, new_cover)
                    covers_renamed += 1
                except OSError:
                    pass
    if updated:
        conn.commit()
        logger.info(f"Migrated {updated} legacy /books/... paths to {config.BOOKS_ROOT}"
                    f" ({covers_renamed} cover files renamed)")
    conn.close()


def _base_filename(filename):
    """Strip extension to get base filename for grouping multi-format variants."""
    return re.sub(r'\.(epub|pdf|cbr|cbz|mobi)$', '', filename, flags=re.IGNORECASE)


def _group_format_variants(books):
    """Group books by base filename + parent folder. Returns deduplicated list with formats array."""
    FORMAT_PRIORITY = {'epub': 0, 'cbz': 1, 'cbr': 2, 'pdf': 3, 'mobi': 4}
    groups = {}
    for b in books:
        base = _base_filename(b['filename'])
        # Use grandparent folder to group sibling folders (CBR/ and PDF/ under same parent)
        path = b.get('path', '')
        parent = os.path.dirname(path)
        grandparent = os.path.dirname(parent)
        key = (base, grandparent)
        if key not in groups:
            groups[key] = []
        groups[key].append(b)

    result = []
    for key, variants in groups.items():
        variants.sort(key=lambda v: FORMAT_PRIORITY.get(v['format'], 9))
        primary = dict(variants[0])
        primary['formats'] = [{'id': v['id'], 'format': v['format']} for v in variants]
        result.append(primary)
    return result



def _base_filename(filename):
    """Strip extension to get base filename for grouping multi-format variants."""
    return re.sub(r'\.(epub|pdf|cbr|cbz|mobi)$', '', filename, flags=re.IGNORECASE)


FORMAT_PRIORITY = {'epub': 0, 'cbz': 1, 'cbr': 2, 'pdf': 3, 'mobi': 4}


def _group_format_variants(books):
    """Group books sharing the same base filename into one entry with a formats array.
    Returns a deduplicated list; each item keeps the best-format copy as primary."""
    from collections import OrderedDict
    groups = OrderedDict()
    for b in books:
        base = _base_filename(b['filename'])
        if base not in groups:
            groups[base] = []
        groups[base].append(b)

    result = []
    for base, variants in groups.items():
        variants.sort(key=lambda v: FORMAT_PRIORITY.get(v['format'], 9))
        primary = dict(variants[0])
        primary['formats'] = [{'id': v['id'], 'format': v['format']} for v in variants]
        result.append(primary)
    return result




# ── Auth helpers ─────────────────────────────────────────────────────────────

def login_required(f):
    """Decorator to require authentication."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if TEST_MODE and "user_id" not in session:
            session["user_id"] = "test-user"
            session["user_name"] = "TestUser"
        if "user_id" not in session:
            return jsonify({"error": "Authentication required"}), 401
        return f(*args, **kwargs)
    return decorated


# ── API: Authentication ──────────────────────────────────────────────────────

@app.route("/api/auth/login", methods=["POST"])
def api_login():
    """Log in by selecting a user (no password required)."""
    data = request.get_json()
    username = data.get("username", "")

    conn = database.get_db()
    user = conn.execute("SELECT id, name FROM users WHERE name = ?", (username,)).fetchone()
    if not user:
        conn.close()
        return jsonify({"error": "User not found"}), 401

    session["user_id"] = user["id"]
    session["user_name"] = user["name"]
    conn.close()
    return jsonify({
        "ok": True,
        "user_id": session["user_id"],
        "user_name": session["user_name"],
    })


@app.route("/api/auth/logout", methods=["POST"])
def api_logout():
    session.clear()
    return jsonify({"ok": True})


@app.route("/api/auth/me")
def api_me():
    """Check current session."""
    if TEST_MODE and "user_id" not in session:
        session["user_id"] = "test-user"
        session["user_name"] = "TestUser"
    if "user_id" in session:
        return jsonify({
            "ok": True,
            "user_id": session["user_id"],
            "user_name": session["user_name"],
        })
    return jsonify({"ok": False}), 401


@app.route("/api/auth/users")
def api_users():
    """Get local user list."""
    conn = database.get_db()
    users = [{"id": r["id"], "name": r["name"]} for r in
             conn.execute("SELECT id, name FROM users ORDER BY name").fetchall()]
    conn.close()
    return jsonify(users)


@app.route("/api/auth/users", methods=["POST"])
def api_create_user():
    """Create a new user."""
    data = request.get_json()
    name = data.get("name", "").strip()
    if not name:
        return jsonify({"error": "Name is required"}), 400
    import uuid
    user_id = uuid.uuid4().hex
    conn = database.get_db()
    try:
        conn.execute("INSERT INTO users (id, name) VALUES (?, ?)", (user_id, name))
        conn.commit()
    except Exception:
        conn.close()
        return jsonify({"error": "User already exists"}), 409
    conn.close()
    return jsonify({"ok": True, "id": user_id, "name": name})


# ── API: Library ─────────────────────────────────────────────────────────────

@app.route("/api/books")
@login_required
def api_books():
    """List books with optional filters."""
    try:
        conn = database.get_db()

        category = request.args.get("category", "")
        genre = request.args.get("genre", "")
        author = request.args.get("author", "")
        fmt = request.args.get("format", "")
        search = request.args.get("search", "")
        sort = request.args.get("sort", "title")
        page = int(request.args.get("page", 1))
        per_page = int(request.args.get("per_page", 50))

        query = "SELECT * FROM books WHERE 1=1"
        params = []

        if category:
            query += " AND category = ?"
            params.append(category)
        if genre:
            query += " AND genre LIKE ?"
            params.append(f"%{genre}%")
        if author:
            query += " AND author LIKE ?"
            params.append(f"%{author}%")
        if fmt:
            query += " AND format = ?"
            params.append(fmt)
        if search:
            query += " AND (title LIKE ? OR author LIKE ? OR series LIKE ?)"
            params.extend([f"%{search}%"] * 3)

        # Count total
        count_query = query.replace("SELECT *", "SELECT COUNT(*)")
        total = conn.execute(count_query, params).fetchone()[0]

        # Sort
        sort_map = {
            "title": "title COLLATE NOCASE ASC",
            "author": "author COLLATE NOCASE ASC, title COLLATE NOCASE ASC",
            "recent": "modified_at DESC",
            "series": "series COLLATE NOCASE ASC, series_index ASC",
        }
        query += f" ORDER BY {sort_map.get(sort, sort_map['title'])}"
        query += f" LIMIT {per_page} OFFSET {(page - 1) * per_page}"

        rows = conn.execute(query, params).fetchall()
        books = [dict(row) for row in rows]
        books = _group_format_variants(books)

        conn.close()
        return jsonify({
            "books": books,
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": (total + per_page - 1) // per_page,
        })
    except Exception as e:
        logger.error(f"Error in api_books: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/books/<int:book_id>")
@login_required
def api_book_detail(book_id):
    """Get single book details with reading progress."""
    try:
        conn = database.get_db()
        book = conn.execute("SELECT * FROM books WHERE id = ?", (book_id,)).fetchone()
        if not book:
            conn.close()
            return jsonify({"error": "Book not found"}), 404

        result = dict(book)

        # Get user's reading progress
        progress = conn.execute(
            "SELECT * FROM reading_progress WHERE user_id = ? AND book_id = ?",
            (session["user_id"], book_id)
        ).fetchone()
        if progress:
            result["progress"] = dict(progress)
        else:
            result["progress"] = None

        conn.close()
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error in api_book_detail: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


def _fixup_epub_images(epub_path):
    """Detect and fix image issues in a Calibre-converted EPUB.

    Calibre sometimes extracts images from PDFs but writes broken relative
    paths in the HTML, or leaves images in the zip with no HTML reference.
    Fixes both: patches broken paths by basename lookup, and appends an extra
    HTML page for any images that remain unreferenced.

    Returns (broken_fixed, images_added).
    """
    IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.gif', '.svg', '.webp', '.bmp'}
    broken_fixed = 0
    images_added = 0
    tmp_path = epub_path + '.tmp.epub'

    try:
        # ── 1. Read entire zip into memory ────────────────────────────────────
        all_files = {}
        with zipfile.ZipFile(epub_path, 'r') as zf:
            for name in zf.namelist():
                all_files[name] = zf.read(name)

        names = set(all_files)
        epub_images = {n for n in names
                       if os.path.splitext(n)[1].lower() in IMAGE_EXTS}
        if not epub_images:
            return 0, 0

        # ── 2. Locate OPF ─────────────────────────────────────────────────────
        opf_path = None
        if 'META-INF/container.xml' in all_files:
            m = re.search(r'full-path=["\']([^"\']+\.opf)["\']',
                          all_files['META-INF/container.xml'].decode('utf-8', errors='replace'))
            if m:
                opf_path = m.group(1)
        if not opf_path:
            opf_path = next((n for n in names if n.endswith('.opf')), None)

        # ── 3. Scan HTML src= references ─────────────────────────────────────
        html_files = [n for n in names
                      if os.path.splitext(n)[1].lower() in ('.html', '.xhtml', '.htm')
                      and 'toc' not in n.lower()]
        referenced = set()
        broken_by_file = {}

        def _resolve(hf_dir, src):
            """Resolve a relative src to an absolute zip name."""
            raw = (hf_dir + '/' + src) if hf_dir else src
            parts = []
            for seg in raw.split('/'):
                if seg == '..':
                    if parts:
                        parts.pop()
                elif seg and seg != '.':
                    parts.append(seg)
            return '/'.join(parts)

        for hf in html_files:
            content = all_files[hf].decode('utf-8', errors='replace')
            hf_dir = hf.rsplit('/', 1)[0] if '/' in hf else ''

            for m in re.finditer(r'src=["\']([^"\']+)["\']', content, re.IGNORECASE):
                src = m.group(1)
                if src.startswith('data:') or src.startswith('http'):
                    continue
                resolved = _resolve(hf_dir, src)
                if resolved in names:
                    referenced.add(resolved)
                elif os.path.splitext(resolved)[1].lower() in IMAGE_EXTS:
                    # Broken path — find by basename
                    basename = src.rsplit('/', 1)[-1]
                    candidates = [img for img in epub_images
                                  if img == basename or img.endswith('/' + basename)]
                    if candidates:
                        target = candidates[0]
                        t_parts = target.split('/')
                        h_parts = hf_dir.split('/') if hf_dir else []
                        common = sum(1 for a, b in zip(h_parts, t_parts) if a == b)
                        new_rel = '../' * (len(h_parts) - common) + '/'.join(t_parts[common:])
                        broken_by_file.setdefault(hf, []).append((src, new_rel))
                        referenced.add(target)

        unreferenced = epub_images - referenced

        if not broken_by_file and not unreferenced:
            logger.info(f"EPUB image audit OK: {len(epub_images)} image(s) all referenced")
            return 0, 0

        if broken_by_file:
            logger.warning(f"EPUB image audit: {sum(len(v) for v in broken_by_file.values())} broken img path(s)")
        if unreferenced:
            logger.warning(f"EPUB image audit: {len(unreferenced)} unreferenced image(s) – appending page")

        # ── 4. Rewrite EPUB ───────────────────────────────────────────────────
        with zipfile.ZipFile(tmp_path, 'w', zipfile.ZIP_DEFLATED) as zout:
            # mimetype must come first, uncompressed
            if 'mimetype' in all_files:
                info = zipfile.ZipInfo('mimetype')
                info.compress_type = zipfile.ZIP_STORED
                zout.writestr(info, all_files['mimetype'])

            skip = {'mimetype'}
            if unreferenced and opf_path:
                skip.add(opf_path)  # Rewritten below after patching

            for name, data in all_files.items():
                if name in skip:
                    continue
                if name in broken_by_file:
                    content = data.decode('utf-8', errors='replace')
                    for old_src, new_src in broken_by_file[name]:
                        content = content.replace(f'src="{old_src}"', f'src="{new_src}"')
                        content = content.replace(f"src='{old_src}'", f"src='{new_src}'")
                        broken_fixed += 1
                    zout.writestr(name, content.encode('utf-8'))
                else:
                    zout.writestr(name, data)

            # Extra page for unreferenced images
            if unreferenced and opf_path:
                opf_dir = opf_path.rsplit('/', 1)[0] if '/' in opf_path else ''
                extra_name = (opf_dir + '/' if opf_dir else '') + 'Text/extra_images.xhtml'
                h_parts = extra_name.rsplit('/', 1)[0].split('/')

                img_tags = []
                for img_name in sorted(unreferenced):
                    i_parts = img_name.split('/')
                    common = sum(1 for a, b in zip(h_parts, i_parts) if a == b)
                    rel = '../' * (len(h_parts) - common) + '/'.join(i_parts[common:])
                    img_tags.append(f'<p><img src="{rel}" alt="" style="max-width:100%"/></p>')
                    images_added += 1

                extra_html = ('<?xml version="1.0" encoding="UTF-8"?>\n'
                              '<!DOCTYPE html>\n'
                              '<html xmlns="http://www.w3.org/1999/xhtml">'
                              '<head><title>Extracted Images</title></head>'
                              '<body>\n' + '\n'.join(img_tags) + '\n</body></html>')
                zout.writestr(extra_name, extra_html.encode('utf-8'))

                # Patch OPF manifest + spine
                opf_str = all_files[opf_path].decode('utf-8', errors='replace')
                manifest_item = '<item id="extra_images" href="Text/extra_images.xhtml" media-type="application/xhtml+xml"/>'
                spine_item = '<itemref idref="extra_images"/>'
                opf_str = re.sub(
                    r'</([a-zA-Z]+:)?manifest>',
                    lambda m_: f'  {manifest_item}\n  </{m_.group(1) or ""}manifest>',
                    opf_str)
                opf_str = re.sub(
                    r'</([a-zA-Z]+:)?spine>',
                    lambda m_: f'  {spine_item}\n  </{m_.group(1) or ""}spine>',
                    opf_str)
                zout.writestr(opf_path, opf_str.encode('utf-8'))

        os.replace(tmp_path, epub_path)
        if broken_fixed:
            logger.info(f"Fixed {broken_fixed} broken image path(s) in EPUB")
        if images_added:
            logger.info(f"Appended {images_added} unreferenced image(s) to EPUB as extra page")
        return broken_fixed, images_added

    except Exception as e:
        logger.error(f"EPUB image fixup failed: {e}\n{traceback.format_exc()}")
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except OSError:
            pass
        return 0, 0


convert_state = {"running": False, "book_id": None, "message": "", "epub_id": None, "error": None, "current_page": 0, "total_pages": 0, "started_at": 0}


@app.route("/api/books/<int:book_id>/convert-epub", methods=["POST"])
@login_required
def api_convert_epub(book_id):
    """Convert a PDF book to EPUB using Calibre (async)."""
    if convert_state["running"]:
        # Treat as stale if running for more than 15 min with no progress
        elapsed = time.time() - convert_state.get("started_at", 0)
        if elapsed > 900:
            convert_state["running"] = False
        else:
            return jsonify({"error": "A conversion is already in progress"}), 409
    try:
        import subprocess
        conn = database.get_db()
        book = conn.execute("SELECT id, path, filename, title, author, genre, format, page_count FROM books WHERE id = ?", (book_id,)).fetchone()
        if not book:
            conn.close()
            return jsonify({"error": "Book not found"}), 404
        if book["format"] != "pdf":
            conn.close()
            return jsonify({"error": "Only PDF books can be converted"}), 400

        pdf_path = _resolve_book_path(book["path"])
        epub_path = os.path.splitext(pdf_path)[0] + ".epub"
        if os.path.exists(epub_path):
            conn.close()
            return jsonify({"error": "EPUB version already exists"}), 409

        book_dict = dict(book)
        total_pages = book["page_count"] or 0
        conn.close()

        def run_convert():
            import time as _time
            convert_state["running"] = True
            convert_state["book_id"] = book_id
            convert_state["message"] = "Converting..."
            convert_state["epub_id"] = None
            convert_state["error"] = None
            convert_state["current_page"] = 0
            convert_state["total_pages"] = total_pages
            convert_state["started_at"] = _time.time()
            try:
                import re as _re
                pdf_dir = os.path.dirname(pdf_path)
                proc = subprocess.Popen(
                    [config.CALIBRE_CONVERT, pdf_path, epub_path,
                     "--title", book_dict["title"],
                     "--authors", book_dict["author"] or "Unknown",
                     "--dont-split-on-page-breaks"],
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    bufsize=0, cwd=pdf_dir
                )
                # Read byte-by-byte to defeat Windows pipe buffering
                buf = b""
                while True:
                    chunk = proc.stdout.read(1)
                    if not chunk:
                        break
                    buf += chunk
                    if chunk in (b"\n", b"\r"):
                        line = buf.decode("utf-8", errors="replace").strip()
                        buf = b""
                        if not line:
                            continue
                        # Log everything from Calibre for debugging
                        logger.info(f"[calibre] {line}")
                        # Calibre: "Page-N" or "N% ..."
                        page_match = _re.match(r"Page-(\d+)", line)
                        pct_match = _re.match(r"(\d+)%", line)
                        if page_match:
                            page_num = int(page_match.group(1))
                            convert_state["current_page"] = page_num
                            convert_state["message"] = f"Page {page_num}" + (f"/{total_pages}" if total_pages else "")
                        elif pct_match:
                            pct_val = int(pct_match.group(1))
                            if pct_val > 1:
                                convert_state["message"] = f"{pct_val}% processing..."
                proc.wait(timeout=600)
                if proc.returncode != 0:
                    convert_state["error"] = "Conversion failed"
                    convert_state["message"] = "Failed"
                    return

                # Post-process: fix any broken/missing image references
                convert_state["message"] = "Checking images..."
                _fixup_epub_images(epub_path)

                convert_state["message"] = "Finalizing..."
                file_size = os.path.getsize(epub_path)
                epub_filename = os.path.basename(epub_path)

                # Extract cover for the new EPUB
                has_cover = 0
                try:
                    from scanner import _extract_cover
                    if _extract_cover(epub_path, ".epub", None):
                        has_cover = 1
                except Exception:
                    pass

                c = database.get_db()
                c.execute("""
                    INSERT INTO books (path, filename, title, author, genre, series, series_index,
                    category, format, file_size, has_cover, page_count, description)
                    SELECT ?, ?, title, author, genre, series, series_index,
                    category, 'epub', ?, ?, 0, description
                    FROM books WHERE id = ?
                """, (epub_path, epub_filename, file_size, has_cover, book_id))
                c.commit()
                new_id = c.execute("SELECT id FROM books WHERE path = ?", (epub_path,)).fetchone()["id"]
                c.close()
                convert_state["epub_id"] = new_id
                convert_state["message"] = "Done"
            except subprocess.TimeoutExpired:
                proc.kill()
                convert_state["error"] = "Conversion timed out (max 10 min)"
                convert_state["message"] = "Timed out"
            except Exception as e:
                convert_state["error"] = str(e)
                convert_state["message"] = "Failed"
                logger.error(f"Convert error: {e}\n{traceback.format_exc()}")
            finally:
                convert_state["running"] = False

        threading.Thread(target=run_convert, daemon=True).start()
        return jsonify({"ok": True, "message": "Conversion started"})
    except Exception as e:
        logger.error(f"Error in convert_epub: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/convert/status")
@login_required
def api_convert_status():
    return jsonify(convert_state)


@app.route("/api/books/<int:book_id>/optimize-epub", methods=["POST"])
@login_required
def api_optimize_epub(book_id):
    """Strip heavy CSS from EPUB to fix rendering issues in epub.js."""
    try:
        conn = database.get_db()
        book = conn.execute("SELECT id, path, format FROM books WHERE id = ?", (book_id,)).fetchone()
        if not book:
            conn.close()
            return jsonify({"error": "Book not found"}), 404
        if book["format"] != "epub":
            conn.close()
            return jsonify({"error": "Only EPUB books can be optimized"}), 400

        orig_path = _resolve_book_path(book["path"])
        tmp_path = orig_path + ".optimized.epub"

        MINIMAL_CSS = b"""
body { margin: 1em; font-family: serif; line-height: 1.6; color: #222; }
img { max-width: 100%; height: auto; }
h1, h2, h3 { margin: 1em 0 0.5em; }
p { margin: 0.5em 0; }
table { border-collapse: collapse; width: 100%; }
td, th { padding: 4px 8px; border: 1px solid #ccc; }
"""
        with zipfile.ZipFile(orig_path, 'r') as zin:
            with zipfile.ZipFile(tmp_path, 'w', zipfile.ZIP_DEFLATED) as zout:
                for item in zin.infolist():
                    data = zin.read(item.filename)
                    if item.filename.endswith('.css'):
                        data = MINIMAL_CSS
                    zout.writestr(item, data)

        os.replace(tmp_path, orig_path)

        # Update file size in DB
        new_size = os.path.getsize(orig_path)
        conn.execute("UPDATE books SET file_size = ?, modified_at = CURRENT_TIMESTAMP WHERE id = ?",
                      (new_size, book_id))
        conn.commit()
        conn.close()
        return jsonify({"ok": True, "message": "EPUB optimized"})
    except subprocess.TimeoutExpired:
        return jsonify({"error": "Optimization timed out (max 5 min)"}), 504
    except Exception as e:
        logger.error(f"Error in optimize_epub: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/books/<int:book_id>/genre", methods=["PUT"])
@login_required
def api_set_genre(book_id):
    """Manually set a book's genre (locks it from AI changes)."""
    try:
        data = request.get_json()
        genre = data.get("genre", "").strip()
        conn = database.get_db()
        conn.execute(
            "UPDATE books SET genre = ?, genre_locked = 1, modified_at = CURRENT_TIMESTAMP WHERE id = ?",
            (genre, book_id)
        )
        conn.commit()
        conn.close()
        return jsonify({"ok": True, "genre": genre})
    except Exception as e:
        logger.error(f"Error in set_genre: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/books/<int:book_id>/series", methods=["DELETE"])
@login_required
def api_remove_book_series(book_id):
    """Remove a single book from its series (book is kept, series is cleared)."""
    try:
        conn = database.get_db()
        conn.execute(
            "UPDATE books SET series = '', series_index = 0, modified_at = CURRENT_TIMESTAMP WHERE id = ?",
            (book_id,)
        )
        conn.commit()
        conn.close()
        return jsonify({"ok": True})
    except Exception as e:
        logger.error(f"Error in remove_book_series: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/series", methods=["DELETE"])
@login_required
def api_delete_series():
    """Delete a series: clears the series field on all its books (books are kept)."""
    try:
        data = request.get_json() or {}
        series = data.get("series", "").strip()
        if not series:
            return jsonify({"error": "series name required"}), 400
        conn = database.get_db()
        result = conn.execute(
            "UPDATE books SET series = '', series_index = 0, modified_at = CURRENT_TIMESTAMP WHERE series = ?",
            (series,)
        )
        affected = result.rowcount
        conn.commit()
        conn.close()
        return jsonify({"ok": True, "affected": affected})
    except Exception as e:
        logger.error(f"Error in delete_series: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/books/<int:book_id>/classify-genre", methods=["POST"])
@login_required
def api_classify_genre(book_id):
    """Ask the local LLM to classify a book's genre."""
    try:
        from genre_ai import classify_genre
        conn = database.get_db()
        book = conn.execute("SELECT id, title, author, genre, description, genre_locked FROM books WHERE id = ?", (book_id,)).fetchone()
        if not book:
            conn.close()
            return jsonify({"error": "Book not found"}), 404
        if book["genre_locked"]:
            conn.close()
            return jsonify({"error": "Genre was manually set and is locked"}), 409

        genre = classify_genre(book["title"], book["author"], book["description"] or "")
        if not genre:
            conn.close()
            return jsonify({"error": "AI classification unavailable (is Ollama running?)"}), 503

        conn.execute("UPDATE books SET genre = ?, modified_at = CURRENT_TIMESTAMP WHERE id = ?", (genre, book_id))
        conn.commit()
        conn.close()
        return jsonify({"genre": genre})
    except Exception as e:
        logger.error(f"Error in classify_genre: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/filters")
@login_required
def api_filters():
    """Get available filter values."""
    try:
        conn = database.get_db()

        categories = [r[0] for r in conn.execute(
            "SELECT DISTINCT category FROM books WHERE category != '' ORDER BY category"
        ).fetchall()]

        authors = [r[0] for r in conn.execute(
            "SELECT DISTINCT author FROM books WHERE author != '' ORDER BY author COLLATE NOCASE"
        ).fetchall()]

        # Extract individual genres (comma-separated)
        raw_genres = [r[0] for r in conn.execute(
            "SELECT DISTINCT genre FROM books WHERE genre != ''"
        ).fetchall()]
        genre_set = set()
        for g in raw_genres:
            for part in g.split(","):
                part = part.strip()
                if part:
                    genre_set.add(part)
        genres = sorted(genre_set, key=str.lower)

        formats = [r[0] for r in conn.execute(
            "SELECT DISTINCT format FROM books ORDER BY format"
        ).fetchall()]

        conn.close()
        return jsonify({
            "categories": categories,
            "authors": authors,
            "genres": genres,
            "formats": formats,
        })
    except Exception as e:
        logger.error(f"Error in api_filters: {e}")
        return jsonify({"categories": [], "authors": [], "genres": [], "formats": []})


@app.route("/api/stats")
@login_required
def api_stats():
    """Get library statistics."""
    conn = database.get_db()
    total = conn.execute("SELECT COUNT(*) FROM books").fetchone()[0]
    by_cat = conn.execute(
        "SELECT category, COUNT(*) as cnt FROM books GROUP BY category ORDER BY cnt DESC"
    ).fetchall()
    by_fmt = conn.execute(
        "SELECT format, COUNT(*) as cnt FROM books GROUP BY format ORDER BY cnt DESC"
    ).fetchall()
    conn.close()
    return jsonify({
        "total": total,
        "by_category": [dict(r) for r in by_cat],
        "by_format": [dict(r) for r in by_fmt],
    })


# ── API: Reading Progress ───────────────────────────────────────────────────

@app.route("/api/books/<int:book_id>/progress", methods=["GET"])
@login_required
def api_get_progress(book_id):
    try:
        conn = database.get_db()
        row = conn.execute(
            "SELECT * FROM reading_progress WHERE user_id = ? AND book_id = ?",
            (session["user_id"], book_id)
        ).fetchone()
        conn.close()
        if row:
            return jsonify(dict(row))
        return jsonify({"progress": 0, "current_location": ""})
    except Exception as e:
        logger.error(f"Error in api_get_progress: {e}")
        return jsonify({"progress": 0, "current_location": ""})


@app.route("/api/books/<int:book_id>/progress", methods=["DELETE"])
@login_required
def api_delete_progress(book_id):
    """Remove a book from the user's reading list."""
    try:
        conn = database.get_db()
        conn.execute(
            "DELETE FROM reading_progress WHERE user_id = ? AND book_id = ?",
            (session["user_id"], book_id)
        )
        conn.commit()
        conn.close()
        return jsonify({"ok": True})
    except Exception as e:
        logger.error(f"Error in api_delete_progress: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/books/<int:book_id>/progress", methods=["PUT"])
@login_required
def api_set_progress(book_id):
    try:
        data = request.get_json()
        progress = float(data.get("progress", 0))
        location = str(data.get("current_location", ""))

        conn = database.get_db()
        conn.execute("""
            INSERT INTO reading_progress (user_id, book_id, progress, current_location, last_read)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id, book_id) DO UPDATE SET
                progress = excluded.progress,
                current_location = excluded.current_location,
                last_read = CURRENT_TIMESTAMP
        """, (session["user_id"], book_id, progress, location))
        conn.commit()
        conn.close()
        return jsonify({"ok": True})
    except Exception as e:
        logger.error(f"Error in api_set_progress: {e}\n{traceback.format_exc()}")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/continue-reading")
@login_required
def api_continue_reading():
    """Get books the user has started reading, ordered by last read."""
    try:
        conn = database.get_db()
        rows = conn.execute("""
            SELECT b.*, rp.progress, rp.current_location, rp.last_read
            FROM reading_progress rp
            JOIN books b ON b.id = rp.book_id
            WHERE rp.user_id = ? AND rp.progress > 0 AND rp.progress < 100
            ORDER BY rp.last_read DESC
            LIMIT 20
        """, (session["user_id"],)).fetchall()
        conn.close()
        return jsonify([dict(r) for r in rows])
    except Exception as e:
        logger.error(f"Error in api_continue_reading: {e}\n{traceback.format_exc()}")
        return jsonify([])


# ── API: File Serving ────────────────────────────────────────────────────────

@app.route("/api/books/<int:book_id>/cover")
def api_book_cover(book_id):
    """Serve book cover image."""
    try:
        conn = database.get_db()
        book = conn.execute("SELECT path, has_cover FROM books WHERE id = ?", (book_id,)).fetchone()
        conn.close()

        if not book:
            return Response(NO_COVER_SVG, mimetype="image/svg+xml")

        if book["has_cover"]:
            cover_path = scanner.get_cover_path(book["path"])
            if cover_path and os.path.exists(cover_path):
                resp = send_file(cover_path, mimetype="image/jpeg")
                resp.headers["Cache-Control"] = "public, max-age=86400"
                return resp

        # Return inline placeholder SVG (short cache so it refreshes when cover is extracted)
        resp = Response(NO_COVER_SVG, mimetype="image/svg+xml")
        resp.headers["Cache-Control"] = "no-cache"
        return resp
    except Exception as e:
        logger.error(f"Error serving cover for book {book_id}: {e}")
        return Response(NO_COVER_SVG, mimetype="image/svg+xml")


@app.route("/api/books/<int:book_id>/file")
@login_required
def api_book_file(book_id):
    """Serve the actual book file for the reader."""
    conn = database.get_db()
    book = conn.execute("SELECT path, format, filename FROM books WHERE id = ?", (book_id,)).fetchone()
    conn.close()

    if not book:
        abort(404)

    resolved_path = _resolve_book_path(book["path"])
    if not os.path.exists(resolved_path):
        abort(404)

    mime_map = {
        "epub": "application/epub+zip",
        "pdf": "application/pdf",
        "cbz": "application/zip",
        "cbr": "application/x-rar-compressed",
        "mobi": "application/x-mobipocket-ebook",
    }
    mimetype = mime_map.get(book["format"], "application/octet-stream")
    # Pre-read into BytesIO so the H: drive (network mount) is fully read before the HTTP
    # response starts — prevents the browser receiving a truncated zip on slow drives.
    try:
        with open(resolved_path, "rb") as f:
            data = f.read()
    except OSError as e:
        abort(500, description=str(e))
    from io import BytesIO
    return send_file(BytesIO(data), mimetype=mimetype, download_name=book["filename"])


@app.route("/api/books/<int:book_id>/epub-resource/<path:resource_path>")
@login_required
def api_epub_resource(book_id, resource_path):
    """Serve a single resource (image, CSS, font) extracted from an EPUB zip.

    epub.js resolves internal EPUB resources via blob: URLs built from the zip
    contents. For flat-structure EPUBs (all files at zip root), its text-based
    URL substitution can silently fail to match relative src attributes, leaving
    images broken. This endpoint gives the client a reliable fallback: look up
    the resource by zip-internal path and stream it back with the correct MIME
    type. The client-side content hook rewrites unresolved <img src> attributes
    to point here instead of relying on epub.js's internal blob URL machinery.
    """
    conn = database.get_db()
    book = conn.execute("SELECT path, format FROM books WHERE id = ?", (book_id,)).fetchone()
    conn.close()

    if not book or book["format"] != "epub":
        abort(404)

    epub_path = _resolve_book_path(book["path"])
    if not os.path.exists(epub_path):
        abort(404)

    # Guard against directory traversal
    resource_path = resource_path.lstrip("/")
    if ".." in resource_path.split("/"):
        abort(400)

    try:
        with zipfile.ZipFile(epub_path, "r") as zf:
            try:
                data = zf.read(resource_path)
            except KeyError:
                # epub.js gives paths relative to the OPF directory (e.g. "Text/ch1.xhtml")
                # but the zip stores them at "OEBPS/Text/ch1.xhtml". Read container.xml
                # to find the OPF base directory and retry.
                try:
                    container_xml = zf.read("META-INF/container.xml").decode("utf-8", errors="replace")
                    import re as _re
                    m = _re.search(r'full-path=["\']([^"\']+)["\']', container_xml)
                    if m:
                        opf_dir = "/".join(m.group(1).split("/")[:-1])
                        if opf_dir:
                            data = zf.read(opf_dir + "/" + resource_path)
                        else:
                            abort(404)
                    else:
                        abort(404)
                except KeyError:
                    abort(404)
    except zipfile.BadZipFile:
        abort(400)

    mime = mimetypes.guess_type(resource_path)[0] or "application/octet-stream"
    resp = Response(data, mimetype=mime)
    resp.headers["Cache-Control"] = "public, max-age=3600"
    return resp


EPUB_LOC_CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache", "epub_locations")


@app.route("/api/books/<int:book_id>/epub-locations", methods=["GET"])
@login_required
def api_get_epub_locations(book_id):
    """Return cached epub.js locations JSON for instant seekbar on re-open."""
    path = os.path.join(EPUB_LOC_CACHE_DIR, f"{book_id}.json")
    if not os.path.exists(path):
        return jsonify({"locations": None})
    with open(path, "r", encoding="utf-8") as f:
        return jsonify({"locations": f.read()})


@app.route("/api/books/<int:book_id>/epub-locations", methods=["PUT"])
@login_required
def api_put_epub_locations(book_id):
    """Store epub.js locations JSON generated by the client."""
    data = request.get_json(silent=True)
    if not data or not isinstance(data.get("locations"), str):
        abort(400)
    os.makedirs(EPUB_LOC_CACHE_DIR, exist_ok=True)
    path = os.path.join(EPUB_LOC_CACHE_DIR, f"{book_id}.json")
    with open(path, "w", encoding="utf-8") as f:
        f.write(data["locations"])
    return jsonify({"ok": True})


@app.route("/api/books/<int:book_id>/comic-pages")
@login_required
def api_comic_pages(book_id):
    """List all pages in a comic archive."""
    conn = database.get_db()
    book = conn.execute("SELECT path, format FROM books WHERE id = ?", (book_id,)).fetchone()
    conn.close()

    if not book:
        abort(404)

    resolved_path = _resolve_book_path(book["path"])
    if book["format"] == "mobi":
        count = _mobi_page_count(resolved_path)
        return jsonify({"pages": list(range(count)), "total": count})
    pages = _list_comic_pages(resolved_path, book["format"])
    return jsonify({"pages": pages, "total": len(pages)})


@app.route("/api/books/<int:book_id>/comic-page/<int:page_num>")
@login_required
def api_comic_page(book_id, page_num):
    """Serve a single comic page image."""
    conn = database.get_db()
    book = conn.execute("SELECT path, format FROM books WHERE id = ?", (book_id,)).fetchone()
    conn.close()

    if not book:
        abort(404)

    resolved_path = _resolve_book_path(book["path"])

    # MOBI: render page via PyMuPDF
    if book["format"] == "mobi":
        try:
            import fitz
            doc = fitz.open(resolved_path)
            if page_num < 0 or page_num >= doc.page_count:
                doc.close()
                abort(404)
            page = doc[page_num]
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
            data = pix.tobytes("jpeg")
            doc.close()
            return send_file(BytesIO(data), mimetype="image/jpeg")
        except Exception as e:
            logger.error(f"Error serving MOBI page: {e}")
            abort(500)

    pages = _list_comic_pages(resolved_path, book["format"])
    if page_num < 0 or page_num >= len(pages):
        abort(404)

    page_name = pages[page_num]
    ext = os.path.splitext(page_name)[1].lower()
    mime = mimetypes.types_map.get(ext, "image/jpeg")

    try:
        archive = _open_comic_archive(resolved_path, book["format"])
        if not archive:
            abort(415)
        with archive:
            data = archive.read(page_name)
        return send_file(BytesIO(data), mimetype=mime)
    except Exception as e:
        logger.error(f"Error serving comic page: {e}")
        abort(500)


def _open_comic_archive(path, fmt):
    """Open a comic archive, handling misnamed formats (CBZ as RAR, CBR as ZIP)."""
    if fmt in ("cbz", "cbr"):
        # Try ZIP first, then RAR — regardless of extension
        try:
            zf = zipfile.ZipFile(path, "r")
            zf.namelist()  # Validate it's a real ZIP
            return zf
        except (zipfile.BadZipFile, Exception):
            pass
        if HAS_RARFILE:
            try:
                return rarfile.RarFile(path, "r")
            except Exception:
                pass
    return None


def _mobi_page_count(path):
    """Get page count of a MOBI file using PyMuPDF."""
    try:
        import fitz
        doc = fitz.open(path)
        count = doc.page_count
        doc.close()
        return count
    except Exception:
        return 0


def _list_comic_pages(path, fmt):
    """List image files in a comic archive, sorted."""
    try:
        archive = _open_comic_archive(path, fmt)
        if not archive:
            return []
        with archive:
            names = archive.namelist()
            pages = sorted([
                n for n in names
                if os.path.splitext(n)[1].lower() in IMAGE_EXTS
                and not n.startswith("__MACOSX")
                and "/." not in n
            ])
            return pages
    except Exception:
        return []


# ── API: Library Scan ────────────────────────────────────────────────────────

@app.route("/api/scan", methods=["POST"])
@login_required
def api_scan():
    """Trigger a library scan in a background thread."""
    if scan_state["running"]:
        return jsonify({"error": "Scan already in progress"}), 409

    def run_scan():
        scan_state["running"] = True
        scan_state["cancel"] = False
        try:
            def cb(current, total, message):
                scan_state["current"] = current
                scan_state["total"] = total
                scan_state["message"] = message
                if scan_state["cancel"]:
                    raise InterruptedError("Scan cancelled")
            result = scanner.scan_library(progress_callback=cb)
            parts = [f"{result['new']} new", f"{result['updated']} updated",
                     f"{result['removed']} removed"]
            if result.get('moved'):
                parts.append(f"{result['moved']} moved")
            scan_state["message"] = "Done: " + ", ".join(parts)
        except InterruptedError:
            scan_state["message"] = "Scan cancelled"
        except Exception as e:
            scan_state["message"] = f"Error: {e}"
            logger.error(f"Scan error: {e}\n{traceback.format_exc()}")
        finally:
            scan_state["running"] = False
            scan_state["cancel"] = False

    thread = threading.Thread(target=run_scan, daemon=True)
    thread.start()
    return jsonify({"ok": True, "message": "Scan started"})


@app.route("/api/scan/status")
@login_required
def api_scan_status():
    return jsonify(scan_state)


@app.route("/api/scan/stop", methods=["POST"])
@login_required
def api_scan_stop():
    """Cancel a running scan."""
    if scan_state["running"]:
        scan_state["cancel"] = True
        return jsonify({"ok": True, "message": "Cancelling scan..."})
    return jsonify({"ok": False, "message": "No scan running"})





@app.route("/api/books/grouped")
@login_required
def api_books_grouped():
    """List books with folder-hierarchy-based collection grouping.
    
    Uses collection_path (e.g. "Marvel/X-Men v2/Here comes tomorrow") for hierarchy.
    The 'prefix' parameter browses into sub-levels.
    Returns a mix of 'collection' items (for folders with children) and 'book' items.
    """
    try:
        conn = database.get_db()

        category = request.args.get("category", "")
        genre = request.args.get("genre", "")
        author = request.args.get("author", "")
        fmt = request.args.get("format", "")
        search = request.args.get("search", "")
        prefix = request.args.get("prefix", "")  # Collection path prefix to browse into
        page = int(request.args.get("page", 1))
        per_page = int(request.args.get("per_page", 50))

        # Build WHERE clause for filters
        where_parts = []
        params = []
        if category:
            where_parts.append("category = ?")
            params.append(category)
        if genre:
            where_parts.append("genre LIKE ?")
            params.append(f"%{genre}%")
        if author:
            where_parts.append("author LIKE ?")
            params.append(f"%{author}%")
        if fmt:
            where_parts.append("format = ?")
            params.append(fmt)
        if search:
            where_parts.append("(title LIKE ? OR author LIKE ? OR series LIKE ? OR collection_path LIKE ?)")
            params.extend([f"%{search}%"] * 4)

        where = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""

        if prefix:
            # Browsing inside a collection: show next level
            prefix_filter = f'{"AND" if where else "WHERE"} collection_path LIKE ?'
            prefix_param = prefix + '/%'
            exact_filter = f'{"AND" if where else "WHERE"} collection_path = ?'
            
            # Get sub-folders at next level
            # collection_path starts with prefix/ -> extract next segment
            all_in_prefix = conn.execute(
                f"SELECT id, title, author, collection_path, has_cover, format, filename, genre FROM books {where} {prefix_filter}",
                params + [prefix_param]
            ).fetchall()
            
            # Also get books exactly at this level
            exact_books = conn.execute(
                f"SELECT * FROM books {where} {exact_filter}",
                params + [prefix]
            ).fetchall()
            
            # Group by next sub-level
            sub_groups = {}
            for r in all_in_prefix:
                rest = r["collection_path"][len(prefix) + 1:]  # after "prefix/"
                next_level = rest.split("/")[0]
                if next_level not in sub_groups:
                    sub_groups[next_level] = {"count": 0, "cover_id": 0, "authors": set(), "full_path": prefix + "/" + next_level}
                sub_groups[next_level]["count"] += 1
                if r["has_cover"] and not sub_groups[next_level]["cover_id"]:
                    sub_groups[next_level]["cover_id"] = r["id"]
                sub_groups[next_level]["authors"].add(r["author"])
            
            collections = []
            for name, info in sorted(sub_groups.items(), key=lambda x: x[0].lower()):
                author_list = sorted(a for a in info["authors"] if a)[:2]
                author_str = ", ".join(author_list)
                if len(info["authors"]) > 2:
                    author_str += f" +{len(info['authors'])-2}"
                collections.append({
                    "type": "collection",
                    "title": name,
                    "collection_path": info["full_path"],
                    "book_count": info["count"],
                    "cover_book_id": info["cover_id"],
                    "author": author_str,
                })
            
            # Books at this exact level
            standalone_books = _group_format_variants([dict(r) for r in exact_books])
            for b in standalone_books:
                b["type"] = "book"
            
            all_items = collections + standalone_books
        else:
            # Top level: group by first segment of collection_path, 
            # plus show standalone books (empty collection_path)
            
            all_books = conn.execute(
                f"SELECT id, title, author, collection_path, has_cover, format, filename, genre FROM books {where}",
                params
            ).fetchall()
            
            top_groups = {}
            standalone_ids = []
            
            for r in all_books:
                cp = r["collection_path"]
                if not cp:
                    standalone_ids.append(r["id"])
                    continue
                
                top_level = cp.split("/")[0]
                if top_level not in top_groups:
                    top_groups[top_level] = {"count": 0, "cover_id": 0, "authors": set(), "has_children": False}
                top_groups[top_level]["count"] += 1
                if "/" in cp:
                    top_groups[top_level]["has_children"] = True
                if r["has_cover"] and not top_groups[top_level]["cover_id"]:
                    top_groups[top_level]["cover_id"] = r["id"]
                top_groups[top_level]["authors"].add(r["author"])
            
            collections = []
            single_book_groups = []  # groups with only 1 book and no children -> show as book
            
            for name, info in top_groups.items():
                if info["count"] == 1 and not info["has_children"]:
                    # Single book in a "collection" -> show as standalone book
                    single_book_groups.append(name)
                    continue
                
                author_list = sorted(a for a in info["authors"] if a)[:2]
                author_str = ", ".join(author_list)
                if len(info["authors"]) > 2:
                    author_str += f" +{len(info['authors'])-2}"
                collections.append({
                    "type": "collection",
                    "title": name,
                    "collection_path": name,
                    "book_count": info["count"],
                    "cover_book_id": info["cover_id"],
                    "author": author_str,
                })
            
            # Get standalone books (no collection_path + single-book groups)
            if standalone_ids or single_book_groups:
                extra_where = []
                extra_params = list(params)
                if standalone_ids:
                    extra_where.append(f"id IN ({','.join('?' * len(standalone_ids))})")
                    extra_params.extend(standalone_ids)
                if single_book_groups:
                    extra_where.append(f"collection_path IN ({','.join('?' * len(single_book_groups))})")
                    extra_params.extend(single_book_groups)
                
                combined = " OR ".join(extra_where)
                base_where = f"WHERE ({combined})" if not where else f"{where} AND ({combined})"
                standalone_rows = conn.execute(
                    f"SELECT * FROM books {base_where}", extra_params
                ).fetchall()
            else:
                standalone_rows = []
            
            standalone_books = _group_format_variants([dict(r) for r in standalone_rows])
            for b in standalone_books:
                b["type"] = "book"
            
            all_items = collections + standalone_books
        
        # Sort
        all_items.sort(key=lambda x: (x.get("title") or "").lower())
        
        total = len(all_items)
        start = (page - 1) * per_page
        page_items = all_items[start:start + per_page]

        conn.close()
        return jsonify({
            "items": page_items,
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": (total + per_page - 1) // per_page,
            "prefix": prefix,
        })
    except Exception as e:
        logger.error(f"Error in api_books_grouped: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500



@app.route("/api/books/recent")
@login_required
def api_books_recent():
    """Return the N most recently added books."""
    try:
        n = int(request.args.get("n", 10))
        conn = database.get_db()
        rows = conn.execute(
            "SELECT * FROM books ORDER BY added_at DESC, id DESC LIMIT ?", (n,)
        ).fetchall()
        books = _group_format_variants([dict(r) for r in rows])
        conn.close()
        return jsonify({"books": books})
    except Exception as e:
        logger.error(f"Error in api_books_recent: {e}")
        return jsonify({"books": []})




@app.route("/api/books/recent-by-category")
@login_required
def api_books_recent_by_category():
    """Return the N most recently added books per category."""
    try:
        n = int(request.args.get("n", 10))
        conn = database.get_db()

        # Get categories ordered by total book count (largest first)
        categories = conn.execute(
            "SELECT category, COUNT(*) as cnt FROM books WHERE category != '' "
            "GROUP BY category ORDER BY cnt DESC"
        ).fetchall()

        result = []
        for cat_row in categories:
            cat = cat_row["category"]
            total = cat_row["cnt"]
            rows = conn.execute(
                "SELECT * FROM books WHERE category = ? ORDER BY added_at DESC, id DESC LIMIT ?",
                (cat, n)
            ).fetchall()
            books = _group_format_variants([dict(r) for r in rows])
            result.append({
                "category": cat,
                "total": total,
                "books": books,
            })

        conn.close()
        return jsonify({"categories": result})
    except Exception as e:
        logger.error(f"Error in api_books_recent_by_category: {e}")
        return jsonify({"categories": []})


# ── API: Category Order ──────────────────────────────────────────────────────

@app.route("/api/category-order")
@login_required
def api_get_category_order():
    conn = database.get_db()
    row = conn.execute(
        "SELECT category_order FROM user_category_order WHERE user_id = ?",
        (session["user_id"],)
    ).fetchone()
    conn.close()
    return jsonify({"order": json.loads(row["category_order"]) if row else []})


@app.route("/api/category-order", methods=["PUT"])
@login_required
def api_save_category_order():
    data = request.get_json()
    order = data.get("order", [])
    conn = database.get_db()
    conn.execute("""
        INSERT INTO user_category_order (user_id, category_order, updated_at)
        VALUES (?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(user_id) DO UPDATE SET
            category_order = excluded.category_order,
            updated_at = CURRENT_TIMESTAMP
    """, (session["user_id"], json.dumps(order)))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


# ── API: Collections ─────────────────────────────────────────────────────────

@app.route("/api/collections")
@login_required
def api_collections():
    """List all series/collections with book count and cover."""
    try:
        conn = database.get_db()

        category = request.args.get("category", "")
        genre = request.args.get("genre", "")
        search = request.args.get("search", "")
        page = int(request.args.get("page", 1))
        per_page = int(request.args.get("per_page", 50))

        where = "WHERE b.series != ''"
        params = []
        if category:
            where += " AND b.category = ?"
            params.append(category)
        if genre:
            where += " AND b.genre LIKE ?"
            params.append(f"%{genre}%")
        if search:
            where += " AND (b.series LIKE ? OR b.author LIKE ?)"
            params.extend([f"%{search}%"] * 2)

        # Count distinct series
        count_q = f"SELECT COUNT(DISTINCT b.series) FROM books b {where}"
        total = conn.execute(count_q, params).fetchone()[0]

        # Get series with aggregated info
        query = f"""
            SELECT b.series,
                   COUNT(*) as book_count,
                   GROUP_CONCAT(DISTINCT b.author) as authors,
                   GROUP_CONCAT(DISTINCT b.genre) as genres,
                   GROUP_CONCAT(DISTINCT b.category) as categories,
                   MIN(b.id) as first_book_id,
                   MAX(b.has_cover) as has_any_cover
            FROM books b {where}
            GROUP BY b.series
            ORDER BY b.series COLLATE NOCASE ASC
            LIMIT ? OFFSET ?
        """
        params.extend([per_page, (page - 1) * per_page])
        rows = conn.execute(query, params).fetchall()

        collections = []
        for r in rows:
            # Find best cover (first book with cover, ordered by series_index)
            cover_book = conn.execute(
                "SELECT id FROM books WHERE series=? AND has_cover=1 ORDER BY series_index ASC LIMIT 1",
                (r["series"],)
            ).fetchone()
            cover_id = cover_book["id"] if cover_book else r["first_book_id"]

            authors = r["authors"] or ""
            # Deduplicate and take first 3
            author_list = list(dict.fromkeys(a.strip() for a in authors.split(",") if a.strip()))
            author_str = ", ".join(author_list[:3])
            if len(author_list) > 3:
                author_str += f" +{len(author_list)-3}"

            collections.append({
                "series": r["series"],
                "book_count": r["book_count"],
                "author": author_str,
                "genres": r["genres"],
                "categories": r["categories"],
                "cover_book_id": cover_id,
            })

        conn.close()
        return jsonify({
            "collections": collections,
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": (total + per_page - 1) // per_page,
        })
    except Exception as e:
        logger.error(f"Error in api_collections: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/collections/<path:series_name>")
@login_required
def api_collection_detail(series_name):
    """Get collection detail with up to 3 levels: series > sub_series > sub_series_2."""
    try:
        conn = database.get_db()
        sub_filter = request.args.get("sub", "")
        sub2_filter = request.args.get("sub2", "")

        def _find_cover(wc, wp):
            row = conn.execute(f"SELECT id FROM books WHERE {wc} AND has_cover=1 ORDER BY series_index ASC LIMIT 1", wp).fetchone()
            if not row:
                row = conn.execute(f"SELECT id FROM books WHERE {wc} ORDER BY series_index ASC LIMIT 1", wp).fetchone()
            return row["id"] if row else 0

        # Level 3: books in sub_series_2
        if sub_filter and sub2_filter:
            rows = conn.execute(
                "SELECT * FROM books WHERE series=? AND sub_series=? AND sub_series_2=? ORDER BY series_index ASC, title COLLATE NOCASE ASC",
                (series_name, sub_filter, sub2_filter)).fetchall()
            books = _group_format_variants([dict(r) for r in rows])
            conn.close()
            return jsonify({"series": series_name, "sub_series": sub_filter, "sub_series_2": sub2_filter,
                            "books": books, "total": len(books), "type": "books"})

        # Level 2: inside sub_series, check for sub_series_2
        if sub_filter:
            sub2s = conn.execute(
                "SELECT sub_series_2, COUNT(*) as cnt FROM books WHERE series=? AND sub_series=? AND sub_series_2!='' GROUP BY sub_series_2 ORDER BY sub_series_2",
                (series_name, sub_filter)).fetchall()
            no_sub2 = conn.execute(
                "SELECT COUNT(*) FROM books WHERE series=? AND sub_series=? AND sub_series_2=''",
                (series_name, sub_filter)).fetchone()[0]

            if sub2s and (len(sub2s) > 1 or (len(sub2s) == 1 and no_sub2 > 0)):
                sub_list = []
                for s2 in sub2s:
                    cid = _find_cover("series=? AND sub_series=? AND sub_series_2=?",
                                      (series_name, sub_filter, s2["sub_series_2"]))
                    sub_list.append({"sub_series_2": s2["sub_series_2"], "book_count": s2["cnt"], "cover_book_id": cid})
                if no_sub2 > 0:
                    cid = _find_cover("series=? AND sub_series=? AND sub_series_2=''", (series_name, sub_filter))
                    sub_list.insert(0, {"sub_series_2": "", "book_count": no_sub2, "cover_book_id": cid})
                conn.close()
                return jsonify({"series": series_name, "sub_series": sub_filter,
                                "sub_collections": sub_list, "total": sum(s["book_count"] for s in sub_list), "type": "sub_collections_2"})
            else:
                rows = conn.execute(
                    "SELECT * FROM books WHERE series=? AND sub_series=? ORDER BY series_index ASC, title COLLATE NOCASE ASC",
                    (series_name, sub_filter)).fetchall()
                books = _group_format_variants([dict(r) for r in rows])
                conn.close()
                return jsonify({"series": series_name, "sub_series": sub_filter,
                                "books": books, "total": len(books), "type": "books"})

        # Level 1: check for sub_series
        subs = conn.execute(
            "SELECT sub_series, COUNT(*) as cnt FROM books WHERE series=? AND sub_series!='' GROUP BY sub_series ORDER BY sub_series",
            (series_name,)).fetchall()
        no_sub = conn.execute(
            "SELECT COUNT(*) FROM books WHERE series=? AND sub_series=''",
            (series_name,)).fetchone()[0]

        if subs and (len(subs) > 1 or (len(subs) == 1 and no_sub > 0)):
            sub_list = []
            for s in subs:
                cid = _find_cover("series=? AND sub_series=?", (series_name, s["sub_series"]))
                sub_list.append({"sub_series": s["sub_series"], "book_count": s["cnt"], "cover_book_id": cid})
            if no_sub > 0:
                cid = _find_cover("series=? AND sub_series=''", (series_name,))
                sub_list.insert(0, {"sub_series": "", "book_count": no_sub, "cover_book_id": cid})
            conn.close()
            return jsonify({"series": series_name, "sub_collections": sub_list,
                            "total": sum(s["book_count"] for s in sub_list), "type": "sub_collections"})
        else:
            rows = conn.execute(
                "SELECT * FROM books WHERE series=? ORDER BY series_index ASC, title COLLATE NOCASE ASC",
                (series_name,)).fetchall()
            books = _group_format_variants([dict(r) for r in rows])
            conn.close()
            return jsonify({"series": series_name, "books": books, "total": len(books), "type": "books"})
    except Exception as e:
        logger.error(f"Error in api_collection_detail: {e}")
        return jsonify({"error": str(e)}), 500



# ── API: Media Enrichment ────────────────────────────────────────────────────

@app.route("/api/enrichment/status")
def api_enrichment_status():
    """Get media enrichment worker status. No auth required (read-only)."""
    return jsonify(media_worker.get_status())


@app.route("/api/enrichment/start", methods=["POST"])
@login_required
def api_enrichment_start():
    """Manually trigger media enrichment."""
    status = media_worker.get_status()
    if status["running"]:
        return jsonify({"error": "Enrichment already running"}), 409
    media_worker.start_worker()
    return jsonify({"ok": True, "message": "Enrichment started"})


# ── API: Upload ──────────────────────────────────────────────────────────────

def _find_genre_subfolder(lib_path, genre):
    """Find an existing subfolder in lib_path whose name matches genre (case-insensitive).
    Returns the full path if found, else None.
    """
    if not genre or not os.path.isdir(lib_path):
        return None
    genre_lower = genre.lower()
    try:
        for entry in os.scandir(lib_path):
            if entry.is_dir() and entry.name.lower() == genre_lower:
                return entry.path
    except Exception:
        pass
    return None


def _determine_placement(meta, ext):
    """Determine the best library folder for an uploaded book.

    Returns (category, dest_folder, reason, is_new_folder).
    is_new_folder=True when dest_folder does not yet exist on disk.
    """
    # Base category from format
    if ext in ('.cbr', '.cbz'):
        category = 'Comics'
    elif ext in ('.epub', '.mobi'):
        category = 'Books'
    else:  # .pdf
        category = 'Books'

    # Find the library root for that category
    lib_path = next(
        (p for p in config.LIBRARY_PATHS if os.path.basename(p) == category),
        config.LIBRARY_PATHS[0]
    )

    series = (meta.get('series') or '').strip()
    # Use only the first (primary) genre
    genre = (meta.get('genre') or '').split(',')[0].strip()

    # 1. Series takes priority
    if series:
        conn = database.get_db()
        row = conn.execute(
            "SELECT path FROM books WHERE series = ? LIMIT 1", (series,)
        ).fetchone()
        conn.close()

        if row:
            existing_folder = os.path.dirname(row['path'])
            for lib in config.LIBRARY_PATHS:
                norm_lib = os.path.normpath(lib)
                if os.path.normpath(existing_folder).startswith(norm_lib):
                    cat = os.path.basename(lib)
                    return cat, existing_folder, f"Existing series '{series}'", False

        # New series subfolder
        new_folder = os.path.join(lib_path, series)
        return category, new_folder, f"New series folder '{series}'", not os.path.isdir(new_folder)

    # 2. No series — try to match genre to an existing subfolder
    if genre and category in ('Books', 'Education', 'Magazines'):
        existing = _find_genre_subfolder(lib_path, genre)
        if existing:
            return category, existing, f"Genre folder '{os.path.basename(existing)}'", False
        # Suggest creating a new genre subfolder
        new_folder = os.path.join(lib_path, genre.capitalize())
        return category, new_folder, f"New genre folder '{genre.capitalize()}'", True

    # 3. Fallback: category root (always exists)
    return category, lib_path, f"{category} library root", False


@app.route("/api/upload/analyze", methods=["POST"])
@login_required
def api_upload_analyze():
    """Accept an uploaded file, extract metadata and suggest a placement path."""
    if 'file' not in request.files:
        return jsonify({"error": "No file provided"}), 400

    f = request.files['file']
    if not f.filename:
        return jsonify({"error": "No filename"}), 400

    filename = _safe_filename(f.filename)
    if not filename:
        return jsonify({"error": "Invalid filename"}), 400
    ext = os.path.splitext(filename)[1].lower()
    if ext not in config.SUPPORTED_FORMATS:
        return jsonify({"error": f"Unsupported format '{ext}'. Allowed: {', '.join(sorted(config.SUPPORTED_FORMATS))}"}), 400

    # Save to a temp upload folder
    temp_dir = os.path.join(os.path.dirname(__file__), 'data', 'uploads')
    os.makedirs(temp_dir, exist_ok=True)
    temp_id = str(uuid.uuid4())
    temp_path = os.path.join(temp_dir, temp_id + ext)
    f.save(temp_path)

    try:
        # Extract metadata using scanner
        root = temp_dir  # use temp dir as root so series-from-folder won't fire
        meta = scanner._extract_metadata(temp_path, filename, ext, 'Books', root)
        # Clear any series/collection inferred from the temp upload folder name
        if meta.get('series') in ('uploads', os.path.basename(temp_dir)):
            meta['series'] = ''
            meta['series_index'] = 0
            meta['collection_path'] = ''

        # Determine placement
        category, dest_folder, reason, is_new_folder = _determine_placement(meta, ext)
        meta['category'] = category

        _pending_uploads[temp_id] = {
            'temp_path': temp_path,
            'filename': filename,
            'ext': ext,
            'meta': meta,
            'dest_folder': dest_folder,
        }

        return jsonify({
            'upload_id': temp_id,
            'filename': filename,
            'title': meta.get('title', ''),
            'author': meta.get('author', ''),
            'series': meta.get('series', ''),
            'series_index': meta.get('series_index', 0),
            'category': category,
            'format': ext.lstrip('.'),
            'genre': meta.get('genre', '').split(',')[0].strip(),
            'dest_folder': dest_folder,
            'placement_reason': reason,
            'is_new_folder': is_new_folder,
        })
    except Exception as e:
        try:
            os.unlink(temp_path)
        except Exception:
            pass
        logger.error(f"Upload analyze error: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/upload/confirm", methods=["POST"])
@login_required
def api_upload_confirm():
    """Move the pending upload to the library and add it to the database."""
    data = request.get_json()
    upload_id = data.get('upload_id')

    if not upload_id or upload_id not in _pending_uploads:
        return jsonify({"error": "Invalid or expired upload ID"}), 400

    # Validate dest_folder BEFORE consuming the upload entry so the user can
    # retry with a corrected path if validation fails.
    pending = _pending_uploads[upload_id]
    dest_folder = data.get('dest_folder') or pending['dest_folder']

    abs_dest = os.path.normpath(os.path.abspath(dest_folder))
    allowed = any(
        abs_dest == os.path.normpath(os.path.abspath(p))
        or abs_dest.startswith(os.path.normpath(os.path.abspath(p)) + os.sep)
        for p in config.LIBRARY_PATHS
    )
    if not allowed:
        return jsonify({"error": "Invalid destination folder"}), 400

    pending = _pending_uploads.pop(upload_id)
    temp_path = pending['temp_path']

    # Allow user to override any metadata field.
    # An explicit empty string means "clear this field" (user cleared the input).
    meta = pending['meta'].copy()
    for field in ('title', 'author', 'series', 'series_index', 'category', 'genre'):
        if field in data:
            meta[field] = data[field]

    filename = pending['filename']
    ext = pending['ext']

    try:
        os.makedirs(dest_folder, exist_ok=True)
        dest_path = os.path.join(dest_folder, filename)

        # Avoid overwriting an existing file
        if os.path.exists(dest_path):
            base = os.path.splitext(filename)[0]
            dest_path = os.path.join(dest_folder, f"{base}_upload{ext}")

        shutil.move(temp_path, dest_path)

        # Re-extract cover now that the file is at its final path
        cover_data = meta.pop('_cover_data', None)
        cover_ok = scanner._extract_cover(dest_path, ext, cover_data)

        collection_path = (meta.get('series') or '').strip()

        conn = database.get_db()
        conn.execute("""
            INSERT OR REPLACE INTO books
              (path, filename, title, author, genre, series, series_index,
               category, format, file_size, has_cover, page_count, description,
               collection_path)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            dest_path, os.path.basename(dest_path),
            meta.get('title', ''), meta.get('author', ''),
            meta.get('genre', ''), meta.get('series', ''),
            meta.get('series_index', 0), meta.get('category', ''),
            ext.lstrip('.'), os.path.getsize(dest_path),
            1 if cover_ok else 0,
            meta.get('page_count', 0), meta.get('description', ''),
            collection_path,
        ))
        conn.commit()
        book = conn.execute("SELECT id FROM books WHERE path = ?", (dest_path,)).fetchone()
        book_id = book['id'] if book else None
        conn.close()

        logger.info(f"Upload complete: '{meta.get('title')}' → {dest_path}")
        return jsonify({
            "ok": True,
            "book_id": book_id,
            "dest_path": dest_path,
            "title": meta.get('title', ''),
            "category": meta.get('category', ''),
        })
    except Exception as e:
        if os.path.exists(temp_path):
            try:
                os.unlink(temp_path)
            except Exception:
                pass
        logger.error(f"Upload confirm error: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/upload/suggest-path")
@login_required
def api_upload_suggest_path():
    """Return a suggested destination folder given series/genre + category."""
    series = request.args.get('series', '').strip()
    genre = request.args.get('genre', '').strip()
    category = request.args.get('category', 'Books').strip()

    lib_path = next(
        (p for p in config.LIBRARY_PATHS if os.path.basename(p) == category),
        config.LIBRARY_PATHS[0]
    )

    if series:
        conn = database.get_db()
        row = conn.execute(
            "SELECT path FROM books WHERE series = ? LIMIT 1", (series,)
        ).fetchone()
        conn.close()
        if row:
            existing_folder = os.path.dirname(row['path'])
            for lib in config.LIBRARY_PATHS:
                if os.path.normpath(existing_folder).startswith(os.path.normpath(lib)):
                    return jsonify({
                        "dest_folder": existing_folder,
                        "reason": f"Existing series '{series}'",
                        "is_new_folder": False,
                    })
        new_folder = os.path.join(lib_path, series)
        return jsonify({
            "dest_folder": new_folder,
            "reason": f"New series folder '{series}'",
            "is_new_folder": not os.path.isdir(new_folder),
        })

    if genre and category in ('Books', 'Education', 'Magazines'):
        existing = _find_genre_subfolder(lib_path, genre)
        if existing:
            return jsonify({
                "dest_folder": existing,
                "reason": f"Genre folder '{os.path.basename(existing)}'",
                "is_new_folder": False,
            })
        new_folder = os.path.join(lib_path, genre.capitalize())
        return jsonify({
            "dest_folder": new_folder,
            "reason": f"New genre folder '{genre.capitalize()}'",
            "is_new_folder": True,
        })

    return jsonify({
        "dest_folder": lib_path,
        "reason": f"{category} library root",
        "is_new_folder": False,
    })


@app.route("/api/upload/cancel", methods=["POST"])
@login_required
def api_upload_cancel():
    """Cancel a pending upload and delete the temp file."""
    data = request.get_json()
    upload_id = data.get('upload_id')
    if upload_id and upload_id in _pending_uploads:
        pending = _pending_uploads.pop(upload_id)
        try:
            os.unlink(pending['temp_path'])
        except Exception:
            pass
    return jsonify({"ok": True})


# ── Frontend Routes ──────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html", version=__version__)


@app.route("/api/version")
def api_version():
    return jsonify({"version": __version__})


@app.route("/download")
def download_page():
    return render_template("download.html", version=__version__)


# ── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logger.info("BookHaven starting...")
    logger.info(f"  Database: {config.DB_PATH}")
    logger.info(f"  Libraries: {config.LIBRARY_PATHS}")
    logger.info(f"  rarfile support: {HAS_RARFILE}")

    # Initialize database
    database.init_db()

    # Migrate any legacy /books/... paths left in DB to current BOOKS_ROOT
    _migrate_legacy_paths()

    # Create static img dir
    os.makedirs(os.path.join(app.static_folder, "img"), exist_ok=True)

    # Start background media enrichment worker
    media_worker.start_worker()
    logger.info("Media enrichment worker launched")

    # Use HTTPS if cert files exist
    cert_file = os.path.join(config.BASE_DIR, "server.crt")
    key_file = os.path.join(config.BASE_DIR, "server.key")
    ssl_ctx = None
    if os.path.exists(cert_file) and os.path.exists(key_file):
        ssl_ctx = (cert_file, key_file)
        logger.info(f"Server starting on https://{config.HOST}:{config.PORT}")
    else:
        logger.info(f"Server starting on http://{config.HOST}:{config.PORT}")
    app.run(host=config.HOST, port=config.PORT, debug=False, threaded=True, ssl_context=ssl_ctx)
