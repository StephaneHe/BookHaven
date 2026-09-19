# Reprise des images échouées/404 transitoires — vérification (2026-09-19)

Objectif : récupérer les strips qui auraient pu échouer sur un **404/erreur réseau
transitoire** (site instable) pendant les passes précédentes, et distinguer une
**absence réelle** (confirmée par la liste autoritative) d'un **échec transitoire**.

## Méthode
`scripts/fetch_manhua_strips.py` durci pour cette reprise :
- **RETRIES 5 → 8** + backoff plus long (1,5 s × tentative).
- **`retry_404=True` pour les images de la liste autoritative** : puisque l'endpoint
  `/auth/chapter-content` garantit qu'une image existe, un 404 dessus est presque
  toujours un hoquet transitoire du CDN → on ré-essaie au lieu de conclure « absente ».
- Idempotent (skip des fichiers déjà valides). Referer `roliascan.org`, UA navigateur.

## Résultat — RIEN à récupérer, AUCUNE absence réelle
Passe complète sur les **217 chapitres** (lots 1-108 et 109-216 + 172.5) :
- **planches récupérées au retry = 0** (tout était déjà présent/valide),
- **still-missing = 0**, **0 anomalie**, **0 échec d'endpoint** (les 217 listes
  autoritatives ont été obtenues).

Census autoritatif (endpoint vs local) :
- **Aucune absence réelle de contenu** : chaque image listée (hors pubs) est présente.
- Les 38 chapitres où « local ≠ liste » correspondent aux **emplacements de pub**
  728×90 (`page_012/013.jpg`, etc.) que l'endpoint liste mais qu'on **exclut
  volontairement** — ce ne sont pas des planches manquantes.
- **Chapitre réellement court confirmé par la liste** : **172.5** (1 image, légitime).
- Les 17 chapitres jadis classés « courts » (bug pas-de-15) sont tous confirmés
  **multi-strips** (3-4 planches) par la liste autoritative — déjà corrigés au tour
  précédent (recheck2, +57 strips).

## Conséquences
- **CBZ non régénéré** (0 planche ajoutée) ; **`content_version` inchangé** (correct).
- Le durcissement retries/`retry_404` est conservé : futures reprises plus robustes
  aux 404 transitoires du site.
- Manifeste : `data/manhua/sir-dont-show-off/_strips_manifest.json`.
