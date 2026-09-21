# Changelog — BookHaven Android

## [1.9.3] - 2026-09-21

### Changed
- **Préchargement manhua « un chapitre en avance ».** Avant : seulement ~3 planches
  suivantes + les 2 premières du chapitre suivant. Maintenant : une **boucle de
  préchargement continue** réchauffe le **cache disque LRU** (fichiers seulement —
  **aucun bitmap décodé**, donc pas d'OOM) avec le **reste du chapitre courant +
  le chapitre suivant ENTIER**, en avance de la position de lecture. Séquentielle
  (pas de tempête de requêtes), saute ce qui est déjà en cache, recalcule depuis la
  dernière position à chaque passe (reste toujours devant). Cache LRU **300 → 500 Mo**
  (garde ~1 chapitre d'avance + le lu récent, borné ; évacue le loin-derrière). Le
  décodage anticipé (PrefetchLayoutManager ~2 écrans) est conservé. `ComicReaderFragment`
  + `ComicPageSource`.

### Changed
- versionCode 64, versionName 1.9.3.

## [1.9.2] - 2026-09-20

### Fixed
- **Préchargement RÉEL des planches dans le lecteur webtoon.** Le prefetch du lot
  précédent ne réchauffait que les *fichiers* (sans effet en hors-ligne et sans
  anticiper le décodage) → aucun gain perçu. Ajout d'un `PrefetchLayoutManager`
  (LinearLayoutManager avec `calculateExtraLayoutSpace` = ~2 écrans sous la fenêtre)
  : RecyclerView **lie et décode (SubsamplingScaleImageView) les planches suivantes
  ~2 écrans en avance** → la planche suivante est déjà rendue quand on l'atteint.
  Bornée (~1 grande planche supplémentaire vive à la fois) + `itemViewCacheSize=4` +
  prefetch fichiers conservé → **pas d'OOM** (robustesse P0-B). `ComicReaderFragment`
  (PrefetchLayoutManager) + `ContinuousComicAdapter` (warm fichiers).

### Added
- **Version affichée sur l'écran d'accueil** (libellé discret en bas : « BookHaven
  vX.Y.Z (code) », `BuildConfig.VERSION_NAME/CODE`) en plus de Réglages (qui
  l'affichait déjà en bas).

### Changed
- versionCode 63, versionName 1.9.2.

## [1.9.1] - 2026-09-19

### Changed
- **Préchargement des planches dans le lecteur webtoon continu.** À chaque planche
  affichée, les **3 planches suivantes** sont pré-téléchargées (fichiers seulement,
  dans le cache LRU — **aucun bitmap décodé**, donc pas d'OOM) ; et en approchant la
  fin d'un chapitre, les **2 premières planches du chapitre suivant** sont préchargées
  → scroll et transition de chapitre fluides. Fenêtre bornée + dédup (scroll rapide
  n'empile pas de travail). Robustesse P0-B conservée. versionCode 62, versionName 1.9.1.

## [1.9.0] - 2026-09-19

### Changed
- **Lecteur manhua/webtoon identique au web mobile (P1-A).** Le manhua s'ouvre
  désormais en **défilement vertical continu** avec les planches en **PLEINE
  LARGEUR** (largeur = écran × zoom, hauteur = largeur × ratio de la planche),
  exactement comme le lecteur web (`#comic-scroll img { width: var(--comic-zoom);
  height: auto }`). Fini le **fit-height** qui rendait les longues planches
  minuscules. Détection auto du type webtoon (1ʳᵉ planche h/l > 2, même règle que
  le web) ; les comics « normaux » gardent le mode paginé (ViewPager2).
  - **Chapitres dérivés des noms de planches** (préfixe `NNNNN_NNN`, préfixe/10 =
    numéro, 172.5 inclus), chargés **un chapitre à la fois**, avec bouton
    « Chapitre suivant ›», boutons ‹/› et sélecteur de chapitre (liste).
  - **Position = index global de planche** (comme le web via `current_location`)
    → reprise web ↔ Android compatible ; suivi au scroll (planche visible en haut).
  - **Zoom mémorisé par livre** (SharedPreferences `bookhaven.zoom.comic.<id>`,
    défaut 100 % = pleine largeur, 40–400 %, pas 15) : pincer + boutons −/label/+
    (tap label = reset). Restauré à la réouverture du même livre ; chaque livre a
    son propre zoom.

### Added
- `android:largeHeap="true"` — marge mémoire pour les longues planches webtoon.

### Notes
- Robustesse P0-B conservée : rendu par **SubsamplingScaleImageView** (tuilage
  BitmapRegionDecoder), planches à la demande (cache LRU 300 Mo), recyclage
  hors-écran, un seul chapitre monté à la fois → pas d'OOM sur le manhua 729 Mo.
- versionCode 61, versionName 1.9.0. Aucun changement serveur (endpoints existants).

## [1.8.0] - 2026-09-19

### Fixed
- **Le contenu comic/manhua mis à jour côté serveur n'était pas repris (cache
  périmé).** L'app réutilisait le CBZ téléchargé et le cache de pages du lecteur
  (P0-B) sans détecter que le contenu serveur avait changé (ex. « Sir, Don't Show
  Off » réparé de 969 à 1263 pages). Désormais :
  - Le cache disque de pages est **clé par empreinte de contenu**
    (`b<id>_v<content_version>_p<n>.img`) ; à l'ouverture, les fichiers d'une
    **version différente sont purgés** → re-fetch du contenu à jour. Robustesse
    P0-B conservée (par références, pas d'OOM).
  - **En ligne** : le lecteur lit `content_version` depuis `/comic-pages` et
    l'utilise comme clé (une seule requête donne pages + version).
  - **Hors-ligne** : la copie téléchargée mémorise sa `content_version` ; à
    l'ouverture, si le serveur a une version différente, l'app **propose « Mettre
    à jour »** (re-télécharge) au lieu d'afficher silencieusement du périmé
    (migration Room 4→5 : colonne `contentVersion`).

### Changed
- versionCode 60, versionName 1.8.0. Nécessite le serveur **≥ 2.7.6** (champ
  `content_version`).

## [1.7.0] - 2026-09-18

### Changed
- **Refonte de la navigation visible (refonte P0-D).** Nouvelle **nav basse** à
  trois onglets : **Accueil**, **Bibliothèque**, **Téléchargements** ; les
  **Réglages** passent dans la barre du haut (menu toolbar). Nouvel écran
  **Accueil** qui agrège les endpoints existants (aucun nouvel endpoint serveur) :
  grande carte **« Reprendre »** (dernière lecture via `/api/continue-reading`),
  rail **« En cours »**, rail **« Récemment ajoutés »** (`/api/books?sort=added_desc`)
  et **raccourcis Catégories** (`/api/filters`) qui ouvrent la Bibliothèque
  pré-filtrée. Le rail « Continue Reading » est retiré de la Bibliothèque
  (déplacé vers l'Accueil), qui se concentre désormais sur la grille paginée,
  les filtres catégorie/genre et le tri.

## [1.6.1] - 2026-09-18

### Changed
- **Bibliothèque : pagination infinie + tris + facettes serveur (refonte P0-C).**
  L'app ne se limite plus aux 50 premiers livres : elle pagine (`page`/`perPage`)
  et charge la suite en fin de liste sur ~9 500 livres. Les filtres (catégories,
  genres **distincts**, formats) viennent de `/api/filters` (facettes complètes,
  plus déduites des 50 affichés). Sélecteur de **tri** (Récemment ajoutés par
  défaut, Récemment lus, Titre, Auteur). Recherche **anti-rebond 300 ms** avec
  annulation de la requête précédente. Snapshot hors-ligne **cumulatif**.

## [1.6.0] - 2026-09-18

### Fixed
- **Crash mémoire (OOM) à l'ouverture des gros comics/manhua (refonte P0-B).**
  Le lecteur chargeait TOUTES les images de l'archive en RAM (~695 Mio pour le
  manhua fusionné) puis décodait des bitmaps pleine taille sur le thread UI.
  Réécrit en **accès page par page** : en ligne via `GET /api/books/<id>/comic-pages`
  + `/comic-page/<n>`, hors-ligne via `ZipFile` (accès direct à l'entrée demandée,
  plus de `ZipInputStream` intégral), avec **cache disque LRU borné (300 Mo)**.
  Affichage via **SubsamplingScaleImageView** (tuilage + sous-échantillonnage via
  `BitmapRegionDecoder`, gère les longues planches ~15 000 px) ; images recyclées
  hors écran. Suppression de `List<ByteArray>` et `BitmapFactory.decodeByteArray`.
  (Scroll vertical webtoon = P1 ; on garde le ViewPager2 paginé pour l'instant.)

## [1.5.2] - 2026-09-18

### Fixed
- **Sync de progression (refonte P0-A).** `SyncRepository` purge désormais la
  progression locale quand le serveur répond **404** (livre supprimé) au lieu de
  la repousser sans fin — c'était le déclencheur du verrou SQLite côté serveur.
  `pendingSync` n'est remis à `false` que si l'envoi a réellement réussi.

## [1.5.1] - 2026-09-15

### Fixed
- **Les couvertures de livres disparaissaient au bout d'un moment** (placeholder
  gris à la place de la vignette). Deux causes cumulées :
  - Coil (chargement des images) utilisait son client HTTP par défaut, **sans le
    cookie de session**. Or `/api/books/<id>/cover` exige l'authentification
    (`@login_required`) → **401 → placeholder**. `BookHavenApp` fournit désormais
    un `ImageLoader` Coil basé sur le **client OkHttp authentifié** (partage du
    `cookieJar`) + un **cache disque persistant** (`cover_cache`, 64 Mo) : les
    couvertures se chargent et **restent visibles** entre les redémarrages, avec
    rechargement propre en cas d'éviction.
  - Le cookie de session n'existait qu'en mémoire (`MemoryCookieJar`) → **perdu à
    la mort du processus**, forçant chaque démarrage à froid à refaire des
    requêtes non authentifiées jusqu'au ré-login silencieux. Remplacé par
    `PersistentCookieJar` (persistance dans les `SharedPreferences`), donc la
    session survit au restore du processus.

## [1.5.0] - 2026-08-28

### Security
- Remplacement du `android:usesCleartextTraffic="true"` global par un
  `network_security_config.xml` dédié et documenté. Le cleartext reste permis
  pour joindre le serveur auto-hébergé (adresse privée/VPN en HTTP), mais la
  permission est désormais explicite et centralisée. `android:allowBackup`
  passe à `false` (la base Room locale et les préférences ne partent plus dans
  les sauvegardes Android).

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
