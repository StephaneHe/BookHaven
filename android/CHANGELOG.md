# Changelog — BookHaven Android

## [1.4.0] - 2026-08-21

### Fixed
- **Un livre lu sur le web s'ouvrait sur le téléphone à la position de DÉPART
  de la session web, pas à la position courante.** Les lecteurs (EPUB/PDF/CBZ)
  restauraient uniquement la progression **locale** (Room) et ne récupéraient
  jamais la position enregistrée côté serveur, donc toute lecture faite sur un
  autre appareil était ignorée. `DownloadRepository.resolveProgress()` réconcilie
  désormais local et serveur à l'ouverture : une progression locale non encore
  poussée (`pendingSync`) l'emporte ; sinon la ligne locale est déjà synchronisée
  et c'est la position **serveur** (potentiellement avancée par le web) qui est
  adoptée, puis recopiée en local. La position EPUB reste un **CFI**
  (indépendant de la taille de police), donc le changement de police sur le web
  n'affecte pas la reprise sur mobile.

## [1.3.0] - 2026-08-17

### Fixed
- **Connexion impossible (403 Forbidden) depuis l'activation du PIN serveur.**
  Le client avait été buildé avant que `BOOKHAVEN_PIN` ne soit activé : il
  postait `/api/auth/login` **sans champ `pin`**, que le serveur rejette en 403.
- **Verrouillage prématuré du client web sur la même IP.** À chaque lancement,
  l'app rejouait silencieusement `/api/auth/login` sans PIN ; ces échecs
  automatiques se cumulaient, sur l'IP VPN partagée du téléphone, avec les
  essais humains du navigateur et déclenchaient le lockout brute-force
  (5 échecs / IP) en quelques essais. L'app ne tente plus de reconnexion
  silencieuse quand un PIN est requis mais qu'aucun PIN valide n'est mémorisé.

### Added
- Champ **PIN** sur l'écran de connexion, affiché uniquement si le serveur le
  requiert (`GET /api/auth/pin-required`). Le PIN est envoyé à
  `/api/auth/login` et `/api/auth/users`, et mémorisé après un login réussi pour
  les reconnexions silencieuses suivantes. Un PIN refusé (403) est oublié et
  signalé clairement (« Incorrect PIN »).

## [1.0.0] - 2026-07-14

### Added
- Initial release of the native Android client for BookHaven
- Server configuration screen (server URL stored in SharedPreferences)
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
