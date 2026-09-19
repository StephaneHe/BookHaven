# Règles de téléchargement roliascan → BookHaven

Consignées à partir du download initial **et** des réparations de « Sir, Don't
Show Off ». Implémentées dans `scripts/fetch_manhua_strips.py` (série connue) et
`scripts/download_roliascan.py` (n'importe quelle série). Skill :
`.claude/skills/roliascan-manhua/SKILL.md`.

## 0. RÈGLE CENTRALE — liste des planches = endpoint autoritatif (PAS de devinette)

roliascan (thème « mangapeak », back Laravel) expose la liste EXACTE et ordonnée
des planches d'un chapitre :

```
GET https://roliascan.com/auth/chapter-content?chapter_id=<POSTID>
-> {"success":true,"chapter_type":"media","images":[<URLs CDN ordonnées>],"total":N}
```

`<POSTID>` = l'id dans le slug `chN-<postid>` (ex. ch57 → 320165). On télécharge
**exactement ces URLs** (stitched OU pages jpg, dans l'ordre). Pas d'auth requise.

⛔ **NE JAMAIS supposer un PAS de numérotation des strips.** Les strips sont
numérotés par **index de 1ʳᵉ page source**, mais le **PAS VARIE** (14, 15, 16, …) :
- **ch57** = `page_001/016/031/046/062` → 46→62 = **+16**
- **ch99** = `page_001/015/029/043` → **+14**

Une ancienne version énumérait « pas de 15 jusqu'au 404 » : elle sondait `page_016`
(404) pour ch99 et concluait « 1 seul strip, chapitre court » — **FAUX** (4 strips) ;
et pour ch57 elle sautait de `page_061`(404) à `page_076`(404) sans jamais tester
`page_062`, tronquant le chapitre. **C'est la cause des chapitres incomplets
(ch50, ch57, ch99, …).** Corrigé : on lit la liste autoritative, aucune grille.

## 1. Hôtes & en-têtes

- **chapter-content** : sur `roliascan.com`, Referer `https://roliascan.com/`.
- **Images** : sur `roliascan.org/storage/chapters/manhwa_<id>_N/…`, Referer
  **`https://roliascan.org/`** (sinon blocage CDN).
- UA navigateur, retries/backoff, reprise (skip des fichiers déjà valides), délais.

## 2. Découverte de la série (pour une nouvelle série)

Page série `https://roliascan.com/series/<slug>/` : `manga_id` via
`data-manga-id`, read-slug via les liens `/read/…`, et **tous** les slugs
`ch<num>-<postid>` (num éventuellement décimal). Le mapping chapitre→dossier CDN
`_N` est confirmé par og:image, mais **inutile pour le download** puisque les URLs
viennent de l'endpoint.

## 3. Filtrage des publicités

Bannière **728×90** injectée en fin de chapitre sous **fausse extension `.jpg`**
(GIF animé, md5 `ed6d7bf6aa`, ~85 633 o). L'endpoint la liste parfois dans
`images` : la reconnaître par hash/format et **ne jamais l'enregistrer** (ni la
compter comme contenu). Exclue du CBZ par `manhua_adfilter.py`.

## 4. Intégrité

Chaque image doit **décoder** (PIL, `LOAD_TRUNCATED_IMAGES=False`) **et** avoir un
**marqueur de fin** valide : JPEG `FF D9`, PNG `IEND`, WebP taille RIFF cohérente.
Contrôle : `python scripts/check_manhua_integrity.py <slug>` → `bad_images=0`.

## 5. Intégration BookHaven

- **Un seul CBZ continu** : planches renommées `NNNNN_NNN.<ext>` avec
  `NNNNN = chapitre × 10` (décimaux préservés : `172.5` → `01725`). Lecteur web
  continu (v2.7.0) : chapitres dérivés du préfixe (préfixe/10). Pubs filtrées.
- Enregistré comme **un seul livre** (INSERT idempotent). `content_version`
  (`file_size:modified_at`) change à la régénération → l'app Android invalide son
  cache et re-télécharge (lot 2.7.6 / android 1.9.0).
- ⚠️ **NE JAMAIS** rejouer `finalize_manhua_single.py` (DELETE d'IDs / casse les
  progressions). **Backup** du CBZ avant remplacement (`.orig` + `.bak`).
- Flask 8097 : CBZ + DB lus **à chaud** → pas de redémarrage requis (sauf bump
  `__version__`).

## 6. ⚠️ Exceptions à surveiller (le site n'est PAS régulier)

Section `anomalies` de `_strips_manifest.json` / `_download_report.json` — **signaler**
plutôt que deviner :

| Anomalie | Signal | Action |
|---|---|---|
| **PAS variable** (14/15/16…) | — | TOUJOURS l'endpoint chapter-content, jamais une grille |
| Chapitre verrouillé/vide | `empty-chapter` (`success:false`/`images:[]`) | Signaler (≠ chapitre court réel) |
| Pub incluse dans la liste | GIF 728×90 md5 `ed6d7bf6aa` | Exclure, ne pas compter |
| Strip introuvable | `missing-strip` | Re-tenter ; noter si persiste |
| Formats mixtes | jpg vs webp `_stitched` | Géré (on suit l'URL) |
| Chapitre décimal (172.5) | postid propre | Préserver l'ordre |
| Changement domaine/endpoint | échecs `fetch-failed` | Re-vérifier `.org`/`.com`/`/auth/chapter-content` |
| Instabilité / rate-limit | lenteur, 5xx, timeouts | Retries/backoff, reprise ; ne pas marteler |

## Provenance

`docs/manhua-recheck2-progress.md` (correction du bug d'énumération, 2026-09-19),
`docs/manhua-integrity-report-2026-09-18.md`.
