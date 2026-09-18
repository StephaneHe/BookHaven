# Manhua integrity audit — « Sir, Don't Show Off »

Date : 2026-09-18 · Source : roliascan.com (manhwa_319969) · Outil : `scripts/check_manhua_integrity.py`

## Synthèse

- Chapitres scannés : **217** (126 planches uniques « stitched » + 91 chapitres multi-planches).
- Images avant / après : **1045 → 971**.
- Images de contenu **corrompues / tronquées : 0** (aucune).
- Junk publicitaire supprimé : **74** fichiers = un unique GIF animé 728×90 (md5 `ed6d7bf6aa`) que roliascan sert en fin de chapitre sous une fausse extension `.jpg`. Déjà exclu du CBZ par `manhua_adfilter.py`; retiré des données pour un rapport d'intégrité honnête. Sauvegarde : `backup/manhua_ad_cleanup/`.
- Chapitres **tronqués À LA SOURCE (irrécupérables depuis roliascan)** : **42**.

## Le cas du chapitre 50 (signalé par l'utilisateur)

Diagnostic confirmé : la fin du ch50 est bien manquante, **mais ce n'est pas un défaut de téléchargement**. roliascan ne possède qu'un seul fichier pour ce chapitre — `manhwa_319969_50/page_001_stitched.webp` (750×14183 px) — **strictement identique octet pour octet** à notre copie (vérifié via le CDN + les métadonnées og:image/JSON-LD + l'API `/manga/v1`). Cette planche unique est coupée **en plein milieu d'un panneau** (personnage + onomatopée « PFFT »), et le ch51 démarre sur une **scène différente** (« I want a bowl of noodles »). Il n'existe ni `page_002`, ni panneaux individuels, ni variante non coupée. **La suite du ch50 n'est récupérable sur aucune URL roliascan.**

## Preuve du plafonnement à la source

Des hauteurs de planche **strictement identiques au pixel près** se répètent sur de nombreux chapitres — statistiquement impossible pour des contenus distincts (une collision à 20 chapitres a une probabilité ≈ 0). Ce sont les chapitres dont le « stitch » a été coupé à un gabarit fixe :

| Hauteur (px) | Nb de chapitres |
|---:|---:|
| 14183 | 20 |
| 14171 | 11 |
| 14748 | 5 |
| 14442 | 3 |
| 14479 | 3 |

**Chapitres tronqués à la source (confiance élevée, hauteur partagée ≥3) :** 037, 038, 039, 040, 041, 043, 044, 046, 047, 048, 049, 050, 052, 054, 055, 056, 057, 058, 059, 060, 061, 062, 063, 065, 067, 068, 070, 071, 072, 073, 074, 077, 083, 085, 087, 094, 109, 115, 123, 125, 129, 157.

**Chapitres à hauteur partagée par 2 (suspects, possiblement coïncidence) :** 075, 081, 091, 095, 097, 101, 102, 106, 107, 112, 133, 134, 146, 160, 164, 166.

## Réparations effectuées

1. Suppression des 74 fichiers-pub GIF (déjà exclus du CBZ) → rescan intégrité : **0 image défectueuse**.
2. **CBZ régénéré** depuis les données nettoyées (`combine_manhua_cbz.py`) : 217 chapitres, **969 pages**, 729,2 Mo — contenu identique (les pubs étaient déjà filtrées). Sauvegardes conservées : `.orig` (avec pubs) et `backup/manhua_ad_cleanup/*.pre-regen.bak`. Vérifié : `testzip` OK, ch49/50/51 présents.
3. Base : `file_size`/`page_count` du livre (id 39572) ré-affirmés (969 pages).

## Ce qui reste problématique

Les **42 chapitres tronqués à la source** ne peuvent PAS être réparés depuis roliascan (c'est roliascan qui sert une image coupée). Seule une **source/miroir alternatif** permettrait de récupérer les fins manquantes — hors du périmètre autorisé (roliascan uniquement). À décider par l'utilisateur.

## Tableau par chapitre (extrait des chapitres concernés)

| Ch | type | planches | hauteur | pubs retirées | statut |
|---:|:--|---:|---:|---:|:--|
| 1 | panels | 11 | - | 2 | ok |
| 2 | panels | 6 | - | 2 | ok |
| 3 | panels | 8 | - | 2 | ok |
| 4 | panels | 8 | - | 2 | ok |
| 5 | panels | 9 | - | 2 | ok |
| 6 | panels | 5 | - | 2 | ok |
| 7 | panels | 4 | - | 2 | ok |
| 8 | panels | 4 | - | 2 | ok |
| 9 | panels | 4 | - | 2 | ok |
| 10 | panels | 5 | - | 2 | ok |
| 11 | panels | 6 | - | 2 | ok |
| 12 | panels | 9 | - | 2 | ok |
| 13 | panels | 8 | - | 2 | ok |
| 14 | panels | 7 | - | 2 | ok |
| 15 | panels | 8 | - | 2 | ok |
| 16 | panels | 8 | - | 2 | ok |
| 18 | panels | 7 | - | 2 | ok |
| 19 | panels | 6 | - | 2 | ok |
| 20 | panels | 8 | - | 2 | ok |
| 21 | panels | 12 | - | 2 | ok |
| 22 | panels | 8 | - | 2 | ok |
| 23 | panels | 7 | - | 2 | ok |
| 24 | panels | 9 | - | 2 | ok |
| 25 | panels | 8 | - | 2 | ok |
| 26 | panels | 8 | - | 2 | ok |
| 27 | panels | 7 | - | 2 | ok |
| 28 | panels | 8 | - | 2 | ok |
| 29 | panels | 9 | - | 2 | ok |
| 30 | panels | 8 | - | 2 | ok |
| 31 | panels | 3 | - | 2 | ok |
| 32 | panels | 4 | - | 2 | ok |
| 33 | panels | 4 | - | 2 | ok |
| 34 | panels | 3 | - | 2 | ok |
| 35 | panels | 4 | - | 2 | ok |
| 36 | panels | 4 | - | 2 | ok |
| 37 | stitched | 1 | 14183 | 0 | tronqué source (irrécupérable) |
| 38 | stitched | 1 | 14183 | 0 | tronqué source (irrécupérable) |
| 39 | stitched | 1 | 14183 | 0 | tronqué source (irrécupérable) |
| 40 | stitched | 1 | 14183 | 0 | tronqué source (irrécupérable) |
| 41 | stitched | 1 | 14183 | 0 | tronqué source (irrécupérable) |
| 43 | stitched | 1 | 14183 | 0 | tronqué source (irrécupérable) |
| 44 | stitched | 1 | 14183 | 0 | tronqué source (irrécupérable) |
| 45 | panels | 38 | - | 2 | ok |
| 46 | stitched | 1 | 14183 | 0 | tronqué source (irrécupérable) |
| 47 | stitched | 1 | 14183 | 0 | tronqué source (irrécupérable) |
| 48 | stitched | 1 | 14183 | 0 | tronqué source (irrécupérable) |
| 49 | stitched | 1 | 14183 | 0 | tronqué source (irrécupérable) |
| 50 | stitched | 1 | 14183 | 0 | tronqué source (irrécupérable) |
| 52 | stitched | 1 | 14183 | 0 | tronqué source (irrécupérable) |
| 54 | stitched | 1 | 14183 | 0 | tronqué source (irrécupérable) |
| 55 | stitched | 1 | 14183 | 0 | tronqué source (irrécupérable) |
| 56 | stitched | 1 | 14183 | 0 | tronqué source (irrécupérable) |
| 57 | stitched | 1 | 14183 | 0 | tronqué source (irrécupérable) |
| 58 | stitched | 1 | 14183 | 0 | tronqué source (irrécupérable) |
| 59 | stitched | 1 | 14183 | 0 | tronqué source (irrécupérable) |
| 60 | stitched | 1 | 14183 | 0 | tronqué source (irrécupérable) |
| 61 | stitched | 1 | 14171 | 0 | tronqué source (irrécupérable) |
| 62 | stitched | 1 | 14171 | 0 | tronqué source (irrécupérable) |
| 63 | stitched | 1 | 14171 | 0 | tronqué source (irrécupérable) |
| 65 | stitched | 1 | 14171 | 0 | tronqué source (irrécupérable) |
| 67 | stitched | 1 | 14171 | 0 | tronqué source (irrécupérable) |
| 68 | stitched | 1 | 14171 | 0 | tronqué source (irrécupérable) |
| 69 | panels | 35 | - | 2 | ok |
| 70 | stitched | 1 | 14171 | 0 | tronqué source (irrécupérable) |
| 71 | stitched | 1 | 14171 | 0 | tronqué source (irrécupérable) |
| 72 | stitched | 1 | 14171 | 0 | tronqué source (irrécupérable) |
| 73 | stitched | 1 | 14171 | 0 | tronqué source (irrécupérable) |
| 74 | stitched | 1 | 14171 | 0 | tronqué source (irrécupérable) |
| 75 | stitched | 1 | 14383 | 0 | suspect (hauteur ×2) |
| 77 | stitched | 1 | 14442 | 0 | tronqué source (irrécupérable) |
| 81 | stitched | 1 | 14383 | 0 | suspect (hauteur ×2) |
| 83 | stitched | 1 | 14442 | 0 | tronqué source (irrécupérable) |
| 85 | stitched | 1 | 14479 | 0 | tronqué source (irrécupérable) |
| 87 | stitched | 1 | 14479 | 0 | tronqué source (irrécupérable) |
| 91 | stitched | 1 | 14751 | 0 | suspect (hauteur ×2) |
| 94 | stitched | 1 | 14479 | 0 | tronqué source (irrécupérable) |
| 95 | stitched | 1 | 14627 | 0 | suspect (hauteur ×2) |
| 97 | stitched | 1 | 14772 | 0 | suspect (hauteur ×2) |
| 101 | stitched | 1 | 14749 | 0 | suspect (hauteur ×2) |
| 102 | stitched | 1 | 14768 | 0 | suspect (hauteur ×2) |
| 106 | stitched | 1 | 14768 | 0 | suspect (hauteur ×2) |
| 107 | stitched | 1 | 14749 | 0 | suspect (hauteur ×2) |
| 109 | stitched | 1 | 14748 | 0 | tronqué source (irrécupérable) |
| 112 | stitched | 1 | 14772 | 0 | suspect (hauteur ×2) |
| 115 | stitched | 1 | 14748 | 0 | tronqué source (irrécupérable) |
| 123 | stitched | 1 | 14748 | 0 | tronqué source (irrécupérable) |
| 125 | stitched | 1 | 14748 | 0 | tronqué source (irrécupérable) |
| 129 | stitched | 1 | 14748 | 0 | tronqué source (irrécupérable) |
| 133 | stitched | 1 | 14751 | 0 | suspect (hauteur ×2) |
| 134 | stitched | 1 | 14627 | 0 | suspect (hauteur ×2) |
| 146 | stitched | 1 | 14783 | 0 | suspect (hauteur ×2) |
| 157 | stitched | 1 | 14442 | 0 | tronqué source (irrécupérable) |
| 160 | stitched | 1 | 14756 | 0 | suspect (hauteur ×2) |
| 164 | stitched | 1 | 14756 | 0 | suspect (hauteur ×2) |
| 166 | stitched | 1 | 14783 | 0 | suspect (hauteur ×2) |

_(Les chapitres « ok » sans pub retirée ni troncature ne sont pas listés. Rapport machine complet : `data/manhua/sir-dont-show-off/_repair_report.json`.)_