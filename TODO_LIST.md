# BookHaven — TODO

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
