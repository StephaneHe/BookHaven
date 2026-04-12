"""BookHaven configuration"""
import os
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Library paths to scan
# In Docker, H:\Books is mounted at /books
_BOOKS_ROOT = os.environ.get("BOOKS_ROOT", r"H:\Books")
LIBRARY_PATHS = [
    os.path.join(_BOOKS_ROOT, "Books"),
    os.path.join(_BOOKS_ROOT, "Comics"),
    os.path.join(_BOOKS_ROOT, "Education"),
    os.path.join(_BOOKS_ROOT, "Magazines"),
    os.path.join(_BOOKS_ROOT, "Professionel"),
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

# Jellyfin API for authentication
JELLYFIN_URL = os.environ.get("JELLYFIN_URL", "http://localhost:8096")
JELLYFIN_API_KEY = os.environ.get("JELLYFIN_API_KEY", "")

# Session secret
SECRET_KEY = os.environ.get("BOOKHAVEN_SECRET_KEY", "bookhaven-dev-secret")

# Scanner settings
SCAN_BATCH_SIZE = 100  # commit every N books

# UnRAR tool path (needed for CBR extraction)
UNRAR_TOOL = os.environ.get("UNRAR_TOOL", r"C:\Program Files\WinRAR\UnRAR.exe")
