# Re-vérification #2 manhua « Sir, Don't Show Off » — correction du bug d'énumération (2026-09-19)

## Cause racine (le « pas de 15 » était FAUX)
Les strips sont numérotés par **index de 1ʳᵉ page source**, mais le **PAS VARIE** :
- ch57 = `page_001/016/031/046/062` (46→62 = **+16**),
- ch99 = `page_001/015/029/043` (**+14**).

L'ancien `fetch_manhua_strips.py` énumérait par **pas fixe de 15** : il sondait
`page_016`(404) pour ch99 → « 1 strip, court » (FAUX, 4 strips), et sautait
`page_062` pour ch57 (testait 061→076, tous 404) → chapitre tronqué. → **cause des
chapitres incomplets (ch50/ch57/ch99…).**

## Correction — source de vérité = endpoint du lecteur
Trouvé dans `chapter.js` du thème mangapeak :
```
GET https://roliascan.com/auth/chapter-content?chapter_id=<POSTID>
-> {"success":true,"images":[<URLs CDN exactes ordonnées>],"total":N}
```
`fetch_manhua_strips.py` **réécrit** : plus AUCUNE grille/pas — on télécharge
exactement les `images` de l'endpoint (stitched OU jpg), pubs 728×90 exclues.
`download_roliascan.py` et `docs/roliascan-download-rules.md` mis à jour idem.
SKILL.md : copie corrigée dans `docs/roliascan-manhua-SKILL.corrected.md`
(écriture `.claude/` bloquée par permissions cette session — à recopier).

## Résultat — 217 re-vérifiés, chapitres complétés
- Images : **1265 → 1322 (+57 strips)** ; intégrité **1322 img, 0 défectueuse**.
- **25 chapitres étaient incomplets**, désormais complets :

| Ch | +strips | Ch | +strips | Ch | +strips |
|---|---|---|---|---|---|
| 39 | +1 | 145 | +1 | 167 | +2 |
| 57 | +1 | 149 | +1 | 168 | +3 |
| 99 | +3 | 150 | +1 | 169 | +2 |
| 132 | +3 | 151 | +1 | 170 | +2 |
| 138 | +3 | 153 | +1 | 173 | +3 |
| 141 | +3 | 156 | +3 | 174 | +3 |
| 142 | +3 | 160 | +3 | 214 | +4 |
| 143 | +2 | 161 | +2 | | |
|  |  | 165 | +3 | | |
|  |  | 166 | +3 | | |

- **ch57 = COMPLET** : 5 strips `page_001/016/031/046/062`, CBZ `00570_001..005`,
  s'enchaîne sur ch58.
- **Chapitres réellement courts à la source** (endpoint `total`=1 ou 2) : vérifiés
  via l'endpoint (aucun n'était un faux-court parmi les 25 réparés) ; les chapitres
  restés à 1 image le sont légitimement d'après l'endpoint.
- Passe finale (217) : **0 téléchargement restant, 0 manquant, 0 anomalie.**

## CBZ / DB
CBZ régénéré **1263 → 1320 pages** (2 pubs filtrées), 1471 Mo. Backups : `.orig`,
`.pre-strips.bak`, `.pre-recheck2.bak`. DB id 39572 : page_count=1320,
file_size + `modified_at` MàJ → **`content_version` change** → l'app (≥1.9.0)
invalide son cache et re-télécharge. `finalize_manhua_single.py` NON rejoué.
