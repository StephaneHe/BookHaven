# Règles de téléchargement roliascan → BookHaven

Consignées à partir du download initial **et** de la réparation de « Sir, Don't
Show Off » (voir `docs/manhua-integrity-report-2026-09-18.md`,
`docs/manhua-repair-progress.md`). Implémentées dans
`scripts/download_roliascan.py` ; exposées comme skill dans
`.claude/skills/roliascan-manhua/SKILL.md`.

## 1. Source autoritative : le CDN `.org`, pas le HTML `.com`

- Les images vivent sur :
  `https://roliascan.org/storage/chapters/manhwa_<MANGA_ID>_<CHAP_NUM>/page_<NNN>[_stitched].<ext>`
- **NE PAS** se fier à la page HTML du chapitre sur `roliascan.com` : elle
  sous-liste les images (og:image / JSON-LD ne montrent souvent que la **1ʳᵉ**
  planche). C'est l'erreur qui avait fait conclure à tort « ch50 tronqué à la
  source ». Le CDN `.org/storage/chapters/` fait autorité.
- En-têtes obligatoires : **User-Agent navigateur** + **`Referer: https://roliascan.org/`**
  (sans ça le CDN peut bloquer).

## 2. Numérotation des planches — « strips stitched », PAS DE 15

- Un chapitre est servi en **un ou plusieurs strips hauts** numérotés par leur
  **première page source** : `page_001_stitched.webp` (pages 1–15),
  `page_016_stitched.webp` (16–30), `page_031` (31–45), `page_046` … → **pas de 15**.
- **Énumérer jusqu'au 404 RÉEL.** Un 404 doit être confirmé par **retries**
  (l'ancien `fetch_manhua.py` s'arrêtait au 1ᵉʳ 404 `page_002` et ne gardait que le
  strip 1 → ~109 chapitres coupés). Ne jamais conclure « fin » sur une erreur
  transitoire.
- Chapitres courts/anciens : parfois en **pages contiguës** (`page_001.jpg`,
  `page_002.jpg`, … pas de 1). Détecter le schéma par sondage de `page_001`.
- Formats **mixtes** possibles : JPEG ou WebP, `_stitched` ou non, selon l'âge.

## 3. Découverte des chapitres & mapping chapitre→dossier CDN

- Page série : `https://roliascan.com/series/<slug>/`. Elle contient :
  - `manga_id` via `data-manga-id="<id>"` (ou `manhwa_<id>_` dans les URLs),
  - le **read-slug** via les liens `/read/<read-slug>/ch…/` (différent du slug
    série : `sir-dont-show-off` vs `sir-don-t-show-off`),
  - **tous** les slugs de chapitres `ch<num>-<postid>` (num éventuellement décimal).
- **Dossier CDN** confirmé via l'**og:image** d'un échantillon de chapitres.
  Observé sur ce titre : **chapitre affiché N → dossier `_N`** (aucun décalage).
  Vérifier ; si décalage, résoudre **chaque** chapitre par son og:image.

## 4. Filtrage des publicités

- Bannière récurrente **728×90** injectée en fin de chapitre sous **fausse
  extension `.jpg`** (en réalité un GIF animé, md5 `ed6d7bf6aa`, ~85 633 o,
  « BEST WEBSITE TO WATCH… »), plus filigranes fins **LIKEMANGA.IO / WEBNOVEL**.
- `manhua_adfilter.py` : rejette les tailles IAB connues (728×90, 970×250, …) et
  les bandes **larges & courtes** (ratio ≥ 3, hauteur ≤ 120 px). Au download, le
  GIF est reconnu par signature/hash et traité comme **fin de contenu**.
- Ces pubs sont **exclues du CBZ** (jamais montrées au lecteur).

## 5. Robustesse

- Retries + backoff, **reprise** (skip des planches déjà valides sur disque),
  concurrence limitée, délais polis (**site lent/instable**), timeouts.
- Idempotent : relancer ne re-télécharge que le manquant.

## 6. Intégrité

- Chaque image doit **décoder** (PIL, `LOAD_TRUNCATED_IMAGES=False`) **et** avoir
  un **marqueur de fin** valide : JPEG `FF D9`, PNG `IEND`, WebP taille RIFF
  cohérente. Les tronquées sont re-téléchargées ou signalées.
- Contrôle : `python scripts/check_manhua_integrity.py <slug>` → `bad_images=0`.

## 7. Intégration BookHaven

- **Un seul CBZ continu** : toutes les planches, renommées de façon triable
  `NNNNN_NNN.<ext>` avec `NNNNN = chapitre × 10` (décimaux préservés : `172.5`
  → préfixe `01725`). Le lecteur **web continu (v2.7.0)** dérive les chapitres du
  préfixe des planches (préfixe/10 = numéro), lecture **verticale continue**.
- Pubs filtrées à la construction du CBZ.
- Enregistré comme **un seul livre** (INSERT idempotent, `genre='Comics'` pour que
  le scan complet le préserve). **Backup** du CBZ avant remplacement (`.orig`).
- ⚠️ **NE JAMAIS** rejouer `finalize_manhua_single.py` : il **DELETE** les lignes
  de la série et peut casser des IDs / progressions de lecture. Le
  `download_roliascan.py` fait un enregistrement **non destructif**.
- Flask 8097 : CBZ + DB lus **à chaud** → pas de redémarrage requis (sauf bump
  `__version__`).

## 8. ⚠️ Exceptions à surveiller (le site n'est PAS régulier)

Le script écrit une section `anomalies` dans `data/manhua/<slug>/_download_report.json`.
**Toujours la revoir** et **signaler pour revue humaine** au lieu de deviner :

| Anomalie | Signal | Action |
|---|---|---|
| Chapitre tronqué/incomplet à la source | 404 réel là où on attend une planche | Le noter précisément ; ne pas inventer |
| Numérotation irrégulière / trou | `short-chapter`, strip manquant au milieu | Vérifier chapitre court (≤15 p.) vs troncature |
| Décalage d'indice chapitre↔dossier | `folder-offset` (og:image ≠ N) | Résolution par-chapitre via og:image |
| Chapitre décimal (172.5) | `decimal-chapter` | Slug parfois `ch172-5-…` ; préserver l'ordre |
| Changement domaine/CDN | 404 systématiques | Re-vérifier `.org` / chemin `/storage/chapters/` |
| Variante de pub | nouvelle bannière/filigrane | Élargir `manhua_adfilter.py` |
| Instabilité / rate-limit | lenteur, 5xx, timeouts | Retries/backoff, reprise ; ne pas marteler |
