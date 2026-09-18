# Contre-expertise refonte Android BookHaven — Anthropic Fable — 2026-09-18

Arbitrage indépendant de `docs/bookhaven-redesign-astra.md` (GPT-6 Astra). **Read-only** : aucun
code, version, DB ni serveur modifié. Toutes les preuves ci-dessous ont été relues dans le dépôt
par moi ; deux points ont été **testés** sur une base SQLite temporaire hors projet.

Convention : **K =** `android/app/src/main/kotlin/com/bookhaven/android/`.

## 0. Synthèse en 8 lignes

1. **Crash Android = OOM par conception : CONFIRMÉ.** Le fix « références + accès page à la demande »
   est correct ; il devient **suffisant** dès qu'on y ajoute un affichage tuilé — et une **bibliothèque
   existante le fournit** (voir §1) : inutile d'écrire un moteur de tuiles ni des tuiles serveur.
2. **Le CBZ unique est gardable.** Aucune ré-architecture des données n'est nécessaire pour ouvrir le manhua.
3. **Pagination limitée à 50 + facettes déduites : CONFIRMÉ**, et c'est pire que décrit : le
   **snapshot hors-ligne est lui aussi plafonné à 50** (`K/ui/library/LibraryViewModel.kt:98`).
4. **Scroll vertical virtualisé : bonne cible**, mais à livrer en 2 temps (d'abord « s'ouvre sans
   crash », ensuite « vertical »), avec la même astuce que le web v2.7.0 : chapitres **dérivés des
   noms de planches**, sans manifeste ni migration.
5. **Verrou SQLite : cause F03 CONFIRMÉE et précisée** — j'ai reproduit sur DB fichier + WAL : la
   transaction fuitée **survit au retour de la fonction** et ne tombe qu'au passage du **GC cyclique**.
   **F04 est réel mais n'était PAS le coupable du 18/09** (le worker n'a fait aucune écriture).
6. **Angle mort majeur d'Astra : c'est l'app Android qui re-déclenche le verrou à chaque lancement**
   (`SyncRepository` renvoie une progression vers des IDs supprimés → FK → fuite). Voir §4.
7. **Structure Accueil / Bibliothèque / Téléchargements, catégories ≠ genres : OK**, réalisable
   **entièrement avec les endpoints existants** + 2 tris à ajouter.
8. **Sur-ingénierie à écarter pour l'instant :** manifeste versionné, tables works/series/chapters/pages,
   ancres versionnées, taxonomie N–N, FTS, outbox idempotent, tuiles serveur, refonte `flask.g`.

---

## 1. Crash Android = OOM — **CONFIRMÉ** ; fix **correct**, suffisant avec une nuance

**Preuves relues :**
- `K/ui/reader/ComicReaderFragment.kt:98` `loadPages(): List<ByteArray>` ; `:102` télécharge **tout**
  le CBZ dans `cacheDir` ; `:113-119` `ZipInputStream` + `zip.readBytes()` pour **chaque** entrée ;
  `:125` renvoie tous les tableaux. L'adapter n'est posé qu'en `:75`, après coup.
  → ~695 Mio d'octets retenus avant la première image. Aucun `largeHeap` dans le manifeste (et ce ne
  serait pas un remède).
- `K/ui/reader/ComicPageAdapter.kt:27-29` : `BitmapFactory.decodeByteArray(data, 0, data.size)` dans
  `onBindViewHolder`, thread UI, sans `Options`. `FIT_CENTER` (`:21`) ne réduit pas l'allocation.
- `:121` `catch (e: Exception)` ne capture pas `OutOfMemoryError`.
- Layout : `res/layout/fragment_comic_reader.xml:7` = `ViewPager2` sans orientation → page-flip horizontal.

Réserve d'Astra maintenue : pas de logcat, donc « OOM observé » non prouvé — mais la conception rend
l'ouverture impossible quel que soit le téléphone ; inutile d'attendre un logcat pour corriger.

**Le fix est-il suffisant ?** Références + pages à la demande supprime F01. Pour F02, **le
downsampling seul ne suffit pas** : une planche de 750 × 14 183 réduite pour tenir dans une texture
GPU devient illisible ; et un bitmap > ~100 Mo ou > taille max de texture échoue au dessin. Il faut
donc un affichage **tuilé par régions**. **Nuance importante vs Astra :**

- Astra propose d'écrire le tuilage (fenêtre, budget, ≤ 6 tuiles) et envisage des **tuiles côté
  serveur** « pour le WebP et les codecs sans décodage régional ». Or `BitmapRegionDecoder` d'Android
  gère **JPEG, PNG et WebP**. Les tuiles serveur sont inutiles pour cette archive (832 JPEG + 137 WebP).
- Surtout, ce moteur existe déjà : **`com.davemorrissey.labs:subsampling-scale-image-view`**
  (tuilage + décodage régional + sous-échantillonnage + zoom + recyclage). C'est la brique utilisée
  par les lecteurs de manga Android open-source pour exactement ce cas. Elle charge depuis un
  **fichier/URI** → on met la page en cache disque puis on l'affiche. **Le lot « tuiles + budget
  mémoire » d'Astra se réduit à une dépendance Gradle.**

**CBZ unique gardable ? OUI — CONFIRMÉ.** En ligne : `/api/books/<id>/comic-pages` +
`/comic-page/<n>` existent déjà (`bookhaven.py`, routes `api_comic_pages` / `api_comic_page`) et
servent une image à la fois. Hors-ligne : `java.util.zip.ZipFile` (accès direct via le répertoire
central, entrées `ZIP_STORED`) au lieu de `ZipInputStream`. Aucune conversion, aucun ré-import.

## 2. Pagination à 50 + facettes déduites — **CONFIRMÉ, défaut majeur** (+ 1 conséquence oubliée)

- `K/data/api/ApiService.kt:39-40` : `page = 1`, `perPage = 50` (Astra cite `:43-44` — décalage de
  lignes, fond exact). `K/data/repository/BookRepository.kt:15-29` n'expose ni `page` ni `perPage`.
  `K/ui/library/LibraryViewModel.kt:88-93` ne demande jamais la page 2.
  → Sur **9 513 livres**, l'app n'en parcourt que **50** (triés par titre). Seule la recherche « voit » au-delà.
- `LibraryViewModel.kt:119-123` : catégories/genres/formats = `distinct()` **des 50 livres reçus**.
  `K/ui/library/LibraryFragment.kt:115,137` n'affiche que les chips catégorie. Le serveur a pourtant
  `/api/filters` (facettes globales).
- **Ajout (non relevé par Astra)** : `LibraryViewModel.kt:98` → `cacheLibrary(books)` sur chargement
  non filtré : le **mode hors-ligne ne connaît que ces 50 livres**, et `DownloadRepository.kt:121-127`
  ne garde que id/titre/auteur/format/catégorie.
- F12 confirmé : `LibraryFragment.kt:80` `doAfterTextChanged { vm.loadBooks(...) }` sans debounce ni
  annulation → une réponse lente peut écraser la recherche la plus récente.

Oui, c'est **le** défaut majeur de la bibliothèque Android : l'app donne l'impression d'une
collection de 50 titres.

## 3. Scroll vertical continu — **bonne cible, à AJUSTER (2 temps, sans manifeste)**

- Constat confirmé : Android = `ViewPager2` horizontal, aucun mode webtoon.
- **Constat d'Astra périmé côté web** : il écrit que le web « n'offre pas encore un vrai scroll
  vertical continu » (`templates/index.html:1153`, `:2642`). Depuis le commit `80c400a` (**web
  v2.7.0**), le web a un lecteur continu : détection automatique (1re planche h/l > 2), planches d'un
  chapitre empilées, **chapitres dérivés du préfixe des noms de planches** (`NNNNN_NNN`, préfixe/10 =
  chapitre, 172.5 inclus), liste de 217 chapitres + précédent/suivant, progression = **index global
  de planche**. C'est la démonstration que **le manifeste versionné (P2.1) n'est pas nécessaire** :
  la même convention est lisible côté Android depuis la réponse de `/comic-pages`.
- Cible Android recommandée : `RecyclerView` vertical, **un item = une planche** affichée par
  SubsamplingScaleImageView, hauteur d'item = `largeur_écran × h/l` (dimensions lues par
  `inJustDecodeBounds` sur le fichier en cache ; placeholder avant), `recycle()` dans
  `onViewRecycled`, chargement **par chapitre** comme le web (5-13 planches, ou 1 strip).
- **Budget mémoire d'Astra (fenêtre 2-3 écrans, ≤ 6 tuiles, ~64 Mio)** : raisonnable comme ordre de
  grandeur, mais **sans objet si on adopte la bibliothèque** (elle borne ses tuiles elle-même). Ce
  qui reste à régler à la main : `setItemViewCacheSize` petit, **1 seul chapitre en mémoire**, cache
  disque de pages **borné** (p. ex. 200-300 Mo LRU dans `cacheDir`), annulation des téléchargements
  hors fenêtre.
- **Compatibilité de position** : garder `current_location` = index global de planche (chaîne
  d'entier). Web (`parseInt`) et Android (`position.toIntOrNull()`, `ComicReaderFragment.kt:81`) le
  lisent déjà tous les deux → reprise web ↔ Android gratuite. **Ne pas** introduire l'ancre JSON
  versionnée d'Astra maintenant.
- **Passage auto de chapitre** : bouton « Chapitre suivant » en bas (comme le web) suffit au départ.

## 4. Verrou SQLite — **F03 CONFIRMÉ et précisé ; F04 NUANCÉ ; fix juste (version légère)**

**F03 — preuve code :** `bookhaven.py:1283-1303` (`api_set_progress`) : si l'`INSERT` lève, on saute
`conn.commit()` / `conn.close()` ; l'`except` ne fait ni rollback ni close.

**F03 — preuve expérimentale (la mienne, DB fichier + WAL + `foreign_keys=ON`, hors projet) :**

```text
route (INSERT FK invalide, même forme que api_set_progress) -> "500"
autre écrivain juste après, sans GC      : LOCKED
autre écrivain 3 s plus tard, sans GC    : LOCKED
gc.collect()                              : 17 objets libérés
autre écrivain après le GC cyclique       : OK
```

→ La `sqlite3.Connection` est prise dans un **cycle de références** (son cache de statements) : le
comptage de références **ne la libère pas** au retour de la fonction. Le verrou d'écriture dure
**jusqu'au prochain passage du GC cyclique qui la couvre** — quelques ms si le serveur alloue
beaucoup, **des minutes** sur un serveur quasi inactif ou si l'objet a été promu en génération
ancienne. C'est plus fort que la repro d'Astra (shared-cache mémoire) et ça explique le blocage
« jusqu'au redémarrage » observé deux fois le 18/09.

**Angle mort d'Astra — le déclencheur récurrent est l'app Android :**
- `api_get_progress` répond `{"progress": 0}` en **200** pour un livre inexistant (pas de 404).
- `K/data/repository/SyncRepository.kt:26-42` : à **chaque lancement**, pour **chaque** progression
  locale, si `local.progress > server.progress` → `api.setProgress(local.bookId, …)`. Pour un ID
  supprimé côté serveur (re-scan, déplacement, import/finalize), c'est vrai **à chaque fois** →
  `INSERT` → **FK** → transaction fuitée → base verrouillée. `:41` passe ensuite `pendingSync=false`
  sans vérifier le succès, mais l'étape 2 ne dépend pas de `pendingSync` : **ça recommence au
  lancement suivant**.
- Logs : 10 événements FK (`2026-08-20`, `08-27`, puis 6 le `09-18` à 08:29 / 08:57-08:59), chacun
  suivi de rafales `database is locked` — **les 182 erreurs « locked » tracées sont toutes dans
  `api_set_progress`**. Le défaut préexiste donc au manhua (août).

**F04 — code confirmé, causalité NUANCÉE :** `media_worker.py` : `UPDATE` puis réseau + `sleep(0.5)`,
`commit` seulement tous les 20 (`processed % 20`). Défaut réel… mais les logs disent
`Media worker: 2425 books need online enrichment` → `Enrichment complete: 0 covers, 0 descriptions`.
**Zéro UPDATE = zéro transaction ouverte = aucun verrou tenu par le worker le 18/09.** F04 est
**latent** (il mordra le jour où l'enrichissement trouvera quelque chose). À corriger car c'est
2 lignes (commit juste après chaque UPDATE), mais ce n'est pas « la cause ».
⚠️ À vérifier séparément : 0 résultat sur 2 425 livres en 6 h suggère que l'enrichissement en ligne
est **inopérant** (réseau ? garde SSRF `_is_safe_url` trop stricte avec le DNS du VPN ?).

**Le fix d'Astra est juste** (transactions courtes, rollback/close garantis, WAL déjà là, **pas de
pool**). **Version minimale recommandée**, sans refonte `flask.g`/teardown :
1. `api_set_progress` : vérifier que le livre existe → **404** ; `with closing(get_db()) as conn, conn:`.
2. `api_get_progress` : **404** si le livre n'existe pas (pour que l'app puisse purger).
3. Un petit context manager `db()` (closing + transaction) appliqué aux **routes d'écriture**
   (progress set/delete, genre, series, category-order, upload confirm, epub-locations).
4. `media_worker` : `commit()` immédiatement après chaque `UPDATE`.
5. Android `SyncRepository` : sur 404 → **supprimer la ligne locale** ; ne passer
   `pendingSync=false` **que si** l'appel a réussi.

Le balayage scanner/imports (F10) et l'observabilité fine : P1, pas P0.

## 5. Structure de refonte — **OK, avec nuances de périmètre**

- **Accueil / Bibliothèque / Téléchargements** : bon découpage. État actuel : `bottom_nav_menu.xml` =
  Bibliothèque / Hors ligne / Réglages. « Hors ligne » → « Téléchargements », Réglages → icône de barre.
- **Accueil réalisable sans nouveau backend** : `/api/continue-reading` (Reprendre + En cours),
  `/api/books/recent` et `/api/books/recent-by-category` (Récemment ajoutés), `/api/filters`
  (raccourcis catégories). « Nouveaux chapitres des séries suivies » = **hors P0** (pas de notion de suivi).
- **Catégories vs genres distincts : CONFIRMÉ utile** (catégorie = rayon de bibliothèque ; genre =
  étiquette multi-valuée). Côté Android : deux rangées de chips / une feuille de filtres alimentée par
  `/api/filters`. La proposition « type de contenu BD/Comics/Manga/Manhwa/Manhua » est pertinente mais
  = nouvelle colonne + UI d'édition → **P2**.
- **Contrats de tri §6.3 : BONS.** Preuve du problème : `bookhaven.py` `sort_map["recent"] =
  "modified_at DESC"` alors que « récents » web = `added_at`. À ajouter côté serveur, **sans casser
  `recent`** : `added_desc` (`added_at DESC, id DESC`) et `last_read_desc` (jointure
  `reading_progress` du profil, jamais-lus en fin). C'est ~15 lignes.
- « filtrage → regroupement → tri → pagination » : juste sur le principe (`LIMIT` avant
  `_group_format_variants` dans `/api/books`), mais l'effet réel est **mineur** (une page peut avoir
  49 cartes). **Ne pas bloquer P0 dessus.**
- **Identité œuvre/série indépendante des fichiers + manifeste versionné : REJETÉ pour l'instant**
  (voir §7). `books.series` / `collection_path` + `/api/books/grouped` couvrent déjà « une carte par
  série » ; le manhua est un seul livre ; les chapitres se dérivent des noms.
- **Nuance « mono-utilisateur » :** le serveur a **5 profils** (usage familial). La clé de progression
  Room = `bookId` seul (`K/data/db/entity/ReadingProgress.kt:9`) mélange les profils sur un appareil
  partagé. Correctif léger (ajouter `userId` à la clé) → **P1**, pas l'usine
  `(server_id, user_id, work_id)` + révisions + outbox d'Astra.

## 6. Cohérence `/api/books` (Android) vs `/api/books/grouped` (web) — **À unifier, en P1**

Confirmé : Android liste des **fichiers** à plat ; le web liste des **collections + livres**
(hiérarchie `collection_path`, pagination par unité visible, SQL optimisé et testé). Avec 6 588
comics, la liste à plat n'est pas une bonne bibliothèque même paginée. **Décision :**
- **P0** : pagination infinie sur `/api/books` + tris explicites → l'app voit enfin toute la collection.
- **P1** : Bibliothèque Android branchée sur `/api/books/grouped` (cartes collection → navigation par
  `prefix`), pour la même organisation que le web. `grouped` n'a pas de paramètre `sort` aujourd'hui :
  l'ajouter à ce moment-là.

## 7. Verdict sur le plan P0 → P3 d'Astra

| Lot Astra | Verdict | Commentaire |
|---|---|---|
| P0.1 SQLite (routes + worker + import + scan) | **NUANCÉ** | Juste, mais trop large pour un P0 : faire la version légère du §4 (routes d'écriture + worker + **SyncRepository**, qu'Astra place en P1.2 alors que c'est le déclencheur). |
| P0.2 Lecteur à références + décodage borné + page haute | **CONFIRMÉ**, simplifié | Remplacer « tuilage maison » par SubsamplingScaleImageView. M, pas M–L. |
| P0.3 Confirmation téléphone + instrumentation | **NUANCÉ** | Un `adb logcat` quand le téléphone est branché : oui. Profils heap/native/graphique : non bloquant. |
| P1.1 Pagination/facettes/tris | **CONFIRMÉ → remonté en P0** | C'est le défaut n°2 visible ; petit côté serveur. |
| P1.2 Reprise/synchro (outbox, ordre d'événements, clés serveur/profil) | **NUANCÉ** | Garder 2 correctifs (404 → purge ; `pendingSync` seulement si succès ; clé par profil). Écarter outbox idempotent / révisions. |
| P1.3 Accueil/Bibliothèque/fiche série | **CONFIRMÉ → Accueil remonté en P0** | Faisable avec les endpoints existants. Fiche série en P1 (avec `grouped`). |
| P2.1 Manifeste versionné + chapitres logiques + migration des positions | **REJETÉ (sur-ingénierie)** | Le web v2.7.0 prouve que le préfixe des noms suffit. À reconsidérer seulement si un 2ᵉ import n'a pas cette convention. |
| P2.2 Scroll vertical virtualisé Android **et web** | **CONFIRMÉ pour Android** ; web **déjà fait** | Ne dépend pas de P2.1. |
| P2.3 Téléchargements ciblés par chapitre/série | **NUANCÉ** | Sans chapitres physiques, le ciblage par chapitre n'a pas d'objet. Garder : cache de pages borné + téléchargement du CBZ entier. |
| P3 Normalisation œuvres/genres N–N, collections perso, FTS | **REJETÉ pour l'instant** | 9 513 lignes : `LIKE` + index suffisent ; aucune douleur utilisateur exprimée. |

Autres findings d'Astra : **F06, F07, F08, F09, F11, F12, F13 confirmés** à la lecture. F09 (ne pas
rejouer `finalize_manhua_single.py`, il supprime des IDs et cascade les progressions) : à retenir
comme règle. F11 (CBR local illisible) : message d'erreur explicite en P1.

## 8. Angles morts d'Astra (récapitulatif)

1. **Durée réelle du verrou F03** : cycle de références → GC cyclique (prouvé §4).
2. **L'app Android re-déclenche le verrou à chaque lancement** (`SyncRepository` + `get_progress` en 200).
3. **F04 innocent le 18/09** (0 écriture du worker) ; **enrichissement en ligne probablement inopérant**.
4. **État web périmé** : lecteur continu + chapitres par noms déjà livrés (v2.7.0) → le manifeste tombe.
5. **Bibliothèque de tuilage existante** + `BitmapRegionDecoder` gère WebP → ni moteur maison ni tuiles serveur.
6. **Snapshot hors-ligne plafonné à 50** (conséquence de F05).
7. **5 profils** : pas strictement mono-utilisateur → clé de progression locale par profil (léger).
8. Perf serveur non mesurée : `api_comic_page` reliste l'archive à chaque page. Le ZIP est `STORED`
   (répertoire central seulement) → probablement négligeable ; si besoin, mini-cache `(path, mtime) →
   liste` en P1. Ne pas sur-investir avant mesure.

---

## 9. PLAN D'ACTION CONSOLIDÉ — minimal d'abord (pour Opus 4.8)

Règles : un lot = un commit ; bump + CHANGELOG (web : `__version__` ; Android : `versionCode`+1) ;
**tout test d'exécution sur l'instance démo isolée** (worktree séparé, jamais `data/` live) ;
injections de panne SQLite **uniquement** sur DB de test.

### P0 — « le manhua s'ouvre, l'app voit toute la bibliothèque, la refonte est visible »

| Lot | Cible | Contenu | Fichiers | Critère de vérif |
|---|---|---|---|---|
| **P0-A** Verrou (S) | **Flask** + Android | `api_set_progress` : existence → 404, `closing` + transaction ; `api_get_progress` : 404 si livre absent ; context manager `db()` sur les routes d'écriture ; `media_worker` : commit après chaque UPDATE. **Android :** `SyncRepository` purge la ligne locale sur 404, `pendingSync=false` seulement si succès. | `bookhaven.py`, `database.py`, `media_worker.py` ; `K/data/repository/SyncRepository.kt` | Test pytest : progression vers ID supprimé → 404 **puis** écriture concurrente OK sans `gc.collect()`. Émulateur : progression locale sur ID inexistant → 1 seul appel, ligne purgée, aucun `locked` dans les logs. **Redémarrage Flask requis.** |
| **P0-B** Crash lecteur (M) | **Android** | Lecteur par **références** : en ligne `GET comic-pages` + `comic-page/{n}` (à ajouter dans `ApiService`) → fichier en cache disque borné (LRU) ; hors-ligne `ZipFile` à la demande. Affichage par **SubsamplingScaleImageView**. Supprimer `List<ByteArray>` et `decodeByteArray`. Garder ViewPager2 à ce stade. | `K/ui/reader/ComicReaderFragment.kt`, `ComicPageAdapter.kt`, `K/data/api/ApiService.kt`, `android/gradle/libs.versions.toml`, `android/app/build.gradle.kts` | Émulateur + **CBZ réel de 729 Mo** (copie dans la bibliothèque démo) : ouverture < qq s, 1re planche nette ; saut vers le chapitre 210 (planches 1 360 × 15 104) OK ; 100 pages d'affilée → `dumpsys meminfo` en **plateau** ; logcat sans OOM. En ligne **et** hors-ligne. |
| **P0-C** Pagination + tris + facettes (M) | **Flask** (petit) + Android | Serveur : tris `added_desc`, `last_read_desc` (garder `recent`). Android : pagination infinie (`page`/`perPage` exposés, chargement en fin de liste, total affiché), facettes via `/api/filters`, sélecteur de tri (**Récemment ajoutés** défaut / **Récemment lus** / Titre / Auteur), recherche debounce 300 ms + annulation du job précédent, snapshot hors-ligne cumulatif. | `bookhaven.py` ; `K/data/api/ApiService.kt`, `K/data/repository/BookRepository.kt`, `K/ui/library/LibraryViewModel.kt`, `LibraryFragment.kt`, `K/data/repository/DownloadRepository.kt` | Défilement au-delà de 50 jusqu'au `total` ; chips = toutes les catégories même sous filtre ; frappe rapide → dernier terme gagne ; tests pytest des 2 tris (dates égales → ordre stable par id). |
| **P0-D** Refonte visible (M) | **Android** | Nav basse **Accueil / Bibliothèque / Téléchargements** ; Accueil = grande carte **Reprendre** + rail En cours + rail Récemment ajoutés + raccourcis Catégories ; Bibliothèque = **catégories et genres en filtres distincts** + tri visible ; Réglages dans la barre. Endpoints existants uniquement. | `res/menu/bottom_nav_menu.xml`, `res/navigation/nav_graph.xml`, nouveau `K/ui/home/*`, `K/ui/library/*`, layouts associés | Parcours émulateur : lancer → Reprendre ouvre le bon livre à la bonne page ; filtre catégorie + genre combinés ; retour du lecteur conserve la position de liste. Captures avec livres du domaine public. |

### P1 — renforcements (après P0)

- **P1-A Scroll vertical webtoon Android** : RecyclerView vertical + détection h/l > 2 + chapitres
  dérivés des noms (même convention que le web) + « Chapitre suivant » ; position = index global
  (compat web). Fichiers : `K/ui/reader/*`, `fragment_comic_reader.xml`.
- **P1-B Bibliothèque sur `/api/books/grouped`** (+ `sort`) et **fiche série/collection**.
- **P1-C Progression par profil** dans Room (clé `userId + bookId`, migration Room) ; remplacer « le
  plus grand pourcentage gagne » par « le plus récent gagne » **si** l'API expose `last_read` (elle le fait).
- **P1-D Hygiène SQLite étendue** : scanner, upload, imports (`F10`) avec le même `db()` ; log durée de transaction.
- **P1-E** Erreur explicite pour CBR local (F11) ; rendu PDF asynchrone ; vérifier pourquoi
  l'enrichissement en ligne renvoie 0 résultat.

### Écarté (sur-ingénierie à ce stade)

Manifeste versionné et ancres `{version, chapitre_id, page_id, fraction}` ; tables
`works/series/chapters/pages` ; taxonomie genres N–N et collections personnelles ; FTS ; outbox
idempotent et révisions serveur ; tuiles/rendus côté serveur ; moteur de tuiles maison ; connexion
`flask.g` + teardown généralisé ; pool de connexions ; téléchargement ciblé par chapitre.
**Condition de réouverture** : un second contenu à chapitres sans convention de nommage, ou un besoin
utilisateur exprimé (collections perso, suivi de séries).

---

*Rapport seul fichier écrit. Aucun code, version, DB ni serveur touché. Non committé (laisser le
chef décider de le versionner avec le rapport d'Astra).*
