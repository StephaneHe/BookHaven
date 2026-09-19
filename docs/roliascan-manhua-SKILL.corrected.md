# ⚠️ Copie corrigée de SKILL.md — à recopier dans .claude/skills/roliascan-manhua/SKILL.md

Ce fichier contient la version **corrigée** de la skill (méthode autoritative,
suppression de la fausse règle « pas de 15 »). Il est ici parce que l'écriture
directe dans `.claude/` a été **bloquée par les permissions** durant la session
autonome du 2026-09-19. **Action manuelle requise** : remplacer le contenu de
`.claude/skills/roliascan-manhua/SKILL.md` par tout ce qui suit la ligne `---8<---`.

Le script (`fetch_manhua_strips.py`, `download_roliascan.py`) et les règles
(`docs/roliascan-download-rules.md`) sont, eux, déjà corrigés et committés.

---8<--- (copier à partir d'ici)

---
name: roliascan-manhua
description: Download any manhua/manhwa from roliascan.com cleanly and integrate it into BookHaven for continuous vertical reading. Use when the user wants to add a roliascan series, or fix/complete/repair an already-downloaded one (missing pages, truncated chapters, ads). Uses the site's AUTHORITATIVE chapter-content endpoint for the exact page list (NEVER a fixed step / index guess — the strip step varies), plus ad filtering, integrity checks, and BookHaven registration.
---

# Télécharger un manhua depuis roliascan → BookHaven

Procédure validée (download + réparations de « Sir, Don't Show Off »). Le script
fait tout ; cette skill explique **quoi lancer, comment vérifier, et les pièges**.

## Source de vérité : l'endpoint chapter-content (PAS de devinette d'index)

roliascan (thème « mangapeak », back Laravel) sert la liste EXACTE des planches
d'un chapitre via :

    GET https://roliascan.com/auth/chapter-content?chapter_id=<POSTID>
    -> {"success":true,"chapter_type":"media","images":[<URLs ordonnées>],"total":N}

`<POSTID>` = l'id du chapitre (slug `chN-<postid>`, ex. ch57-320165). Les `images`
sont les URLs CDN exactes (`roliascan.org/storage/chapters/manhwa_<id>_N/page_NNN[_stitched].webp`),
stitched OU jpg, **dans l'ordre**. On télécharge EXACTEMENT ces URLs. Aucune grille.

⛔ **NE JAMAIS supposer un pas de numérotation.** Les strips sont numérotés par
**index de 1ʳᵉ page source**, mais le **PAS VARIE** (14/15/16…) : ch57 =
`page_001/016/031/046/062` (46→62 = **+16**) ; ch99 = `page_001/015/029/043`
(**+14**). L'ancien « pas de 15 jusqu'au 404 » **sautait** des strips → chapitres
incomplets (ch50/ch57/ch99…). Corrigé : liste autoritative.

## Script

- `scripts/fetch_manhua_strips.py` : réparateur autoritatif (série connue ; lit
  `_chapters.json` = num→postid). `python scripts/fetch_manhua_strips.py [nums…]`.
- `scripts/download_roliascan.py <url|slug>` : pipeline complet nouvelle série
  (discover → download via chapter-content → combine CBZ → import 1 livre ; `--plan`).
- Puis : `check_manhua_integrity.py <slug>` (0 bad) ; `combine_manhua_cbz.py` (CBZ).

En-têtes : endpoint sur `roliascan.com` ; images sur `roliascan.org` (Referer
`https://roliascan.org/`). UA navigateur, retries, reprise, délais polis.

## Règles (voir `docs/roliascan-download-rules.md`)

1. Liste des planches = endpoint chapter-content. Pas de grille, pas de pas fixe.
2. Pubs : GIF 728×90 (md5 `ed6d7bf6aa`) sous fausse extension `.jpg` — reconnue et
   jamais enregistrée ; exclue du CBZ.
3. Intégrité : décodage PIL + marqueur de fin (JPEG FFD9 / PNG IEND / WebP RIFF).
4. BookHaven : un CBZ unique (`NNNNN_NNN`, préfixe/10 = chapitre, 172.5 préservé),
   lecture verticale continue ; `content_version` change → l'app invalide son cache.
   **NE JAMAIS** rejouer `finalize_manhua_single.py`. Backup avant remplacement.

## ⚠️ Exceptions à surveiller

Lire `anomalies` du manifeste et **signaler** :
- **PAS variable** (14/15/16…) → toujours l'endpoint, jamais une grille.
- **Chapitre verrouillé/vide** (`empty-chapter`, `success:false`/`images:[]`).
- **Pub incluse** dans la liste (728×90) → exclure.
- **Formats mixtes** jpg/webp, **chapitres décimaux** (172.5), **changement
  domaine/endpoint**, **instabilité/rate-limit** → retries, reprise.

## Provenance

`docs/manhua-recheck2-progress.md`, `docs/roliascan-download-rules.md`,
`docs/manhua-integrity-report-2026-09-18.md`.
