# Refonte BookHaven P0 — progression (Opus 4.8)

Spec : `docs/bookhaven-redesign-validated.md` §9. Périmètre = **P0 uniquement**.
Un commit par lot. Tests sur instance démo isolée / DB de test. NE PUSH PAS.

| Lot | Statut | Horodatage | Notes |
|---|---|---|---|
| P0-A Verrou SQLite (Flask + Android) | **done** | 2026-09-18 | commit dd79050 ; pytest 3/3 |
| P0-B Crash lecteur OOM (Android) | **done** | 2026-09-18 | build APK OK (12:17) ; à valider émulateur |
| P0-C Pagination + tris + facettes (Flask + Android) | in-progress | 2026-09-18 | — |
| P0-D Refonte visible (Android) | pending | — | — |

## PROCHAINE ACTION
P0-C : **Flask** — ajouter tris `added_desc` (`added_at DESC, id DESC`) et `last_read_desc`
(jointure reading_progress du profil) dans `sort_map` de `/api/books`, SANS casser `recent`.
**Android** — exposer `page`/`perPage` dans `ApiService`+`BookRepository`, pagination infinie dans
`LibraryViewModel`/`LibraryFragment` (charger en fin de liste, afficher total), facettes via
`/api/filters`, sélecteur de tri (défaut Récemment ajoutés), recherche debounce 300 ms + annulation,
snapshot hors-ligne cumulatif. Redémarrage Flask requis (P0-C touche le serveur).

## Journal
- 2026-09-18 — Début. Fichier de progression créé.
- 2026-09-18 — **P0-A done.** Flask : `database.writing()` (database.py) + routes d'écriture
  refactorées + 404 sur progress + media_worker commit/UPDATE. Android : `SyncRepository` purge 404.
  Test `tests/test_db_writing_lock.py` = 3/3. Versions 2.7.1 / Android 56 (1.5.2). Commit → voir git.
