"""BookHaven configuration"""
import os
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Library root — set BOOKS_ROOT env var to override (e.g. D:\MyBooks)
BOOKS_ROOT = os.environ.get("BOOKS_ROOT", r"H:\Books")

LIBRARY_PATHS = [
    os.path.join(BOOKS_ROOT, "Books"),
    os.path.join(BOOKS_ROOT, "Comics"),
    os.path.join(BOOKS_ROOT, "Education"),
    os.path.join(BOOKS_ROOT, "Magazines"),
    os.path.join(BOOKS_ROOT, "Professionel"),
]

# Category mapping from top-level folder name
CATEGORY_MAP = {
    "Books": "Books",
    "Comics": "Comics",
    "Education": "Education",
    "Magazines": "Magazines",
    "Professionel": "Professionnel",
}

# Supported file extensions
SUPPORTED_FORMATS = {".epub", ".pdf", ".cbr", ".cbz", ".mobi"}

# Database
DB_PATH = os.path.join(BASE_DIR, "data", "bookhaven.db")

# Cover cache
COVER_CACHE_DIR = os.path.join(BASE_DIR, "cache", "covers")

# Server
HOST = "0.0.0.0"
PORT = int(os.environ.get("BOOKHAVEN_PORT", 8097))

# Session secret
SECRET_KEY = os.environ.get("BOOKHAVEN_SECRET_KEY", "bookhaven-dev-secret")

# Scanner settings
SCAN_BATCH_SIZE = 100  # commit every N books

# UnRAR tool path (needed for CBR extraction)
UNRAR_TOOL = os.environ.get("UNRAR_TOOL", r"C:\Program Files\WinRAR\UnRAR.exe")

# Calibre ebook-convert (needed for PDF→EPUB conversion)
CALIBRE_CONVERT = os.environ.get(
    "CALIBRE_CONVERT",
    r"C:\Program Files (x86)\Calibre2\ebook-convert.exe",
)
