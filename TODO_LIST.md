# BookHaven — TODO

## 2026-09-18 — Skill roliascan réutilisable (web 2.7.5)

- [x] Skill `.claude/skills/roliascan-manhua/SKILL.md` + `scripts/download_roliascan.py`
      (discover→download→combine→import, généralise fetch_manhua_strips/combine/adfilter,
      mapping via og:image, strips pas-de-15→404 réel, `--plan`, non destructif, rapport
      d'anomalies) + `docs/roliascan-download-rules.md`. Testé mapping+énumération sur la
      série connue (216 ch, 0 anomalie).

## 2026-09-18 — Réparation manhua « Sir, Don't Show Off » (web 2.7.4)

- [x] **Strips manquants récupérés.** Correction du diagnostic 2.7.3 (« tronqué à la
      source » = FAUX). Chaque chapitre stitched = plusieurs strips `page_001/016/031/046…`
      (pas de 15) ; l'ancien fetcher ne gardait que le strip 1. `fetch_manhua_strips.py` :
      **+294 strips, 109 chapitres réparés**, 17 genuinement courts, **0 image corrompue**
      (1265 img). CBZ **969→1263 pages** régénéré, DB à jour, backups gardés. ch50 complet
      (4 strips) enchaîne ch51. Détail : `docs/manhua-integrity-report-2026-09-18.md`,
      progression : `docs/manhua-repair-progress.md`.
- [x] Nettoyage pub (2.7.3) : 74 GIF 728×90 identiques retirés des données (déjà exclus du CBZ).

## 2026-09-18 — Refonte P0 (Opus 4.8) — voir docs/bookhaven-refonte-progress.md

- [x] **P0-A Verrou SQLite** (Flask 2.7.1 + Android 1.5.2/56) : `database.writing()`
      (rollback+close garantis) sur routes d'écriture ; `api_set_progress`/
      `api_get_progress` → 404 si livre absent ; `media_worker` commit par UPDATE ;
      `SyncRepository` purge sur 404. Test `tests/test_db_writing_lock.py` (3 verts).
      **Redémarrage Flask requis.**
- [x] **P0-B Crash lecteur OOM** (Android 1.6.0/57) : lecteur page par page (API comic-pages/comic-page en ligne, ZipFile offline, cache LRU 300 Mo) + SubsamplingScaleImageView (tuilage). Build APK OK. À valider sur émulateur/device (ouverture manhua 729 Mo sans OOM).
- [x] **P0-C Pagination + tris + facettes** (Flask 2.7.2 + Android 1.6.1/58) :
      `/api/books` tris `added_desc`/`last_read_desc` ; Android pagination infinie
      + facettes `/api/filters` + sélecteur de tri + recherche debounce 300 ms +
      snapshot hors-ligne cumulatif. compileDebugKotlin OK. **Redémarrage Flask requis.**
- [x] **P0-D Refonte visible** (Android 1.7.0/59) : nav basse Accueil/Bibliothèque/
      Téléchargements (Réglages en toolbar) ; écran Accueil (Reprendre + rails En cours /
      Récemment ajoutés + raccourcis Catégories, endpoints existants) ; rail Continue Reading
      retiré de la Bibliothèque. Build APK OK. À valider sur émulateur/device. Pas de changement Flask.

**P0 terminé (A/B/C/D).** P1 et lots écartés = hors périmètre, non réalisés.

## 2026-09-18 — Manhua en défilement vertical continu (webtoon)

- [x] **Option retenue = 1 (chapitres + scroll continu)** implémentée SUR le livre
      unique : les 217 chapitres sont dérivés des noms de planches (`NNNNN_NNN`,
      prefix/10 = n° chapitre, décimaux inclus) → **pas de ré-import DB**, pas de
      churn catalogue, scroll inter-chapitres possible. (Données brutes par
      chapitre conservées dans `data/manhua/` en fallback si besoin d'un vrai
      re-split.)
- [x] Lecteur : mode **continu** auto-détecté (planche haute, h/l>2) → planches
      d'un chapitre empilées, **scroll vertical**, **plus de page-flip**. Nav
      chapitres : dropdown 217 + ‹ / › + « Chapitre suivant » en bas.
      Chargement par chapitre (perfs).
- [x] Comics normaux **restent paginés** (vérifié : 38983 page-flip 1→2 OK).
- [x] Zoom conservé en continu ; indicateur planche suit le scroll ; « aller à »
      scrolle (pas de page-flip). Progression restaurée (rouvre à la planche lue).
- [x] Pubs (pages 728×90) déjà absentes. Web v2.7.0, template auto-reload → pas
      de redémarrage Flask.

### Suivi possible
- [ ] Les **filigranes du ripper baked-in** (« NovelMic.Com », LIKEMANGA…) sont
      dans les planches de contenu → non supprimables sans recadrage (hors scope).
- [ ] Optionnel : auto-avance en fin de chapitre (actuellement bouton explicite).


## 2026-09-18 — Zoom lecteur web + mémorisation par livre

- [x] Contrôles **+ / − / reset** dans la barre du lecteur comic + raccourcis
      `+`/`-`/`0` et **Ctrl+molette**. Agit sur la largeur des planches
      (`--comic-zoom`). Défaut 100% = largeur d'ajustement entre les boutons.
- [x] Zoom in → défilement **horizontal** ; boutons gauche/droite **visibles +
      cliquables** même zoomé (vérifié : nav topmost, clic 1/969→2/969) ;
      défilement vertical conservé.
- [x] **Mémorisé par livre** : localStorage `bookhaven.zoom.comic.<id>` (préférence
      d'affichage par appareil, pas de changement de schéma DB, fallback try/catch).
      Vérifié headless : livre A restauré à 130% à la réouverture, livre B
      indépendant à 100%, retour A toujours 130%.
- [x] Web v2.6.0. Template auto-reload → **pas de redémarrage Flask** requis.


## 2026-09-18 — Lecteur web : image entre les boutons (correctif fit-width)

- [x] Le fit-width plein écran recouvrait les boutons prev/next → l'image remplit
      désormais la **zone centrale entre les boutons** (gutters 64 px desktop /
      44 px mobile). Boutons rendus **visibles + cliquables** (fond translucide +
      chevrons ‹ ›). Scroll vertical conservé, navigation avant/arrière OK.
- [x] Vérifié headless (1000px) : image 64→936 px, boutons dans les gutters, pas
      de recouvrement, clic Next 1/969→2/969. Web v2.5.3.
- [x] Template auto-reload → **pas de redémarrage Flask requis** pour le correctif
      (redémarrage seulement pour afficher le nouveau n° de version).


## 2026-09-18 — Quickfix manhua (pubs + fit-width)

- [x] **Pubs retirées** : détection (`scripts/manhua_adfilter.py`) — pub 728×90
      récurrente (74×) + bandeaux filigrane larges/courts. CBZ reconstruit
      **1045 → 969 pages** (76 retirées), backup `Sir, Don't Show Off.cbz.orig`.
- [x] **Pipeline filtré pour l'avenir** : `combine_` et `pack_manhua_cbz.py`
      excluent les pubs à la construction.
- [x] **Lecteur web : défaut fit-width** (100% largeur, scroll vertical) au lieu
      de fit-height. Template auto-reload.
- [x] Version web 2.5.2, redémarrage Flask pour la version (les 2 fixes sont
      actifs sans redémarrage : template + CBZ relus à chaud).


## 2026-09-18 — Import manhua « Sir, Don't Show Off » (offline)

- [x] Site roliascan.com (thème mangapeak). Liste complète des chapitres extraite
      du sélecteur du reader : **217 chapitres** (1–216 + décimal **172.5**).
- [x] Images sur CDN déterministe `roliascan.org/storage/chapters/manhwa_319969_<ch>/`.
      **Deux formats par chapitre** : multi-pages `page_NNN.jpg` OU strip unique
      `page_001_stitched.webp` → détection auto par chapitre (fallback JSON-LD).
- [x] Téléchargé **217/217 chapitres, 1045 images, 735 Mo, 0 échec** →
      `data/manhua/sir-dont-show-off/<NNN>/` (resumable, poli, hors dépôt).
- [x] Packagé en **217 CBZ** dans `H:\Books\Comics\Sir, Don't Show Off\`.
- [x] Importé en base (surgical, 217 lignes, `series_index` exact 1..216 + 172.5,
      couvertures) sans rescan global. Backup DB pré-import créé.
- [x] Vérifié LISIBLE sur le web live (8097) : série ordonnée (…172, 172.5, 173…),
      chapitres multi-pages ET strips webp s'affichent dans l'ordre.
- [x] Fix MIME WebP pour `/comic-page` (bump 2.5.1) — **redémarrer Flask** pour l'appliquer.

- [x] **Lecture en un seul livre continu** (demande utilisateur) : 217 chapitres
      combinés en **1 CBZ / 1045 pages** (`combine_manhua_cbz.py` +
      `finalize_manhua_single.py`), enregistré comme un seul comic. Vérifié sur le
      web live : reader « Sir, Don't Show Off » 1/1045, défilement continu.
- [x] Serveur Flask redémarré → correctif MIME WebP appliqué (page webp servie
      `image/webp`), base débloquée.

### Suivi possible (non bloquant)
- [ ] **Bug latent à corriger** : des handlers Flask ne ferment pas toujours la
      connexion SQLite sur le chemin d'erreur → une transaction d'écriture peut
      rester ouverte et **verrouiller toute la base** (constaté : `api_set_progress`
      « database is locked » en boucle, corrigé par un redémarrage). Envelopper
      l'accès DB dans un `try/finally: conn.close()` (ou un context manager).
- [ ] Vérifier le rendu d'un strip webp très haut (~14000 px) sur l'app Android
      (Coil peut sous-échantillonner les très grandes images). Web = OK.
- [ ] Si de nouveaux chapitres sortent : `fetch_manhua.py <ch>` puis
      `combine_manhua_cbz.py` + `finalize_manhua_single.py` (idempotents).



## 2026-09-15 — Icônes/couvertures qui disparaissent (app Android)

- [x] Diagnostiquer l'interface concernée : **app Android** (l'UI web sert les
      couvertures correctement depuis le cache disque `cache/covers/`).
- [x] Cause racine : Coil chargeait les couvertures avec son client HTTP par
      défaut **sans cookie de session** → `/api/books/<id>/cover` (`@login_required`)
      renvoyait **401** → placeholder gris. Aggravé par un `MemoryCookieJar`
      **mémoire seulement**, perdu au restore du processus.
      Refs : `bookhaven.py:1323` (login_required cover), `BookAdapter.kt:28`,
      `ApiClient.kt` (cookie jar), `AppModule.kt`.
- [x] Fix : `PersistentCookieJar` (SharedPreferences) + `ImageLoader` Coil
      authentifié avec cache disque persistant (`BookHavenApp.newImageLoader()`).
- [x] Vérifié sur émulateur `Pixel_3a_API_33_x86_64` contre l'instance démo
      isolée (port 8099, livres domaine public) : couvertures chargées + toujours
      visibles après `am kill` / redémarrage du processus.
- [x] Android `versionCode` 54→55, `versionName` 1.5.0→1.5.1, CHANGELOG daté.

### Suivi possible (non bloquant)
- [ ] Optionnel : ajouter `coil-svg` pour rendre le placeholder « No Cover » SVG
      du serveur nativement (aujourd'hui Coil ne décode pas le SVG et retombe sur
      `ic_book_placeholder`, ce qui est acceptable).
- [ ] Optionnel : bouton « vider le cache images » dans les Réglages Android.
