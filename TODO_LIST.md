# BookHaven — TODO

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
