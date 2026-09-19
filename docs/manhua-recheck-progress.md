# Re-vérification intégrité manhua « Sir, Don't Show Off » (2026-09-19)

Déclencheur : utilisateur signale le **ch57 incomplet** malgré la réparation
précédente (+294 strips). Objectif : re-vérifier **exhaustivement les 217
chapitres** contre le CDN, sans se fier au bilan précédent.

## Méthode
`scripts/fetch_manhua_strips.py` (durci ce tour) : chapitre affiché N → dossier
`manhwa_319969_N` (identité confirmée og:image), strips `page_001/016/031/046…`
**pas de 15**, CDN `roliascan.org/storage`. **Durcissement** : fin de chapitre =
**2 404 consécutifs** (au lieu du 1er 404) → un strip manquant au milieu (trou
source) est détecté (`source-gap`) au lieu de tronquer le chapitre.

## Résultat — RIEN À COMPLÉTER (données déjà complètes)
Re-vérif des **217 chapitres** (lots 1-72, 73-144, 145-216 + 172.5) :
- **strips téléchargés = 0** (tout déjà présent en local == CDN),
- **trous source (`source-gap`) = 0**, **tronqués = 0**, **anomalies = 0**,
- intégrité (décodage PIL + marqueurs de fin) : **1265 images, 0 défectueuse**.

Inventaire : 126 stitched (109 multi-strip, **17 genuinement courts** ≤15 pages),
91 paged (jpg). Total 1265 unités. Manifeste : `_recheck_inventory.json`,
`_strips_manifest.json`.

### ch57 (signalé)
`data/manhua/.../057/` = **4 strips** `page_001/016/031/046_stitched.webp`, tous
décodent (750×14183/14258/14528/14433, RIFF OK), **identiques octet-pour-octet au
CDN**. CDN ch57 : page_061 = **404 réel** (fin). CBZ : `00570_001..004.webp`.
og:image : ch56→_56, ch57→_57, ch58→_58 (aucun décalage). **ch57 est COMPLET et
s'enchaîne sur ch58.**

### Chapitres réellement courts à la source (≤15 pages, `page_016` = 404 réel)
099, 132, 138, 141, 142, 143, 156, 160, 161, 165, 166, 167, 168, 169, 170, 173, 174
(17 chapitres — 1 strip légitime, pas un manque de notre côté).

## Conclusion — cause probable côté APP, pas serveur
Le serveur (données, CBZ 1263 pages, CDN) est **cohérent et complet**. Le ch57
« incomplet » vu par l'utilisateur vient très probablement de l'**app Android non
mise à jour** : avant la réparation (+294 strips), ch57 n'avait qu'1 strip ; une
app **antérieure à 1.9.0 / serveur 2.7.6** a pu **mettre en cache** cet ancien
contenu sans `content_version` et ne jamais le rafraîchir. Le correctif
d'invalidation de cache (`content_version`, lot précédent) + le nouveau lecteur
pleine largeur sont dans l'**APK 1.9.0** : l'installer résout l'affichage.

## Actions
- **Aucun re-téléchargement** (rien ne manquait).
- **CBZ NON régénéré** : contenu inchangé (0 strip ajouté) → régénérer un
  fichier de 1,4 Go identique est inutile et risquerait le lecteur en cours.
  `content_version` reste correct (les données n'ont pas changé).
- Durcissement de `fetch_manhua_strips.py` conservé (protège les futurs
  téléchargements contre une troncature sur trou-source).
