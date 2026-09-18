# Refonte BookHaven P0 — progression (Opus 4.8)

Spec : `docs/bookhaven-redesign-validated.md` §9. Périmètre = **P0 uniquement**.
Un commit par lot. Tests sur instance démo isolée / DB de test. NE PUSH PAS.

| Lot | Statut | Horodatage | Notes |
|---|---|---|---|
| P0-A Verrou SQLite (Flask + Android) | **done** | 2026-09-18 | commit dd79050 ; pytest 3/3 |
| P0-B Crash lecteur OOM (Android) | **done** | 2026-09-18 | build APK OK (12:17) ; à valider émulateur |
| P0-C Pagination + tris + facettes (Flask + Android) | **done** | 2026-09-18 | compileDebugKotlin OK ; SQL smoke-test OK |
| P0-D Refonte visible (Android) | **done** | 2026-09-18 | build APK OK (15:49) ; à valider émulateur |

## PROCHAINE ACTION
**P0 terminé** (P0-A/B/C/D done). Reste à faire manuellement :
- **Valider sur émulateur/appareil** : ouverture manhua 729 Mo sans OOM (P0-B), scroll pagination
  (P0-C), écran Accueil + tris + raccourcis Catégories (P0-D).
- **Redémarrage Flask déjà requis pour P0-A/P0-C** (changements `.py`, `debug=False`).
- P1 et lots écartés : NON réalisés (hors périmètre).

## Journal
- 2026-09-18 — Début. Fichier de progression créé.
- 2026-09-18 — **P0-A done.** Flask : `database.writing()` (database.py) + routes d'écriture
  refactorées + 404 sur progress + media_worker commit/UPDATE. Android : `SyncRepository` purge 404.
  Test `tests/test_db_writing_lock.py` = 3/3. Versions 2.7.1 / Android 56 (1.5.2). Commit → voir git.
- 2026-09-18 — **P0-B done.** Lecteur comic page-par-page (online API + offline ZipFile), cache LRU
  300 Mo, SubsamplingScaleImageView. Android 1.6.0. Commit c4b9e62.
- 2026-09-18 — **P0-C done.** Flask tris `added_desc`/`last_read_desc` (recent conservé) ; Android
  pagination infinie + facettes `/api/filters` + tri + recherche anti-rebond + snapshot cumulatif.
  Web 2.7.2 / Android 1.6.1. Commit 51855d9.
- 2026-09-18 — **P0-D done.** Nav basse Accueil/Bibliothèque/Téléchargements (Réglages en toolbar via
  `main_toolbar_menu`) ; `HomeFragment` + `HomeViewModel` + `CoverRailAdapter` (Reprendre + rails En
  cours / Récemment ajoutés + raccourcis Catégories) ; rail Continue Reading retiré de la Bibliothèque.
  Android 1.7.0 (versionCode 59). APK buildé (assembleDebug OK). Aucun changement Flask.
