# Manhua repair progress — « Sir, Don't Show Off »

Objectif : compléter les strips manquants (numérotés `page_001/016/031/046…`, **pas de 15**)
sur le CDN autoritatif `roliascan.org/storage/chapters/manhwa_319969_<N>/`. Mapping
chapitre affiché N → dossier `_N` (aucun décalage, confirmé via og:image).

Outil : `scripts/fetch_manhua_strips.py` (resumable, retries/backoff, poli).

## État initial (avant cette reprise)
- 217 chapitres : 91 paged (jpg, complets), 126 stitched.
- Stitched multi-strip déjà complétés : 14.
- **Stitched single-strip à compléter : 112** (chap. 52–174, cf. liste).

## Journal
- 2026-09-18 — Reprise après arrêt à 40/217. Traitement par lots (foreground, resumable).
- 2026-09-18 — **TERMINÉ (217/217).** Lots 41-80, 81-120, 121-160, 161-200+172.5, 201-216 +
  passe finale complète. **+294 strips récupérés**, 109 chapitres stitched réparés, 17 genuinement
  à 1 strip (≤15 pages, 404 réel vérifié). Intégrité : 1265 images, **0 corrompue**.
  CBZ régénéré (969→**1263 pages**, 1362,9 Mo), DB id 39572 (page_count/file_size) mise à jour.
  ch50 = 4 strips complets, enchaîne ch51. Web 2.7.4. Aucune vraie absence CDN.
