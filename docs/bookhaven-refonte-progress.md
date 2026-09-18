# Refonte BookHaven P0 — progression (Opus 4.8)

Spec : `docs/bookhaven-redesign-validated.md` §9. Périmètre = **P0 uniquement**.
Un commit par lot. Tests sur instance démo isolée / DB de test. NE PUSH PAS.

| Lot | Statut | Horodatage | Notes |
|---|---|---|---|
| P0-A Verrou SQLite (Flask + Android) | **done** | 2026-09-18 | commit ci-dessous ; pytest 3/3 ; Android compile à valider au build P0-B |
| P0-B Crash lecteur OOM (Android) | in-progress | 2026-09-18 | — |
| P0-C Pagination + tris + facettes (Flask + Android) | pending | — | — |
| P0-D Refonte visible (Android) | pending | — | — |

## PROCHAINE ACTION
P0-B : `ApiService` + `getComicPages`/`comic-page/{n}` ; `ComicReaderFragment` lecteur par
références (cache disque LRU en ligne, `ZipFile` à la demande offline) ; `ComicPageAdapter` via
`SubsamplingScaleImageView` (dépendance Gradle) ; supprimer `List<ByteArray>` + `decodeByteArray`.
Puis `./gradlew assembleDebug` (valide aussi la compil P0-A Android). Redémarrage Flask requis pour P0-A.

## Journal
- 2026-09-18 — Début. Fichier de progression créé.
- 2026-09-18 — **P0-A done.** Flask : `database.writing()` (database.py) + routes d'écriture
  refactorées + 404 sur progress + media_worker commit/UPDATE. Android : `SyncRepository` purge 404.
  Test `tests/test_db_writing_lock.py` = 3/3. Versions 2.7.1 / Android 56 (1.5.2). Commit → voir git.
