# Réparation strips manhua — « Sir, Don't Show Off »

Date : 2026-09-18 · CDN autoritatif : `roliascan.org/storage/chapters/manhwa_319969_<N>/`

## Correction du diagnostic précédent (IMPORTANT)
Le rapport précédent concluait à tort « ch50 tronqué à la source, irrécupérable ». **FAUX.**
Chaque chapitre « stitched » est servi en **plusieurs strips hauts** numérotés
`page_001/016/031/046…` **par pas de 15** (chaque strip = 15 pages sources). L'ancien
téléchargeur (`fetch_manhua.py`) s'arrêtait au 1er 404 (`page_002`) et ne gardait que le
**strip 1** de chaque chapitre stitched. Les strips suivants existaient sur le CDN ; ils ont
été récupérés (`scripts/fetch_manhua_strips.py`, pas de 15 jusqu'au 404 réel).

Mapping confirmé via og:image du site : chapitre affiché **N → dossier `_N`** (aucun décalage ;
le « _49 » du signalement était un décalage de transcription).

## Synthèse
- Chapitres : **217** (126 stitched, 91 paged jpg).
- Images : **971 → 1265** (**+294 strips récupérés**).
- Chapitres stitched réparés (strips ajoutés) : **109**.
- Chapitres stitched genuinement à 1 strip (≤15 pages ; `page_016` = 404 réel vérifié 6× retries) : **17** → 099, 132, 138, 141, 142, 143, 156, 160, 161, 165, 166, 167, 168, 169, 170, 173, 174.
- Images corrompues/tronquées après réparation : **0** (décodage PIL complet des 1265).
- Vraies absences côté CDN (404 réel) : **aucune** au-delà de la fin de chaque chapitre.
- CBZ régénéré : **1263 pages** (2 pubs filtrées), 1362,9 Mo. Backups : `.orig`, `.pre-regen.bak`, `.pre-strips.bak`.

## ch50 (cas signalé)
- CDN `_50` : strips [1, 16, 31, 46] (fin 404 à page_[61]).
- CBZ : `00500_001..004.webp` (4 strips ordonnés). Continuité strip-001→016 vérifiée
  visuellement (la même scène « PFFT » se poursuit). Enchaîne sur ch51 (`00510_*`, 4 strips).

## Tableau par chapitre stitched

| Ch | strips (CDN) | nb strips | récupérés | fin 404 |
|---:|:--|---:|---:|:--|
| 37 | [1, 16, 31] | 3 | 2 | page_[46] |
| 38 | [1, 16, 31] | 3 | 2 | page_[46] |
| 39 | [1, 16, 31] | 3 | 2 | page_[46] |
| 40 | [1, 16, 31] | 3 | 2 | page_[46] |
| 41 | [1, 16, 31] | 3 | 2 | page_[46] |
| 42 | [1, 16, 31] | 3 | 2 | page_[46] |
| 43 | [1, 16, 31] | 3 | 2 | page_[46] |
| 44 | [1, 16, 31, 46] | 4 | 3 | page_[61] |
| 46 | [1, 16, 31, 46] | 4 | 3 | page_[61] |
| 47 | [1, 16, 31] | 3 | 2 | page_[46] |
| 48 | [1, 16, 31] | 3 | 2 | page_[46] |
| 49 | [1, 16, 31] | 3 | 2 | page_[46] |
| 50 | [1, 16, 31, 46] | 4 | 3 | page_[61] |
| 51 | [1, 16, 31, 46] | 4 | 3 | page_[61] |
| 52 | [1, 16, 31, 46] | 4 | 3 | page_[61] |
| 53 | [1, 16, 31, 46] | 4 | 3 | page_[61] |
| 54 | [1, 16, 31, 46] | 4 | 3 | page_[61] |
| 55 | [1, 16, 31, 46] | 4 | 3 | page_[61] |
| 56 | [1, 16, 31, 46] | 4 | 3 | page_[61] |
| 57 | [1, 16, 31, 46] | 4 | 3 | page_[61] |
| 58 | [1, 16, 31, 46] | 4 | 3 | page_[61] |
| 59 | [1, 16, 31, 46] | 4 | 3 | page_[61] |
| 60 | [1, 16, 31, 46] | 4 | 3 | page_[61] |
| 61 | [1, 16, 31, 46] | 4 | 3 | page_[61] |
| 62 | [1, 16, 31, 46] | 4 | 3 | page_[61] |
| 63 | [1, 16, 31, 46] | 4 | 3 | page_[61] |
| 64 | [1, 16, 31, 46] | 4 | 3 | page_[61] |
| 65 | [1, 16, 31, 46] | 4 | 3 | page_[61] |
| 66 | [1, 16, 31, 46] | 4 | 3 | page_[61] |
| 67 | [1, 16, 31, 46] | 4 | 3 | page_[61] |
| 68 | [1, 16, 31, 46] | 4 | 3 | page_[61] |
| 70 | [1, 16, 31, 46] | 4 | 3 | page_[61] |
| 71 | [1, 16, 31, 46] | 4 | 3 | page_[61] |
| 72 | [1, 16, 31, 46] | 4 | 3 | page_[61] |
| 73 | [1, 16, 31, 46] | 4 | 3 | page_[61] |
| 74 | [1, 16, 31, 46] | 4 | 3 | page_[61] |
| 75 | [1, 16, 31, 46] | 4 | 3 | page_[61] |
| 76 | [1, 16, 31, 46] | 4 | 3 | page_[61] |
| 77 | [1, 16, 31, 46] | 4 | 3 | page_[61] |
| 78 | [1, 16, 31, 46] | 4 | 3 | page_[61] |
| 79 | [1, 16, 31, 46] | 4 | 3 | page_[61] |
| 80 | [1, 16, 31, 46] | 4 | 3 | page_[61] |
| 81 | [1, 16, 31, 46] | 4 | 3 | page_[61] |
| 82 | [1, 16, 31, 46] | 4 | 3 | page_[61] |
| 83 | [1, 16, 31, 46] | 4 | 3 | page_[61] |
| 84 | [1, 16, 31, 46] | 4 | 3 | page_[61] |
| 85 | [1, 16, 31] | 3 | 2 | page_[46] |
| 86 | [1, 16, 31, 46] | 4 | 3 | page_[61] |
| 87 | [1, 16, 31, 46] | 4 | 3 | page_[61] |
| 88 | [1, 16, 31, 46] | 4 | 3 | page_[61] |
| 89 | [1, 16, 31, 46] | 4 | 3 | page_[61] |
| 90 | [1, 16, 31, 46] | 4 | 3 | page_[61] |
| 91 | [1, 16, 31, 46] | 4 | 3 | page_[61] |
| 92 | [1, 16, 31, 46] | 4 | 3 | page_[61] |
| 93 | [1, 16, 31, 46] | 4 | 3 | page_[61] |
| 94 | [1, 16, 31, 46] | 4 | 3 | page_[61] |
| 95 | [1, 16, 31, 46] | 4 | 3 | page_[61] |
| 96 | [1, 16, 31, 46] | 4 | 3 | page_[61] |
| 97 | [1, 16, 31, 46] | 4 | 3 | page_[61] |
| 98 | [1, 16, 31, 46] | 4 | 3 | page_[61] |
| 99 | [1] | 1 | 0 | page_[16] |
| 100 | [1, 16, 31, 46] | 4 | 3 | page_[61] |
| 101 | [1, 16, 31, 46] | 4 | 3 | page_[61] |
| 102 | [1, 16, 31, 46] | 4 | 3 | page_[61] |
| 103 | [1, 16, 31] | 3 | 2 | page_[46] |
| 104 | [1, 16, 31, 46] | 4 | 3 | page_[61] |
| 105 | [1, 16, 31, 46] | 4 | 3 | page_[61] |
| 106 | [1, 16, 31, 46] | 4 | 3 | page_[61] |
| 107 | [1, 16, 31, 46] | 4 | 3 | page_[61] |
| 108 | [1, 16, 31, 46] | 4 | 3 | page_[61] |
| 109 | [1, 16, 31, 46] | 4 | 3 | page_[61] |
| 110 | [1, 16, 31, 46] | 4 | 3 | page_[61] |
| 111 | [1, 16, 31, 46] | 4 | 3 | page_[61] |
| 112 | [1, 16, 31, 46] | 4 | 3 | page_[61] |
| 113 | [1, 16, 31, 46] | 4 | 3 | page_[61] |
| 114 | [1, 16, 31] | 3 | 2 | page_[46] |
| 115 | [1, 16, 31, 46] | 4 | 3 | page_[61] |
| 116 | [1, 16, 31, 46] | 4 | 3 | page_[61] |
| 117 | [1, 16, 31] | 3 | 2 | page_[46] |
| 118 | [1, 16, 31, 46] | 4 | 3 | page_[61] |
| 119 | [1, 16, 31] | 3 | 2 | page_[46] |
| 120 | [1, 16, 31, 46] | 4 | 3 | page_[61] |
| 121 | [1, 16, 31, 46] | 4 | 3 | page_[61] |
| 123 | [1, 16, 31] | 3 | 2 | page_[46] |
| 125 | [1, 16, 31, 46] | 4 | 3 | page_[61] |
| 126 | [1, 16, 31, 46] | 4 | 3 | page_[61] |
| 128 | [1, 16, 31] | 3 | 2 | page_[46] |
| 129 | [1, 16, 31, 46] | 4 | 3 | page_[61] |
| 130 | [1, 16, 31] | 3 | 2 | page_[46] |
| 132 | [1] | 1 | 0 | page_[16] |
| 133 | [1, 16, 31] | 3 | 2 | page_[46] |
| 134 | [1, 16, 31, 46] | 4 | 3 | page_[61] |
| 135 | [1, 16, 31, 46] | 4 | 3 | page_[61] |
| 136 | [1, 16, 31] | 3 | 2 | page_[46] |
| 137 | [1, 16, 31, 46] | 4 | 3 | page_[61] |
| 138 | [1] | 1 | 0 | page_[16] |
| 139 | [1, 16, 31, 46] | 4 | 3 | page_[61] |
| 140 | [1, 16, 31, 46] | 4 | 3 | page_[61] |
| 141 | [1] | 1 | 0 | page_[16] |
| 142 | [1] | 1 | 0 | page_[16] |
| 143 | [1] | 1 | 0 | page_[16] |
| 144 | [1, 16, 31] | 3 | 2 | page_[46] |
| 145 | [1, 16, 31] | 3 | 2 | page_[46] |
| 146 | [1, 16, 31] | 3 | 2 | page_[46] |
| 147 | [1, 16, 31, 46] | 4 | 3 | page_[61] |
| 148 | [1, 16, 31, 46] | 4 | 3 | page_[61] |
| 149 | [1, 16] | 2 | 1 | page_[31] |
| 150 | [1, 16] | 2 | 1 | page_[31] |
| 151 | [1, 16, 31] | 3 | 2 | page_[46] |
| 152 | [1, 16, 31, 46] | 4 | 3 | page_[61] |
| 153 | [1, 16] | 2 | 1 | page_[31] |
| 156 | [1] | 1 | 0 | page_[16] |
| 157 | [1, 16, 31] | 3 | 2 | page_[46] |
| 159 | [1, 16, 31] | 3 | 2 | page_[46] |
| 160 | [1] | 1 | 0 | page_[16] |
| 161 | [1] | 1 | 0 | page_[16] |
| 162 | [1, 16, 31] | 3 | 2 | page_[46] |
| 164 | [1, 16, 31, 46] | 4 | 3 | page_[61] |
| 165 | [1] | 1 | 0 | page_[16] |
| 166 | [1] | 1 | 0 | page_[16] |
| 167 | [1] | 1 | 0 | page_[16] |
| 168 | [1] | 1 | 0 | page_[16] |
| 169 | [1] | 1 | 0 | page_[16] |
| 170 | [1] | 1 | 0 | page_[16] |
| 173 | [1] | 1 | 0 | page_[16] |
| 174 | [1] | 1 | 0 | page_[16] |

_(91 chapitres paged (jpg) : complets, non listés. Manifeste : `data/manhua/sir-dont-show-off/_strips_manifest.json`.)_