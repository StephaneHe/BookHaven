---
name: roliascan-manhua
description: Download any manhua/manhwa from roliascan.com cleanly and integrate it into BookHaven for continuous vertical reading. Use when the user wants to add a roliascan series, or fix/complete/repair an already-downloaded one (missing pages, truncated chapters, ads). Covers CDN enumeration (the authoritative roliascan.org/storage), chapter to folder mapping, the step-15 stitched-strip numbering, ad filtering, integrity checks, and BookHaven registration.
---

# Télécharger un manhua depuis roliascan → BookHaven

Procédure validée en réparant « Sir, Don't Show Off » (voir
`docs/manhua-integrity-report-2026-09-18.md`). Le script fait tout le travail ;
cette skill explique **quoi lancer, comment vérifier, et les pièges à surveiller**.

## Script

`scripts/download_roliascan.py` (généralise `fetch_manhua_strips.py` +
`combine_manhua_cbz.py` + `manhua_adfilter.py` + registration DB). Étapes :
**discover → download → combine (CBZ unique) → import (1 livre)**.

```bash
# 1) TOUJOURS commencer par un PLAN (aucun téléchargement) : découverte des
#    chapitres, vérification du mapping chapitre->dossier, énumération des strips.
python scripts/download_roliascan.py https://roliascan.com/series/<slug>/ --plan

# 2) Télécharger + filtrer pubs + vérifier intégrité + CBZ + enregistrer le livre
python scripts/download_roliascan.py https://roliascan.com/series/<slug>/

# Réparer / compléter seulement certains chapitres (numéros de dossier CDN) :
python scripts/download_roliascan.py <slug> --chapters 49 50 51

# Étapes sélectives : --no-download  --no-combine  --no-import  --title "Titre"
```

Rapport machine écrit dans `data/manhua/<slug>/_download_report.json`
(chapitres, mode de mapping, **anomalies à revoir**).

Prérequis : Python système + Pillow ; `.env` avec `BOOKHAVEN_SECRET_KEY` et
`BOOKS_ROOT` (l'étape `import` charge `config`). Site lent/instable -> patience.

## Comment ça marche (règles centrales — voir `docs/roliascan-download-rules.md`)

1. **CDN autoritatif** : `https://roliascan.org/storage/chapters/manhwa_<MANGA_ID>_<CHAP>/page_<NNN>[_stitched].webp`.
   **NE PAS** se fier à la page HTML `.com` du chapitre (elle sous-liste les
   images : og:image ne montre souvent que la 1re planche).
2. **En-tête obligatoire** : `Referer: https://roliascan.org/` + User-Agent navigateur (sinon blocage).
3. **Strips « stitched » numérotés par PAS DE 15** : `page_001`, `page_016`,
   `page_031`, `page_046`, … (chaque strip = 15 pages sources). Énumérer jusqu'au
   **404 REEL** (retries pour distinguer une erreur transitoire de la fin). Les
   chapitres courts/anciens peuvent être en **pages contiguës** (`page_001.jpg`, `page_002.jpg`…).
4. **Mapping chapitre->dossier** : découvert en scrappant la page série
   (`/series/<slug>/` contient tous les slugs `ch<num>-<postid>`, le `manga_id`
   via `data-manga-id`, le read-slug via les liens `/read/`). Le dossier CDN est
   **confirmé par l'og:image** d'un échantillon de chapitres. Sur « Sir, Don't
   Show Off » : **chapitre affiché N -> dossier `_N`** (aucun décalage). Le script
   vérifie et, en cas de décalage, résout **chaque** chapitre via son og:image.
5. **Filtrage pubs** : bannière **728x90** (GIF pub sous fausse extension `.jpg`,
   md5 `ed6d7bf6aa`, « BEST WEBSITE… », filigranes LIKEMANGA/WEBNOVEL). Détectée
   par taille/hash/format (`manhua_adfilter.py`), exclue du CBZ.
6. **Intégrité** : chaque image doit **décoder** (PIL) et avoir un **marqueur de
   fin** valide (JPEG `FFD9`, PNG `IEND`, WebP RIFF). Les tronquées sont
   re-téléchargées / signalées.
7. **Intégration BookHaven** : un **CBZ unique** (toutes les planches, noms
   triables `NNNNN_NNN` où `NNNNN = chapitre x 10`, décimaux préservés) -> lecture
   **verticale continue** (les chapitres sont dérivés des préfixes de planches).
   Enregistré comme **un seul livre** (INSERT idempotent). **NE JAMAIS** rejouer
   `finalize_manhua_single.py` (il DELETE des IDs et casse les progressions).
   **Backup** du CBZ avant remplacement (`.orig` conservé automatiquement).

## Vérification après coup

- `--plan` : le nombre de chapitres et le mapping doivent être cohérents (0
  MISMATCH), l'énumération finit sur un `end404` par chapitre.
- Après download : `python scripts/check_manhua_integrity.py <slug>` -> **0
  bad_image** (ou liste explicite des tronquées à re-tenter).
- Le premier chapitre lu doit s'enchaîner sans coupure sur le suivant (contrôle
  visuel d'un chapitre multi-strip : bas du strip N -> haut du strip N+1).
- Flask (8097) : le CBZ et la DB sont lus **à chaud** -> pas de redémarrage requis
  pour ce livre (redémarrer seulement si on bump `__version__`).

## Exceptions à surveiller (le site n'est PAS régulier)

Toujours lire la section `anomalies` de `_download_report.json` et **signaler pour
revue humaine** plutôt que deviner en silence :

- **Chapitres réellement tronqués/incomplets à la source** : un **404 réel**
  (vérifié avec retries) là où on attend une planche. Le noter précisément — ne
  pas inventer une planche.
- **Numérotation irrégulière** : le pas n'est pas garanti = 15 partout ; un strip
  peut manquer au milieu (trou) ou suivre un autre pas. Le script signale
  `short-chapter` (1 seul strip) — vérifier si c'est vraiment un chapitre court
  (<=15 pages) ou une troncature.
- **Décalage d'indice** chapitre<->dossier (`folder-offset`) : ne pas supposer
  `N -> _N` ; le script échantillonne l'og:image et bascule en résolution
  par-chapitre si besoin.
- **Chapitres décimaux** (ex. `172.5`) : slug parfois `ch172-5-…` ou absent du
  listing HTML ; ordre à préserver (`NNN.5` entre `NNN` et `NNN+1`). Signalé
  `decimal-chapter`.
- **Changements de domaine/CDN** dans le temps (`.org` vs `.com`, chemin
  `/storage/chapters/`) : re-vérifier si les 404 deviennent systématiques.
- **Variantes de pub** : d'autres bannières/filigranes que le GIF 728x90 connu ;
  élargir `manhua_adfilter.py` si de nouvelles apparaissent.
- **Formats mixtes** JPEG/WebP, `_stitched` ou non, selon l'âge du chapitre.
- **Instabilité / rate-limiting** : lenteur, 5xx, timeouts -> retries/backoff,
  reprise ; ne pas marteler le site.

## Provenance

Diagnostic & réparation : `docs/manhua-integrity-report-2026-09-18.md`,
`docs/manhua-repair-progress.md`. Règles détaillées :
`docs/roliascan-download-rules.md`.
