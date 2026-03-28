"""BookHaven library scanner - extracts metadata and covers from book files."""
import os
import re
import zipfile
import hashlib
import xml.etree.ElementTree as ET
from io import BytesIO
import logging

try:
    import rarfile
    HAS_RARFILE = True
except ImportError:
    HAS_RARFILE = False

from genre_ai import classify_genre

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

try:
    import fitz  # PyMuPDF for PDF cover extraction
    HAS_FITZ = True
except ImportError:
    HAS_FITZ = False

import config
import database

# Configure unrar tool for CBR support
if HAS_RARFILE and hasattr(config, 'UNRAR_TOOL') and os.path.exists(config.UNRAR_TOOL):
    rarfile.UNRAR_TOOL = config.UNRAR_TOOL

logger = logging.getLogger("bookhaven.scanner")

# Image extensions for comic archives
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"}


def scan_library(progress_callback=None):
    """Scan all configured library paths and update the database.
    
    Args:
        progress_callback: optional callable(current, total, message)
    """
    conn = database.get_db()
    
    # Get existing books to detect removed files
    existing = {row["path"] for row in conn.execute("SELECT path FROM books").fetchall()}
    found_paths = set()
    new_count = 0
    updated_count = 0
    
    # Collect all files first
    all_files = []
    for lib_path in config.LIBRARY_PATHS:
        if not os.path.isdir(lib_path):
            logger.warning(f"Library path not found: {lib_path}")
            continue
        category = _get_category(lib_path)
        for root, dirs, files in os.walk(lib_path):
            for fname in files:
                ext = os.path.splitext(fname)[1].lower()
                if ext in config.SUPPORTED_FORMATS:
                    full_path = os.path.join(root, fname)
                    all_files.append((full_path, fname, ext, category, root))
    
    total = len(all_files)
    logger.info(f"Found {total} book files to process")
    
    for idx, (full_path, fname, ext, category, root) in enumerate(all_files):
        found_paths.add(full_path)
        
        if progress_callback:
            progress_callback(idx, total, f"Scanning: {fname[:60]}")
        
        try:
            file_size = os.path.getsize(full_path)
            file_mtime = os.path.getmtime(full_path)
            
            # Check if already scanned and unchanged
            row = conn.execute(
                "SELECT id, file_size, genre FROM books WHERE path = ?",
                (full_path,)
            ).fetchone()

            if row and row["file_size"] == file_size and row["genre"]:
                continue  # Already scanned, same size, has genre = skip
            
            # Extract metadata based on format
            meta = _extract_metadata(full_path, fname, ext, category, root)
            meta["path"] = full_path
            meta["filename"] = fname
            meta["format"] = ext.lstrip(".")
            meta["file_size"] = file_size
            
            # Extract cover
            cover_ok = _extract_cover(full_path, ext, meta.get("_cover_data"))
            meta["has_cover"] = 1 if cover_ok else 0
            
            # Remove internal fields
            meta.pop("_cover_data", None)
            
            # Derive collection_path from series if available
            collection_path = meta.get("series") or ""

            if row:
                # Update existing
                conn.execute("""
                    UPDATE books SET title=?, author=?, genre=?, series=?,
                    series_index=?, category=?, format=?, file_size=?,
                    has_cover=?, page_count=?, description=?,
                    collection_path=CASE WHEN (collection_path IS NULL OR collection_path='') THEN ? ELSE collection_path END,
                    modified_at=CURRENT_TIMESTAMP
                    WHERE id=?
                """, (meta["title"], meta["author"], meta["genre"],
                      meta["series"], meta["series_index"],
                      meta["category"], meta["format"], meta["file_size"], meta["has_cover"],
                      meta.get("page_count", 0), meta.get("description", ""),
                      collection_path, row["id"]))
                updated_count += 1
            else:
                # Insert new
                conn.execute("""
                    INSERT INTO books (path, filename, title, author, genre, series,
                    series_index, category, format, file_size, has_cover, page_count, description,
                    collection_path)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (meta["path"], meta["filename"], meta["title"],
                      meta["author"], meta["genre"], meta["series"],
                      meta["series_index"], meta["category"], meta["format"],
                      meta["file_size"], meta["has_cover"],
                      meta.get("page_count", 0), meta.get("description", ""),
                      collection_path))
                new_count += 1
            
            conn.commit()
                
        except Exception as e:
            logger.error(f"Error scanning {full_path}: {e}")
    
    # Remove books whose files no longer exist
    removed_paths = existing - found_paths
    if removed_paths:
        for rpath in removed_paths:
            conn.execute("DELETE FROM books WHERE path = ?", (rpath,))
        logger.info(f"Removed {len(removed_paths)} books no longer on disk")
    
    conn.commit()
    conn.close()
    
    msg = f"Scan complete: {new_count} new, {updated_count} updated, {len(removed_paths)} removed"
    logger.info(msg)
    if progress_callback:
        progress_callback(total, total, msg)
    
    # Post-scan: auto-assign collections to books without series (always run)
    try:
        assigned = assign_collections()
        if assigned > 0:
            msg += f", {assigned} auto-classified"
            logger.info(f"Auto-classified {assigned} books into collections")
    except Exception as e:
        logger.error(f"Collection assignment error: {e}")
    
    return {"new": new_count, "updated": updated_count, "removed": len(removed_paths), "total": total}


def _get_category(lib_path):
    """Get category from library path."""
    folder_name = os.path.basename(lib_path)
    return config.CATEGORY_MAP.get(folder_name, folder_name)


_KNOWN_GENRES = {
    "article", "autres", "aventure", "bit-lit", "drame", "espionnage",
    "fantastique", "fantasy", "historique", "jeunesse", "philosophie",
    "policier", "romance", "science-fiction", "thriller", "horreur",
    "humour", "biographie", "essai", "poesie", "info",
}

# Maps common EPUB dc:subject values and LLM variants to canonical genres
_GENRE_ALIASES = {
    "sf": "Science-Fiction", "science fiction": "Science-Fiction",
    "sci-fi": "Science-Fiction",
    "bd": "Comics", "bande dessinee": "Comics", "bande dessinée": "Comics",
    "comic": "Comics", "comics": "Comics", "manga": "Comics",
    "roman": "Autres", "roman fantastique": "Fantastique",
    "roman historique": "Historique", "urban fantasy": "Fantasy",
    "terreur": "Horreur", "suspense": "Thriller", "suspence": "Thriller",
    "light novel": "Jeunesse", "young adult fiction": "Jeunesse",
    "litterature": "Autres", "littérature": "Autres",
    "anticipation": "Science-Fiction", "presse": "Article",
    "theatre": "Autres", "théâtre": "Autres",
}


def normalize_genre(raw_genre):
    """Normalize a genre string to a known canonical genre.

    Returns the canonical genre if recognized, or '' if not.
    """
    if not raw_genre:
        return ""
    low = raw_genre.strip().lower()
    # Direct match against known genres
    for g in _KNOWN_GENRES:
        if g == low:
            return g.capitalize() if g != "bit-lit" else "Bit-Lit"
    # Check aliases
    if low in _GENRE_ALIASES:
        return _GENRE_ALIASES[low]
    return ""


def _genre_from_path(full_path):
    """Infer genre from a subfolder whose name matches a known genre.

    Example: H:\\Books\\Education\\philosophie\\book.pdf -> 'Philosophie'
    Only assigns genre when the folder name is in _KNOWN_GENRES,
    to avoid tagging series or author folders as genres.
    """
    for lib_path in config.LIBRARY_PATHS:
        norm_lib = os.path.normpath(lib_path)
        norm_full = os.path.normpath(full_path)
        if norm_full.startswith(norm_lib + os.sep):
            rel = os.path.relpath(norm_full, norm_lib)
            parts = rel.split(os.sep)
            for part in parts[:-1]:  # skip the filename itself
                if part.lower() in _KNOWN_GENRES:
                    return part.capitalize()
    return ""


def _extract_metadata(full_path, fname, ext, category, root):
    """Extract metadata based on file format."""
    meta = {
        "title": "",
        "author": "",
        "genre": "",
        "series": "",
        "series_index": 0,
        "collection_path": "",
        "category": category,
        "description": "",
        "page_count": 0,
        "_cover_data": None,
    }
    
    if ext == ".epub":
        _parse_epub(full_path, meta)
    elif ext in (".cbr", ".cbz"):
        _parse_comic(full_path, fname, ext, meta, root)
    elif ext == ".pdf":
        _parse_pdf(full_path, fname, meta, root)
    elif ext == ".mobi":
        _parse_filename(fname, meta, root)
    
    # Fallback: parse filename if title is still empty
    if not meta["title"]:
        _parse_filename(fname, meta, root)
    
    # Clean up
    meta["title"] = meta["title"].strip()
    meta["author"] = meta["author"].strip()
    meta["genre"] = meta["genre"].strip()

    # Fallback 1: infer genre from subfolder name if still empty
    if not meta["genre"]:
        meta["genre"] = _genre_from_path(full_path)

    # Fallback 2: ask local LLM via Ollama
    if not meta["genre"]:
        meta["genre"] = classify_genre(meta["title"], meta["author"])

    return meta


def _parse_epub(full_path, meta):
    """Extract metadata from EPUB file (OPF)."""
    try:
        with zipfile.ZipFile(full_path, "r") as zf:
            # Find the OPF file
            opf_path = None
            for name in zf.namelist():
                if name.endswith(".opf"):
                    opf_path = name
                    break
            
            if not opf_path:
                # Try via container.xml
                try:
                    container = ET.fromstring(zf.read("META-INF/container.xml"))
                    ns = {"c": "urn:oasis:names:tc:opendocument:xmlns:container"}
                    rootfile = container.find(".//c:rootfile", ns)
                    if rootfile is not None:
                        opf_path = rootfile.get("full-path")
                except Exception:
                    pass
            
            if not opf_path:
                return
            
            opf_content = zf.read(opf_path)
            root = ET.fromstring(opf_content)
            
            ns = {
                "dc": "http://purl.org/dc/elements/1.1/",
                "opf": "http://www.idpf.org/2007/opf",
            }
            
            # Title
            el = root.find(".//dc:title", ns)
            if el is not None and el.text:
                meta["title"] = el.text.strip()
            
            # Author
            el = root.find(".//dc:creator", ns)
            if el is not None and el.text:
                meta["author"] = el.text.strip()
            
            # Genre/Subject - normalize to known genres only, keep up to 3
            subjects = root.findall(".//dc:subject", ns)
            if subjects:
                matched = []
                for s in subjects:
                    if s.text:
                        g = normalize_genre(s.text.strip())
                        if g and g not in matched:
                            matched.append(g)
                if matched:
                    meta["genre"] = ", ".join(matched[:3])
            
            # Description
            el = root.find(".//dc:description", ns)
            if el is not None and el.text:
                meta["description"] = el.text.strip()[:500]
            
            # Cover image extraction
            cover_id = None
            # Method 1: meta cover tag
            for m in root.findall(".//opf:meta", ns):
                if m.get("name") == "cover":
                    cover_id = m.get("content")
                    break
            
            # Method 2: look in manifest for cover item
            if not cover_id:
                for item in root.findall(".//{http://www.idpf.org/2007/opf}item"):
                    item_id = item.get("id", "").lower()
                    href = item.get("href", "").lower()
                    if "cover" in item_id or "cover" in href:
                        mtype = item.get("media-type", "")
                        if mtype.startswith("image/"):
                            cover_id = item.get("id")
                            break
            
            if cover_id:
                # Find the href for this cover id
                for item in root.findall(".//{http://www.idpf.org/2007/opf}item"):
                    if item.get("id") == cover_id:
                        cover_href = item.get("href")
                        if cover_href:
                            # Resolve relative path
                            opf_dir = os.path.dirname(opf_path)
                            cover_path = os.path.join(opf_dir, cover_href).replace("\\", "/")
                            # Also try without opf_dir
                            for try_path in [cover_path, cover_href]:
                                try_path = try_path.replace("\\", "/")
                                if try_path in zf.namelist():
                                    meta["_cover_data"] = zf.read(try_path)
                                    break
                        break
    except Exception as e:
        logger.debug(f"EPUB parse error for {full_path}: {e}")


def _parse_comic(full_path, fname, ext, meta, root):
    """Extract metadata from CBR/CBZ comic file."""
    # Parse title/series from filename and folder structure
    _parse_filename(fname, meta, root)
    
    # Try to extract cover (first image)
    try:
        if ext == ".cbz":
            with zipfile.ZipFile(full_path, "r") as zf:
                images = sorted([
                    n for n in zf.namelist()
                    if os.path.splitext(n)[1].lower() in IMAGE_EXTS
                    and not n.startswith("__MACOSX")
                    and "/." not in n
                ])
                if images:
                    meta["page_count"] = len(images)
                    meta["_cover_data"] = zf.read(images[0])
        elif ext == ".cbr":
            # Many CBR files are actually ZIP archives
            opened = False
            try:
                zf = zipfile.ZipFile(full_path, "r")
                images = sorted([
                    n for n in zf.namelist()
                    if os.path.splitext(n)[1].lower() in IMAGE_EXTS
                    and not n.startswith("__MACOSX") and "/." not in n
                ])
                if images:
                    meta["page_count"] = len(images)
                    meta["_cover_data"] = zf.read(images[0])
                zf.close()
                opened = True
            except zipfile.BadZipFile:
                pass
            if not opened and HAS_RARFILE:
                with rarfile.RarFile(full_path, "r") as rf:
                    images = sorted([
                        n for n in rf.namelist()
                        if os.path.splitext(n)[1].lower() in IMAGE_EXTS
                        and not n.startswith("__MACOSX") and "/." not in n
                    ])
                    if images:
                        meta["page_count"] = len(images)
                        meta["_cover_data"] = rf.read(images[0])
    except Exception as e:
        logger.debug(f"Comic parse error for {full_path}: {e}")


def _parse_pdf(full_path, fname, meta, root):
    """Extract metadata and cover from PDF."""
    _parse_filename(fname, meta, root)
    if HAS_FITZ:
        try:
            doc = fitz.open(full_path)
            if doc.page_count > 0:
                meta["page_count"] = doc.page_count
                page = doc[0]
                mat = fitz.Matrix(150 / 72, 150 / 72)
                pix = page.get_pixmap(matrix=mat)
                meta["_cover_data"] = pix.tobytes("jpeg")
            doc.close()
        except Exception as e:
            logger.debug(f"PDF cover extraction error {full_path}: {e}")


def _parse_filename(fname, meta, root):
    """Parse title and author from filename patterns.
    
    Common patterns:
    - "Title - Author.ext"
    - "Author - Title.ext"
    - "Series - T01 - Title.ext"
    - "Title (Year).ext"
    """
    name = os.path.splitext(fname)[0]
    
    # Remove common tags like [BD][MULTI], {{hash}}, (year)
    name = re.sub(r"\[.*?\]", "", name)
    name = re.sub(r"\{\{.*?\}\}", "", name)
    name = re.sub(r"\(\d{4}\)", "", name)
    name = name.strip(" -_.")
    
    # Try to extract series index: T01, Tome 01, Vol. 1, Vol_ 1, #1, etc.
    idx_match = re.search(r"(?:T|Tome|Vol[.\s_]*|Volume|#)\s*(\d+)", name, re.IGNORECASE)
    if idx_match:
        meta["series_index"] = float(idx_match.group(1))
    
    # Handle numeric prefix: "01 - Real Title" or "001 - Real Title"
    num_prefix = re.match(r"^(\d{1,3})\s*[-–]\s+(.+)", name)
    if num_prefix:
        meta["series_index"] = float(num_prefix.group(1))
        name = num_prefix.group(2).strip()
    
    # Try "Author - Title" or "Title - Author" pattern
    parts = [p.strip() for p in name.split(" - ") if p.strip()]
    
    if len(parts) >= 2:
        # Heuristic: if last part looks like an author name (short, no numbers)
        last = parts[-1]
        if len(last.split()) <= 4 and not re.search(r"\d", last):
            meta["author"] = last
            meta["title"] = " - ".join(parts[:-1])
        else:
            meta["title"] = " - ".join(parts)
    elif parts:
        meta["title"] = parts[0]
    else:
        meta["title"] = name
    
    # Try to get series from parent folder name
    parent = os.path.basename(root)
    # Don't use top-level category folders as series
    if parent not in ("Books", "Comics", "Education", "Magazines"):
        # Only set series if it's different from the title
        if parent != meta["title"] and len(parent) > 2:
            meta["series"] = parent
            meta["collection_path"] = parent

    # Detect series from "Series Name, Vol N" / "Series Name Vol N" title patterns
    if not meta["series"]:
        vol_in_title = re.match(
            r'^(.+?),?\s+(?:Vol[.\s_]*|Volume\s*|Tome\s*|T)(\d+)\s*$',
            meta["title"], re.IGNORECASE
        )
        if vol_in_title:
            candidate = vol_in_title.group(1).strip()
            if len(candidate) >= 3:
                meta["series"] = candidate
                meta["collection_path"] = candidate
                if not meta["series_index"]:
                    meta["series_index"] = float(vol_in_title.group(2))


def _extract_cover(full_path, ext, cover_data):
    """Save cover image to cache directory.
    
    Returns True if cover was saved.
    """
    if not cover_data:
        return False
    
    try:
        # Generate cover filename from book path hash
        path_hash = hashlib.md5(full_path.encode()).hexdigest()
        cover_path = os.path.join(config.COVER_CACHE_DIR, f"{path_hash}.jpg")
        
        if os.path.exists(cover_path):
            return True  # Already cached
        
        os.makedirs(config.COVER_CACHE_DIR, exist_ok=True)
        
        if HAS_PIL:
            # Resize cover to reasonable thumbnail size
            img = Image.open(BytesIO(cover_data))
            img.thumbnail((300, 450), Image.LANCZOS)
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            img.save(cover_path, "JPEG", quality=85)
        else:
            # Save as-is
            with open(cover_path, "wb") as f:
                f.write(cover_data)
        
        return True
    except Exception as e:
        logger.debug(f"Cover extraction error for {full_path}: {e}")
        return False



def assign_collections(conn=None):
    """Post-scan: assign series/collection_path to books that have none.
    
    Detection methods:
    1. [SeriesName-N] bracket pattern in filenames (AlexandriZ format)
    2. Title prefix matching against existing series in DB
    3. Title similarity (e.g., "Ellana", "Ellana - L'envol" -> same series)
    """
    close_conn = False
    if conn is None:
        conn = database.get_db()
        close_conn = True
    
    total_assigned = 0
    
    # ── Method 1: Bracket pattern [SeriesName-N] ─────────────────
    bracket_re = re.compile(r'\[([^\]]+?)-(\d+)\]')
    
    # Also fix books that have series from folder-name parsing but no collection_path yet
    conn.execute("""
        UPDATE books SET collection_path = series
        WHERE series != '' AND series IS NOT NULL
        AND (collection_path IS NULL OR collection_path = '')
    """)

    orphans = conn.execute(
        "SELECT id, filename, title, author FROM books WHERE (series IS NULL OR series='') "
    ).fetchall()

    # Build a map of existing series (lowercase -> canonical name)
    existing_series = {}
    for r in conn.execute("SELECT DISTINCT series FROM books WHERE series != ''").fetchall():
        existing_series[r[0].lower()] = r[0]

    for r in orphans:
        fn = r["filename"]
        m = bracket_re.search(fn)
        if m:
            series_name = m.group(1).strip()
            vol_num = m.group(2)
            
            # Use canonical form if exists
            low = series_name.lower()
            if low in existing_series:
                series_name = existing_series[low]
            else:
                existing_series[low] = series_name
            
            conn.execute(
                "UPDATE books SET series=?, collection_path=?, series_index=? WHERE id=?",
                (series_name, series_name, float(vol_num), r["id"])
            )
            total_assigned += 1
    
    # ── Method 2: Title prefix matching ──────────────────────────
    # Reload orphans (some were fixed by method 1)
    orphans = conn.execute(
        "SELECT id, filename, title, author FROM books WHERE (series IS NULL OR series='') "
    ).fetchall()
    
    # For each orphan, check if its title is a prefix of an existing series name
    # or if an existing series name is a prefix of its title
    # e.g., title "Ellana - L'envol" matches series "Le Pacte des MarchOmbres"? No.
    # Better: group orphans by author, then find common title prefixes
    
    # Method 2b: Match against existing series by checking if title starts with series name
    # or if title contains the series name
    for r in orphans:
        title = r["title"]
        title_low = title.lower()
        
        best_match = None
        best_len = 0
        
        for series_low, series_canon in existing_series.items():
            # Check if title starts with series name
            if title_low.startswith(series_low) and len(series_low) > best_len:
                # Make sure it's a word boundary (not just a random prefix)
                rest = title_low[len(series_low):]
                if not rest or rest[0] in (' ', '-', ',', ':', '.', '_'):
                    best_match = series_canon
                    best_len = len(series_low)
        
        if best_match and best_len >= 3:
            conn.execute(
                "UPDATE books SET series=?, collection_path=? WHERE id=?",
                (best_match, best_match, r["id"])
            )
            total_assigned += 1
    
    # ── Method 3: Detect new series from common title prefixes ───
    # Group remaining orphans by author, find shared title prefixes
    orphans = conn.execute(
        "SELECT id, filename, title, author FROM books WHERE (series IS NULL OR series='') "
        "AND author != ''"
    ).fetchall()
    
    from collections import defaultdict
    by_author = defaultdict(list)
    for r in orphans:
        by_author[r["author"]].append(dict(r))
    
    for author, books in by_author.items():
        if len(books) < 2:
            continue
        
        # Find common title prefixes (at least 3 chars, word boundary)
        titles = [b["title"] for b in books]
        for i, t1 in enumerate(titles):
            for t2 in titles[i+1:]:
                # Find common prefix
                prefix = os.path.commonprefix([t1, t2]).rstrip(' -:,.')
                if len(prefix) >= 4:
                    # Check: how many titles share this prefix?
                    matching = [b for b in books if b["title"].startswith(prefix)]
                    if len(matching) >= 2:
                        # Check it's a real series name (word boundary)
                        series_name = prefix.strip()
                        if series_name and series_name.lower() not in existing_series:
                            existing_series[series_name.lower()] = series_name
                            for b in matching:
                                conn.execute(
                                    "UPDATE books SET series=?, collection_path=? WHERE id=?",
                                    (series_name, series_name, b["id"])
                                )
                                total_assigned += 1
                        break  # One prefix per author group is enough
    
    # ── Method 4: Extract series from "Title, Vol N" / "Title Vol N" patterns ──
    # Handles titles like "The Unwanted Undead Adventurer, Vol_ 04"
    orphans = conn.execute(
        "SELECT id, title FROM books WHERE (series IS NULL OR series='') "
    ).fetchall()

    vol_re = re.compile(
        r'^(.+?),?\s+(?:Vol[.\s_]*|Volume\s*|Tome\s*|T)(\d+)\s*$', re.IGNORECASE
    )
    for r in orphans:
        m = vol_re.match(r["title"] or "")
        if not m:
            continue
        series_name = m.group(1).strip()
        vol_num = float(m.group(2))
        if len(series_name) < 3:
            continue
        low = series_name.lower()
        if low in existing_series:
            series_name = existing_series[low]
        else:
            existing_series[low] = series_name
        conn.execute(
            "UPDATE books SET series=?, collection_path=?, series_index=? WHERE id=?",
            (series_name, series_name, vol_num, r["id"])
        )
        total_assigned += 1

    conn.commit()
    if close_conn:
        conn.close()

    logger.info(f"Collection assignment: {total_assigned} books assigned to series")
    return total_assigned


def get_cover_path(book_path):
    """Get the cached cover image path for a book."""
    path_hash = hashlib.md5(book_path.encode()).hexdigest()
    cover_path = os.path.join(config.COVER_CACHE_DIR, f"{path_hash}.jpg")
    if os.path.exists(cover_path):
        return cover_path
    return None
