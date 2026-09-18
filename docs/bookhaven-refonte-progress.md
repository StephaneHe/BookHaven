# Refonte BookHaven P0 — progression (Opus 4.8)

Spec : `docs/bookhaven-redesign-validated.md` §9. Périmètre = **P0 uniquement**.
Un commit par lot. Tests sur instance démo isolée / DB de test. NE PUSH PAS.

| Lot | Statut | Horodatage | Notes |
|---|---|---|---|
| P0-A Verrou SQLite (Flask + Android) | **done** | 2026-09-18 | commit dd79050 ; pytest 3/3 |
| P0-B Crash lecteur OOM (Android) | **done** | 2026-09-18 | build APK OK (12:17) ; à valider émulateur |
| P0-C Pagination + tris + facettes (Flask + Android) | **done** | 2026-09-18 | compileDebugKotlin OK ; SQL smoke-test OK |
| P0-D Refonte visible (Android) | in-progress | 2026-09-18 | — |

## PROCHAINE ACTION
P0-D : **Android** — nav basse Accueil/Bibliothèque/Téléchargements (Réglages en barre/toolbar) ;
créer `HomeFragment` (Reprendre = dernière lecture via `/api/continue-reading` premier item ;
rail « En cours » ; rail « Récemment ajoutés » via `/api/books?sort=added_desc` ; raccourcis
Catégories via `/api/filters`). Renommer OfflineFragment → « Téléchargements ». Retirer le rail
Continue Reading de LibraryFragment (déplacé vers Accueil). Puis `./gradlew assembleDebug` (APK final).
Redémarrage Flask requis pour P0-A/P0-C.

## Journal
- 2026-09-18 — Début. Fichier de progression créé.
- 2026-09-18 — **P0-A done.** Flask : `database.writing()` (database.py) + routes d'écriture
  refactorées + 404 sur progress + media_worker commit/UPDATE. Android : `SyncRepository` purge 404.
  Test `tests/test_db_writing_lock.py` = 3/3. Versions 2.7.1 / Android 56 (1.5.2). Commit → voir git.
