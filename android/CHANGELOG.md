# Changelog — BookHaven Android

## [1.0.0] - 2026-07-14

### Added
- Initial release of the native Android client for BookHaven
- Server configuration screen (VPN URL stored in SharedPreferences)
- User login via POST /api/auth/login with persistent session cookie (MemoryCookieJar)
- Library grid view with cover images (Coil), title, author, search, category chip filters
- Download badge on downloaded books; spinner badge while downloading
- Download manager: saves EPUB/PDF/CBZ/CBR to getExternalFilesDir("books"), tracked in Room DB
- Offline library view showing only locally stored books with delete (long-press)
- EPUB reader: WebView + epub.js bundled in assets/, serves via /api/books/:id/file
- PDF reader: Android PdfRenderer in vertical RecyclerView
- Comic reader (CBZ): ViewPager2 with pages extracted via ZipInputStream, page counter overlay
- Reading progress saved to Room DB (CFI string for EPUB, page for PDF/comics)
- Dark theme matching BookHaven web UI (#0f0f1a background, #7c8cf5 primary)
- minSdk 26, targetSdk 35, Kotlin, Hilt, Retrofit2, Room, Coil, Navigation Component
