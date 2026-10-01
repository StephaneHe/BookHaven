# Analyse crash Android + refonte BookHaven — OpenAI GPT-6 Astra — 2026-09-18

## 1. Décisions et niveau de certitude

**Le défaut Android principal est établi : le lecteur conserve toutes les images encodées du CBZ en RAM avant d'afficher la première page.** Sur l'archive actuelle, cela représente **695,37 Mio de tableaux d'octets**, auxquels s'ajoutent les allocations temporaires et les bitmaps. Une page peut demander **78,36 Mio** supplémentaires en ARGB_8888. L'OOM par volume est donc l'explication dominante du crash rapporté ; **l'exception exacte du téléphone n'est pas confirmée**, faute d'appareil ADB connecté et de logcat disponible. Ne pas transformer cette limite en faux diagnostic « OOM observé ».

**Le CBZ fusionné n'est pas intrinsèquement incompatible avec Android.** Il est incompatible avec le chargement intégral actuel. Le correctif immédiat doit lire les pages à la demande, depuis les routes Flask existantes ou un `ZipFile` local, avec décodage borné. La cible durable est **une seule fiche de série, des chapitres logiques ordonnés et un lecteur continu virtualisé** ; les chapitres peuvent référencer des plages de l'archive existante. Il n'est pas nécessaire de réimporter 217 livres visibles ni de reconstruire immédiatement les fichiers.

**Le verrou SQLite dispose d'un chemin causal documenté :** écriture de progression vers un livre supprimé → violation de clé étrangère → branche d'erreur sans rollback/fermeture → transaction susceptible de rester ouverte et de bloquer les autres écritures. Les logs du 18 septembre montrent cette succession. Un autre défaut indépendant retient le verrou d'écriture pendant l'enrichissement réseau. WAL et des timeouts sont **déjà présents** ; les ajouter ne constitue pas le correctif.

Périmètre respecté : analyse du dépôt, des logs, de l'archive et d'un instantané SQLite en mémoire. Aucun serveur démarré/redémarré, aucun import exécuté, aucun appel aux routes applicatives, aucun build, aucun changement de code, bibliothèque ou DB. Seul fichier créé : ce rapport. Aucun commit ni bump de version. Le callback au projet chef est l'action externe expressément demandée.

## 2. Mesures et méthode reproductible

### Archive réellement présente

Fichier : `H:\Books\Comics\Sir, Don't Show Off.cbz`, dernière modification observée le 18 septembre 2026 à 09:14:05, heure affichée par Windows.

| Mesure | Résultat |
|---|---:|
| Taille du CBZ | 729 242 884 octets, soit 729,24 Mo / 695,46 Mio |
| Images / chapitres identifiables par préfixe | **969 / 217** |
| Somme des tailles des entrées image | **729 143 750 octets / 695,37 Mio** |
| Méthode ZIP | 969 entrées `ZIP_STORED` ; pas de décompression ZIP coûteuse |
| Formats d'image | 832 JPEG, 137 WebP |
| Première image | `00010_001.jpg`, 800 × 5 360, ~16,36 Mio en RGBA |
| Deuxième / troisième image | 800 × 6 290 / 800 × 7 000 ; ~19,20 / 21,36 Mio |
| Plus grandes images | `02100_001.jpg` et `02100_002.jpg`, 1 360 × 15 104 ; ~78,36 Mio chacune |
| Plus grosse entrée encodée | `01640_001.webp`, 4 211 850 octets, 750 × 14 756 |
| Contrôles | 969 en-têtes lisibles ; 969 décodages Pillow complets et CRC ZIP valides ; aucune erreur |

Mesures effectuées par Python `-B`, `zipfile` et Pillow, une image à la fois, sans extraction sur disque. Le passage complet a pris 61,22 s sur cette machine : ce n'est **pas** un benchmark Android. Les tailles RGBA sont calculées par `largeur × hauteur × 4`, pas mesurées dans le processus Android.

Les **~1 045 pages** du contexte correspondent à un état antérieur : le fichier principal SQLite, lu sans son WAL, contient encore 1 045 pages / 735 594 839 octets. L'état incluant les transactions validées du WAL contient **969 pages / 729 242 884 octets**, cohérent avec le disque. Le script de fusion filtre les publicités (`scripts/combine_manhua_cbz.py:75`) ; cela explique plausiblement l'évolution, sans inventer l'historique précis de chaque page supprimée.

### Base et limites de collecte

- Base configurée : **`I:\Dev\BookHaven\data\bookhaven.db`**, et non le fichier homonyme vide à la racine (`config.py:33`, `bookhaven.log:1320`). Taille observée : 22 528 000 octets ; WAL : 173 072 octets.
- Première lecture `mode=ro&immutable=1` : état du fichier principal seulement, volontairement sans interaction avec WAL/SHM. **Cet état n'est pas utilisé comme vérité courante.**
- Pour inclure le WAL sans écrire dans le SHM : double lecture stable des octets DB/WAL ; reconstruction uniquement en RAM des 42 frames jusqu'au dernier commit, contrôle des tailles et sels de frames ; adaptation en RAM des octets de mode journal pour `sqlite3.deserialize`. `PRAGMA integrity_check` sur cette copie en mémoire : `ok`. Il s'agit d'un contrôle ponctuel, pas d'une procédure de sauvegarde à réutiliser en production ; le script d'audit n'a pas implémenté la validation des checksums WAL.
- État ainsi observé : **9 513 livres**, dont 6 588 Comics et 2 925 Books ; **6 948 genres vides** (~73 %). Manhua : ID **39572**, `genre='Comics'`, `series=''`, `collection_path=''`, `page_count=969`, `added_at=2026-09-18 05:46:14`, `modified_at=2026-09-18 06:18:01` (valeurs brutes SQLite).
- `adb devices -l` : liste vide. Aucun `OutOfMemory`, `FATAL EXCEPTION` ou `ComicReaderFragment` dans les logs serveur courants examinés. Des logs Flask ne remplacent pas logcat. Version du code Android : `versionCode=55`, `versionName=1.5.1` (`android/app/build.gradle.kts:16`). Version réellement installée inconnue.
- Aucun sous-agent utilisé. Aucun test du projet exécuté, pour éviter écritures de caches, bases et artefacts ; les vérifications spécifiques ci-dessus et la reproduction SQLite ci-dessous s'exécutent en mémoire.

## 3. Findings priorisés et preuves

Convention pour alléger les références : **K = `android/app/src/main/kotlin/com/bookhaven/android/`**. Ainsi `K/ui/reader/ComicReaderFragment.kt:117` désigne exactement ce fichier dans le dépôt. Les numéros sont ceux du code présent lors de l'analyse.

| ID | Priorité | Finding et preuve | Conséquence / décision |
|---|---|---|---|
| F01 | **BLOCKER** | `K/ui/reader/ComicReaderFragment.kt:98`, `:111`, `:117`, `:125` : `List<ByteArray>`, `zip.readBytes()` pour chaque entrée, tri puis retour de tous les tableaux. L'adapter n'est attaché qu'en `:75`, après `loadPages` (`:67`). | Au moins 695,37 Mio retenus avant affichage. Remplacer par des références de pages et accès à la demande. OOM extrêmement plausible, non confirmé par logcat. |
| F02 | **BLOCKER** | `K/ui/reader/ComicPageAdapter.kt:27` et `:29` : `BitmapFactory.decodeByteArray` dans `onBindViewHolder`, sans options ni travail asynchrone. | Gros bitmaps sur le thread UI, sans downsampling. Corriger **avec** F01 ; une seule page haute reste dangereuse. |
| F03 | **BLOCKER** | `bookhaven.py:1289` à `:1303` : l'échec de l'INSERT saute `commit/close` ; le `except` ne libère rien. `bookhaven.log:1207`, `:1221`, `:1283`, `:1289` : FK puis verrous. | Transaction non terminée après erreur. Rollback garanti, close garanti et traitement des IDs supprimés. |
| F04 | **MAJOR** | `media_worker.py:612`, `:618`, `:648`, `:651`, `:658`, `:662` : commit toutes les 50 extractions / 20 recherches ; réseau et sleep entre deux commits. Fermeture seulement en `:665`. | Après un premier UPDATE, verrou conservé durant les opérations suivantes ; contention même sans exception. Séparer préparation lente et transaction courte. |
| F05 | **MAJOR** | `K/data/api/ApiService.kt:43` et `:44` : défaut page 1 / 50 ; `K/data/repository/BookRepository.kt:16` à `:30` n'expose pas la pagination ; `K/ui/library/LibraryViewModel.kt:88` ne consomme pas les pages suivantes. | Bibliothèque Android limitée à la première tranche de 50 lignes, parfois moins de cartes après regroupement de formats. La recherche peut trouver au-delà, mais la navigation complète manque. |
| F06 | **MAJOR** | `bookhaven.py:645` : `recent = modified_at DESC` ; `:1979` : récents par `added_at` ; `:1317` : reprise par `last_read` ; `:1918` : bibliothèque groupée alphabétique. | Trois sens de « récent » non unifiés. Séparer explicitement récemment lu, ajouté et modifié ; tri commun web/Android. |
| F07 | **MAJOR** | `K/ui/library/LibraryViewModel.kt:119` à `:123` déduit les facettes de la réponse courante ; `K/ui/library/LibraryFragment.kt:115`, `:137` n'affiche que les chips catégorie. | Facettes incomplètes et rétrécissant avec le filtre ; genres calculés mais non proposés dans cet écran. Utiliser les facettes serveur et dissocier catégories/genres. |
| F08 | **MAJOR** | `K/data/repository/SyncRepository.kt:29`, `:37` : pourcentage maximal gagnant ; `:38` à `:41` peut effacer `pendingSync` malgré échec réseau. `K/data/db/entity/ReadingProgress.kt:9` : clé = bookId seul. | Relecture en arrière écrasée ; synchronisation fragile ; progression locale non isolée par profil/serveur. À traiter avant une reprise de lecture refondue. |
| F09 | **MAJOR** | `scripts/finalize_manhua_single.py:63` supprime les lignes de chapitres ; `database.py:49` cascade les progressions ; `:94` du script supprime le dossier. Le livre fusionné est inséré sans série (`:70`). | Chapitres et positions perdent leur identité. Ne pas rejouer cet import pour construire la refonte ; introduire un manifeste et une migration de positions. |
| F10 | **MAJOR** | `scripts/import_manhua_to_db.py:73`, `scanner.py:142`, `bookhaven.py:2517` : erreurs sans rollback/close garanti. `scripts/finalize_manhua_single.py:75` ne traite que `OperationalError`. | Le correctif DB doit couvrir routes, scan, workers et imports, pas seulement la route qui a laissé des traces. |
| F11 | **MAJOR** | `K/ui/reader/ReaderActivity.kt:46` envoie CBZ **et CBR** au même fragment, lequel ne lit que ZIP (`ComicReaderFragment.kt:113`). | Un vrai RAR/CBR reste illisible en local. L'API serveur sait essayer ZIP puis RAR (`bookhaven.py:1582`). Prévoir une capacité distincte et une erreur explicite. |
| F12 | **MINOR** | `K/ui/library/LibraryFragment.kt:80` lance une recherche à chaque frappe ; `LibraryViewModel.kt:83` lance des jobs concurrents sans annulation. | Réponses anciennes pouvant écraser la recherche récente. Debounce et annulation/identifiant de requête. |
| F13 | **MINOR** | `K/ui/reader/ComicReaderFragment.kt:101`, `:102`, `:128` : téléchargement complet dans le cache à chaque ouverture distante, sans politique dédiée de réutilisation/éviction ni indicateur de chargement dans le layout. | Attente et consommation disque importantes ; distinguer cache de lecture et téléchargement hors ligne. |

## 4. A — Anatomie du crash Android

### Chemin d'ouverture

1. `LibraryFragment.kt:152` ouvre `ReaderActivity` et transmet le fichier local s'il est téléchargé.
2. `ReaderActivity.kt:46` sélectionne `ComicReaderFragment`.
3. Sans chemin local, le fragment télécharge **tout** le CBZ dans `cacheDir/comic_<id>.cbz` (`:99` à `:103`). Retrofit a bien `@Streaming` (`K/data/api/ApiService.kt:67`) : le transfert HTTP n'est donc pas, dans ce code, une copie intégrale préalable en RAM.
4. `ZipInputStream` parcourt chaque entrée et `readBytes()` crée son tableau complet. Tous ces tableaux restent référencés dans `pages`. `sortedBy/map` duplique des listes/références, **pas tous les octets d'image une deuxième fois** ; `readBytes()` peut néanmoins créer des buffers temporaires et des copies pendant une lecture.
5. Le fragment attend la fin de ce parcours avant l'affichage. Son adapter garde la liste complète (`ComicPageAdapter.kt:8`). RecyclerView/ViewPager2 recycle les **vues**, pas cette collection de données.
6. `onBindViewHolder` décode en taille native, synchroniquement. `FIT_CENTER` (`:21`) réduit le rendu dans la vue, **pas l'allocation du bitmap**.

Le layout utilise **ViewPager2**, sans orientation verticale spécifiée (`android/app/src/main/res/layout/fragment_comic_reader.xml:7`) : lecture paginée horizontale par défaut. Aucun scroll webtoon continu n'est implémenté. Le code ne fixe ni fenêtre de données, ni budget d'images, ni `offscreenPageLimit`. Le nombre exact de vues/bitmaps vivants dépend du recyclage et de la prélecture du composant : impossible de le donner sans mesure. En revanche, le nombre de tableaux d'images conservés est bien **969**.

Coil 2.6.0 existe (`android/gradle/libs.versions.toml:16`) et les couvertures utilisent un ImageLoader authentifié avec un cache **disque** de 64 Mio (`K/BookHavenApp.kt:54` à `:63`). **Le lecteur comic n'utilise pas Coil** ; ce cache ne protège donc pas les pages. Pas de stratégie spécifique de libération des bitmaps au recyclage ni de réaction à la pression mémoire dans ce lecteur. `onDestroyView` ne fait que vider le binding ; cela ne démontre pas à lui seul une fuite permanente, mais le nettoyage doit être explicite dans le nouveau lecteur.

### Arbitrage des hypothèses

| Hypothèse | Conclusion |
|---|---|
| OOM dû au volume total | **Très fortement étayé** : 695,37 Mio de payload retenu, avant bitmaps. Un heap autorisé de 256 ou 512 Mio ne peut pas contenir cette collection ; limite réelle de l'appareil inconnue. Échec possible pendant `readBytes()` avant toute page affichée. |
| OOM / rendu impossible sur une page géante | **Risque indépendant établi par dimensions et code**, même après suppression de la liste globale. Première page déjà ~16 Mio ; certaines ~78 Mio, dimensions susceptibles aussi de dépasser les limites de rendu du matériel. Exception précise non observée. |
| Page précise corrompue / codec Android | **Aucun indice de corruption** : tous les CRC et décodages Pillow passent. Cela ne valide pas les décodeurs Android de chaque appareil ; conserver cette piste seulement si logcat identifie un codec/une entrée. |
| Parsing bloquant le thread UI | **Pas l'explication première** : téléchargement et parcours ZIP s'exécutent dans `Dispatchers.IO` (`ComicReaderFragment.kt:67`, `:98`). Le lecteur reste néanmoins vide jusqu'à la fin. Décodage bitmap, lui, exécuté sur UI ; saccades/ANR possibles. |

`catch (Exception)` (`ComicReaderFragment.kt:121`) ne capture pas `OutOfMemoryError`, qui est un `Error`. Le décodage de l'adapter n'a pas non plus de garde. Ajouter un catch OOM ou `largeHeap` ne résout pas la conception ; la priorité est d'éviter ces allocations.

### Confirmation appareil à demander à l'implémentation, pas obtenue ici

Capturer sans effacer les logs : `adb logcat -d -v threadtime`, vérifier la version installée via `adb shell dumpsys package com.bookhaven.android`, puis reproduire en ligne et avec copie locale. Relever le nom de l'exception, la pile, les octets demandés, la limite de heap, la page et la version du contenu. Mesurer aussi `adb shell dumpsys meminfo com.bookhaven.android` et la mémoire native/graphique, pas uniquement le heap Java. Une pile dans `readBytes` confirme le volume ; dans `decodeByteArray` ou le rendu, elle précise l'effet des grandes pages ; un ANR exige sa propre trace. L'absence de logcat interdit de nommer une exception effectivement observée.

## 5. C — Scroll continu de tous les chapitres sans crash

### Architecture recommandée

**Une série affichée une seule fois → manifeste ordonné → pages ou tuiles virtuelles → source distante ou locale.** La fusion physique et l'expérience de lecture sont deux décisions indépendantes.

| Option | Verdict |
|---|---|
| CBZ unique + liste actuelle de tous les octets | **KO** sur Android pour ce volume. Réduire seulement les vues adjacentes ne suffit pas. |
| CBZ unique + manifeste léger + accès page par page + tuilage | **OK en principe**, sous budget mémoire vérifié. Solution de compatibilité immédiate ; le téléchargement intégral reste nécessaire pour l'offline ZIP local. |
| Chapitres séparés + une fiche série + lecteur virtualisé traversant les chapitres | **Cible recommandée** pour téléchargements, mises à jour et reprise. Toujours tuiler les images hautes : séparer les chapitres ne corrige pas F02. |
| Tous les `<img loading="lazy">` dans une immense page web | Insuffisant comme garantie mémoire : les images déjà vues peuvent rester décodées. Virtualiser et évincer réellement les éléments/images hors fenêtre. |

**Étape immédiate :** réutiliser `/api/books/<id>/comic-pages` et `/comic-page/<n>` (`bookhaven.py:1513`, `:1532`). Android conserve les noms/indices, demande l'image visible et une petite avance. Pour l'offline, indexer le répertoire central d'un `ZipFile` et ouvrir seulement l'entrée demandée ; ne pas rescanner avec `ZipInputStream` depuis le début à chaque page. Fermer chaque stream et le conteneur selon leur cycle de vie. Le CBZ actuel est directement exploitable, sans conversion ni écriture dans `H:\Books`.

**Pour les pages webtoon hautes, fenêtre en octets ET en surface affichée :**

1. Déterminer dimensions/ratio avant décodage. Adapter la résolution à la largeur physique utile, sans agrandissement inutile ; borner aussi hauteur et pixels, car une largeur raisonnable peut cacher 15 000 pixels de hauteur. Le downsampling doit précéder l'allocation, pas suivre un décodage géant. Voir la [documentation Android sur les grands bitmaps](https://developer.android.com/topic/performance/graphics/load-bitmap).
2. Découper les longues images en tuiles verticales indépendantes, par exemple largeur utile jusqu'à 1 024 px × hauteur maximale 2 048 px. Une tuile RGBA à cette taille représente 8 Mio. Pour le WebP et les codecs sans décodage régional adapté, proposer des tuiles dérivées côté serveur ou préparer un cache local de manière bornée ; **décoder d'abord toute l'image sur Android pour la découper réintroduirait F02**.
3. Point de départ à mesurer : fenêtre d'environ 2 à 3 écrans, plafond de 6 tuiles décodées **au total** (visibles, voisines et cache), 1 décodage simultané sur petit appareil, jusqu'à 2 après mesure. Budget images initial `min(64 Mio, environ 25 % du heap autorisé)`, réservant les buffers en cours ; réduire dimensions/fenêtre si nécessaire. Six tuiles de 8 Mio + deux buffers de 8 Mio consomment déjà 64 Mio, avant les autres coûts. Ce sont des valeurs de départ, pas une garantie universelle.
4. RecyclerView vertical à éléments de hauteur connue, IDs stables, placeholders conservant le ratio ; recycler/libérer les ressources hors fenêtre, annuler les demandes obsolètes, limiter prélecture et cache partagé. Ne jamais imbriquer la liste dans un conteneur mesurant toute sa hauteur. Zoom via tuiles plus précises à la demande.
5. Téléchargements et décodages hors UI ; recyclage, départ de l'écran et `onTrimMemory` doivent annuler/évincer. Réutiliser le client HTTP authentifié ; distinguer cache LRU de lecture et fichiers explicitement conservés hors ligne. Les budgets doivent inclure couvertures, pages et allocations de travail.

**Côté Flask :** l'API actuelle lit une seule image encodée (`bookhaven.py:1573`) et ne redimensionne pas. Chaque demande reliste puis rouvre l'archive (`:1560`, `:1569`). Ajouter progressivement un manifeste caché, lié à une version de contenu, et des rendus/tuiles bornés, avec dimensions, ordre, MIME, limites de taille et quotas. Borner aussi les conversions concurrentes côté serveur ; déplacer la consommation mémoire d'Android vers huit workers décodant chacun une grande image serait un autre défaut. Les paramètres de pages doivent rester des identifiants validés, jamais des chemins libres.

### Chapitres et position de lecture

- Manifeste cible : identifiant série/œuvre, version du contenu, chapitres `{id, label, ordre}`, pages `{id, chapitre, entrée ou fichier source, dimensions, ordre}` et tuiles éventuelles. Les 217 préfixes de l'archive permettent une première table de correspondance ; le chapitre **172.5** doit rester correctement ordonné.
- Le même flux traverse la frontière de chapitre sans retour à la bibliothèque. Précharger seulement le début du suivant, afficher un repère de chapitre discret ; retour arrière symétrique. Les chapitres non téléchargés donnent un état récupérable, pas un crash.
- Sauvegarder une ancre logique `{version, chapitre_id, page_id, fraction_verticale}`. Convertir l'ancien index global grâce au manifeste ; ne pas conserver uniquement une position pixel, instable après rotation, zoom et redécoupage.
- Compatibilité : conserver l'index numérique actuel pour anciens clients jusqu'au déploiement conjoint web/Android, puis introduire une représentation versionnée. Un objet JSON introduit brutalement dans `current_location` casserait `toIntOrNull()` et `parseInt()` existants.
- Préserver la correspondance lors de la suppression de publicités ou du découpage d'archives ; choisir la page restante la plus proche si la page d'origine a disparu. Le manifeste courant et l'ancien doivent être identifiables.
- Ne pas supprimer/recréer les livres pour cette migration : cela efface progression et références, et déclenche précisément le problème d'IDs orphelins observé.

**Web actuel :** il affiche une seule balise image (`templates/index.html:1153`) et change son URL (`:2642`). Il lit une archive continue page par page ; il n'offre pas encore un vrai scroll vertical continu. La refonte web doit partager le manifeste et les ancres, avec une fenêtre DOM limitée et des espaces réservés calculés.

## 6. B — Refonte Android et cohérence web

### Existant à préserver et manques

Android : navigation basse **Bibliothèque / Hors ligne / Réglages** (`android/app/src/main/res/menu/bottom_nav_menu.xml:4`), recherche, grille fixe trois colonnes (`K/ui/library/LibraryFragment.kt:77`), chips de catégorie, bandeau de reprise, détails au menu contextuel, upload. Modèle Kotlin déjà doté de `category`, `genre`, `series`, `seriesIndex`, `addedAt`, `lastRead` (`K/data/api/model/Book.kt:13`). Plusieurs briques sont présentes ; les contrats et les écrans ne les exploitent pas complètement.

Web : reprise, rangées récentes par catégorie réordonnables, filtres genre/auteur/format, collections hiérarchiques, détails et édition de métadonnées (`templates/index.html:958`, `:1479`, `:1569`, `:1816`). Il appelle `/api/books/grouped` (`:1670`), Android `/api/books`. Ce décalage explique des organisations différentes d'une même bibliothèque. Préserver les optimisations du regroupement SQL (`bookhaven.py:1884`) et leurs tests de parité ; ne pas revenir au chargement de toutes les fiches.

Lecteurs : EPUB en WebView/epub.js avec CFI et synchronisation (`K/ui/reader/EpubReaderFragment.kt:105`, `:221`) ; PDF déjà en RecyclerView, mais rendu synchrone dans `onBindViewHolder` (`K/ui/reader/PdfReaderFragment.kt:153`) ; comics en pager sans zoom/scroll webtoon dédiés. La refonte partage la navigation, les préférences et la reprise, tout en conservant les moteurs adaptés aux formats.

### Structure cible

Navigation principale Android : **Accueil / Bibliothèque / Téléchargements**, avec recherche globale et accès Profil/Réglages dans la barre supérieure. Le web expose les mêmes destinations dans sa barre latérale et sa navigation mobile.

| Écran | Contenu et comportement |
|---|---|
| **Accueil** | Grande action « Reprendre » sur la dernière lecture, carrousel « En cours », « Récemment ajoutés », « Nouveaux chapitres » des séries suivies, raccourcis Catégories. Une carte par œuvre/série, pas 217 cartes de chapitres. |
| **Bibliothèque** | Vues Œuvres / Séries / Catégories / Collections personnelles ; grille adaptative ou liste ; tri visible et conservé par profil. Pagination réelle et restauration de la position après retour du lecteur. |
| **Catégorie / Genre** | Catégorie de bibliothèque et genre comme filtres distincts, compteurs globaux pertinents, accès « Non classés ». Combinaison avec format, état de lecture, disponibilité offline et auteur. |
| **Recherche** | Recherche titre, auteur, série ; debounce ~300 ms, suppression des résultats obsolètes ; mêmes filtres et tri que bibliothèque ; résultat au niveau œuvre avec accès aux chapitres. Conserver la requête au retour. |
| **Fiche œuvre / série** | Couverture, description, auteurs, catégories, genres, formats disponibles, progression, CTA Reprendre/Lire ; liste de volumes/chapitres ordonnée, statut téléchargé, téléchargement ciblé et sommaire. |
| **Téléchargements** | En cours, terminés, erreurs ; taille/espace, pause/reprise selon transport, suppression locale, choix chapitre/série ; lecture fiable hors ligne. État « cache temporaire » distinct de « conservé ». |
| **Lecteur** | Contrôles discrets, sommaire, recherche de page/chapitre, progression locale et globale, signets, sens LTR/RTL, mode paginé ou vertical, adaptation largeur, zoom, rotation et thème. Sauvegarde d'ancre fiable au départ. |
| **Profil / Réglages** | Serveur, profil actif, état de synchro, préférences par type de livre, stockage et import avec suivi. États connexion expirée, serveur indisponible, livre retiré et page illisible explicites. |

Catégories recommandées : conserver d'abord les catégories existantes de bibliothèque, puis offrir pour Comics un **type de contenu** BD / Comics / Manga / Manhwa / Manhua, distinct du genre narratif (action, aventure, romance…). « Comics » actuellement enregistré comme genre du manhua n'apporte pas cette information. Ne pas inventer automatiquement son genre narratif. Les genres sont multiples ; les collections personnelles (« À lire », favoris, listes) ne sont ni des dossiers physiques ni des séries.

UX transversale : libellés français cohérents, tailles tactiles et texte accessibles, contrastes, grille adaptée aux tablettes, états vides utiles, erreur de page avec Réessayer/Passer, indicateurs de chargement localisés. Préférences du lecteur par œuvre/type, et bouton explicite pour reprendre ou recommencer. Pour EPUB : typographie, marges, interligne et thème ; PDF : zoom, page et rendu asynchrone ; comics : largeur lisible et continuité sans petites pages entières tassées dans l'écran.

### Contrat précis des tris et filtres

| Tri | Définition et comportement cible |
|---|---|
| **Récemment lus** | Dernière interaction de lecture de l'utilisateur, `last_read DESC` puis identifiant stable. Inclure les terminés dans l'historique ; le rail « En cours » reste séparé et filtré. Livres jamais lus en fin de bibliothèque, exclus de l'historique. |
| **Récemment ajoutés** | `added_at DESC, id DESC` ; jamais `modified_at`. Défaut de la Bibliothèque ; le premier élément de l'Accueil reste la reprise. |
| **Titre / Auteur** | Comparaison cohérente entre clients, tri stable et ordre secondaire par identifiant. Recherche tolérante aux accents à prévoir/tester, sans prétendre que SQLite NOCASE gère tout Unicode. |
| **Ordre de série** | Ordre explicite des volumes/chapitres, y compris 172.5. Ne dépend pas du nom de fichier ni d'un tri alphabétique de « Chapter 10 ». |
| **Récemment modifiés** | Option de gestion des métadonnées si utile, distincte des deux tris « récents » destinés à lire. |

Définir la date d'ajout d'une série/œuvre comme le premier ajout ; proposer un signal **nouveau chapitre** fondé sur le dernier ajout enfant, sans faire remonter une œuvre seulement parce qu'un second format du même livre arrive. La dernière lecture agrégée d'une série est le maximum des lectures de ses enfants pour le profil actif.

Le serveur doit appliquer **filtrage → regroupement en unités visibles → tri → pagination** et retourner un total dans cette même unité. Aujourd'hui `/api/books` limite les lignes avant `_group_format_variants` (`bookhaven.py:649`, `:653`). Facettes issues d'une requête dédiée — `/api/filters` existe déjà (`bookhaven.py:1180`) — et non des 50 cartes affichées. Contrat partagé pour `/books`, `/books/grouped`, récents et recherche, avec paramètres explicites `added_desc`, `last_read_desc`, etc., et migration compatible de `recent`.

### Modèle de données cible, par étapes

État actuel : `books` représente surtout un **fichier**, mêlant œuvre, format, genre texte séparé par virgules, série texte et `collection_path`. `reading_progress` est par `(user_id, book_id)` côté serveur (`database.py:42`), mais par `bookId` seul dans Room. Aucun modèle de chapitre/page ni de collection personnelle. La base réelle contient aussi `sub_series` et `sub_series_2` historiques ; les inventorier dans les migrations, sans supposer qu'une base fraîche leur ressemble.

1. **Stabiliser l'existant** : dates d'ajout immuables, tris explicites, pagination, facettes et état de lecture. Enrichir le cache Room : genre, série, dates, version et statut ; actuellement seuls ID/titre/auteur/format/catégorie sont conservés (`K/data/repository/DownloadRepository.kt:121`). Appliquer localement filtres/tris hors ligne, au lieu de renvoyer le snapshot entier quel que soit le filtre.
2. **Introduire une identité indépendante des fichiers** : `works`, `series`, `chapters` (ordre stable), et rattachement des `books` existants comme fichiers/éditions. Une œuvre ordinaire conserve sa fiche ; une série expose ses chapitres sans polluer la grille principale.
3. **Manifeste versionné** : `pages` ou index de contenu avec chapitre, source ZIP/entrée, dimensions, ordre, version/fingerprint. Plages de chapitres possibles dans le CBZ actuel ; fichiers par chapitre pour les nouveaux imports si souhaité. Distinguer version du fichier et simple modification de métadonnées.
4. **Taxonomie** : catégories stables, types de contenu, tables `genres` et relation N–N œuvre/genre ; migrer les tags texte sans perdre `genre_locked`. Collections personnelles et relation N–N par utilisateur. Déduplication formats par identité d'œuvre vérifiée, pas uniquement similitude de titre.
5. **Lecture/synchro** : clé locale `(server_id, user_id, work_id)` et ancre versionnée ; statut à lire/en cours/terminé, révision serveur et événement client idempotent. Une lecture volontaire en arrière est légitime : le pourcentage maximal ne doit plus gagner. Conserver un outbox pending jusqu'à ACK ; sérialiser/coalescer les sauvegardes par œuvre et gérer les suppressions comme événements terminaux.

Index proposés après vérification du plan SQL : `(added_at DESC, id DESC)`, `(category, added_at DESC, id DESC)`, progression `(user_id, last_read DESC, book_id)`, chapitres `(series_id, sort_order, id)` et pages `(chapter_id, ordinal)`. La base actuelle ne dispose pas d'index `added_at`. FTS pour titres/auteurs/séries peut venir après les corrections de pagination ; ~9 500 fichiers ne justifient pas d'emblée une infrastructure de recherche externe.

## 7. D — SQLite : cause, correctif et validation

### Incident du 18 septembre : ce qui est prouvé

- `bookhaven.log:1207` : **08:29:51**, `api_set_progress`, `FOREIGN KEY constraint failed` ; nouvelle occurrence à `:1214`.
- `bookhaven.log:1221` : **08:30:13**, `database is locked`, puis `:1228` et `:1235`.
- Nouvelle séquence plus explicite avec les lignes actuelles : `bookhaven.log:1283` (**08:59:28**, FK, `bookhaven.py:1290`) puis `:1289` (**08:59:44**, locked), jusqu'à `:1313` (**09:00:19**).
- L'INSERT vise `reading_progress.book_id`, seule FK de cette table, vers `books(id)` (`database.py:49`). Le code d'import supprime les anciens IDs de chapitres (`scripts/finalize_manhua_single.py:63`). Une progression issue d'un ancien onglet/app peut donc viser un ID absent.

**Conclusion causale :** le chemin FK échouée → transaction non terminée est démontré dans le code et reproduit en mémoire ; les logs sont cohérents avec son occurrence. **L'identité du processus/objet détenant le verrou historique et le book_id fautif ne figurent pas dans ces logs.** L'import est un déclencheur plausible d'IDs obsolètes, pas une preuve que sa connexion était l'unique propriétaire du verrou. Les logs plus anciens contiennent aussi des verrous, donc le défaut préexiste à ce manhua.

Reproduction isolée réalisée avec deux connexions SQLite en mémoire partagée, sans toucher la DB réelle :

```text
INSERT progression(book_id absent) -> FOREIGN KEY constraint failed
connexion A.in_transaction -> True
écriture depuis connexion B -> database table is locked
rollback + close de A ; nouvelle écriture B -> OK
```

Le message `database table is locked` appartient ici au mode shared-cache mémoire ; ce n'est pas une reproduction du code d'erreur WAL disque exact. Cela démontre le maintien de transaction après FK échouée. Le temps de rétention réel sans close dépend notamment de la vie des références/du GC ; on ne doit jamais lui confier la libération du verrou.

Une connexion simplement ouverte et inactive n'est **pas** nécessairement un verrou d'écriture. Le défaut déterminant est la **transaction d'écriture non terminée**, ou trop longue. Dans `media_worker.py`, un UPDATE peut rester non validé pendant les recherches réseau suivantes et leurs pauses, jusqu'au prochain multiple de 20. Le `finally` externe (`:681`) remet le statut du worker, pas la connexion. Dans le scanner/import initial, continuer après une exception sans rollback peut prolonger la transaction vers le fichier suivant.

### Correctif recommandé pour Opus 4.8

1. **Propriétaire unique de la connexion et fin garantie.** Pour chaque unité de travail : ouvrir, exécuter la transaction courte, commit si succès, rollback sur toute exception, close dans tous les cas. Exemple illustratif à implémenter ultérieurement :

   ```python
   from contextlib import closing

   with closing(database.get_db()) as conn:
       with conn:
           # Uniquement les écritures SQL de cette unité atomique.
           conn.execute(...)
   ```

   Le `except` qui transforme l'erreur en réponse HTTP doit être **à l'extérieur** du bloc transactionnel pour laisser le rollback s'exécuter. **`with conn:` seul ne ferme pas la connexion.** C'est indiqué dans la [documentation Python sqlite3](https://docs.python.org/3.12/library/sqlite3.html#how-to-use-the-connection-context-manager). Si `get_db()` échoue pendant les PRAGMA après connect, cette fonction doit aussi fermer la connexion déjà créée.

2. **Flask :** choisir soit un context manager explicite pour toutes les routes, soit une connexion lazy stockée dans `flask.g` et un `teardown_appcontext` garantissant rollback d'une transaction encore ouverte puis close. Le teardown ne doit jamais committer implicitement ; même une exception capturée et transformée en réponse 500 peut lui parvenir sans exception active. Workers/imports utilisent leurs propres connexions, jamais celle d'une requête ni une connexion globale partagée entre threads.
3. **Progression vers un livre retiré :** valider existence et valeurs, renvoyer 404/410 ou erreur métier documentée, rollback/close aussi si suppression concurrente provoque une FK après le contrôle. L'app retire/met en quarantaine l'outbox de cet ID et actualise le catalogue ; elle ne doit pas retenter indéfiniment. Préserver les IDs ou migrer les ancres lors d'un remplacement de contenu.
4. **Transactions courtes partout :** préparer couvertures, ZIP, appels réseau et pauses **avant** la transaction ; commit par livre ou petit lot déjà préparé. Corriger `media_worker`, `scanner`, upload, modifications de métadonnées et imports. `finalize_manhua_single.py:50` prépare déjà couverture/métadonnées avant `BEGIN IMMEDIATE`, ce qui va dans le bon sens, mais il manque une fermeture globale et une gestion de toutes les erreurs.
5. **Conserver WAL et régler les délais :** `database.py:10` à `:14` utilise déjà WAL, foreign_keys et 15 s de busy timeout. `media_worker.py:70` demande 30 s puis `:73` remplace ce délai par 5 s ; l'import final passe à 120 s avec six tentatives (`scripts/finalize_manhua_single.py:48`, `:60`). Ces attentes ne libèrent aucun verrou. Définir des délais cohérents et bornés selon requête/background, retry uniquement sur contention transitoire, après rollback et hors transaction. Initialiser WAL à la création/migration, conserver les PRAGMA par connexion nécessaires. WAL autorise lectures/écriture concurrentes, mais **un seul écrivain à la fois** : [documentation SQLite](https://www.sqlite.org/wal.html).
6. **Pas de pool comme remède initial.** Des connexions courtes par unité de travail conviennent ici. Un pool devrait réinitialiser/rollback chaque connexion rendue ; augmenter sa taille ne multiplie pas les écrivains SQLite. Une file d'écriture sérialisée peut servir aux tâches de fond si les mesures le justifient, sans bloquer les requêtes de lecture.
7. **Observabilité :** journaliser opération, book_id, durée de transaction, type/code SQLite, tentative et fin commit/rollback, sans données sensibles. Waitress a huit threads (`bookhaven.py:2639`) : plusieurs écritures attendant 15 s peuvent les occuper et donner l'impression d'un serveur globalement bloqué, même si WAL permet encore les lectures. Cette saturation est un mécanisme plausible, pas une mesure historique obtenue ici.

Validation à programmer sur DB **de test** : FK sur livre supprimé, exception entre deux écritures, échec au commit, import interrompu et enrichissement réseau lent ; dans tous les cas, aucune transaction persistante et écriture concurrente suivante réussie. Vérifier qu'un timeout retourne une réponse exploitable et ne rend pas les données partiellement validées. Ne jamais faire cette injection de panne sur la bibliothèque réelle.

## 8. Plan d'implémentation priorisé pour Opus 4.8

Estimations d'effort indicatives : **S = 0,5–1 j**, **M = 2–4 j**, **L = 5–8 j**, hors aléas et matrice complète d'appareils. L'impact prévaut pour les BLOCKER ; les durées sont à recalibrer après prise en main.

| Ordre | Lot | Impact × effort | Dépendances / critère de sortie |
|---|---|---|---|
| **P0.1** | Sécuriser la route progression et les propriétaires de connexions ; raccourcir les transactions worker/import/scan. | Critique × M | Tests d'erreur/concurrence ci-dessus ; FK supprimée ne bloque plus les autres écritures. Aucune migration de contenu nécessaire. |
| **P0.2** | Lecteur comic à références : pages API en ligne, `ZipFile` à la demande offline ; supprimer la liste d'octets globale ; décodage asynchrone borné et gestion de page haute. | Critique × M–L | Le manhua actuel ouvre sans charger 695 Mio. Dimension et budget vérifiés ; passage des images de 15 104 px. Le tuilage fait partie de ce lot si le downsampling seul dégrade la lisibilité. |
| **P0.3** | Confirmation sur téléphone et instrumentation de consommation/erreurs. | Élevé × S | Version installée identifiée, logcat, limites mémoire et profils heap/native/graphique ; ne pas annoncer le crash résolu sans mesure appareil. |
| **P1.1** | Pagination Android complète, facettes serveur, tri ajouté/lu explicite ; tri groupé web cohérent et totaux corrects. | Élevé × M | Plus de limite implicite à 50 ; mêmes résultats/tris sur les deux clients ; tests des tris avec dates identiques et formats multiples. |
| **P1.2** | Reprise et synchro : clés serveur/profil, outbox fiable, ordre des événements, relecture arrière, IDs supprimés. | Élevé × M | Aller-retour web/Android et lecture offline puis reconnexion sans recul involontaire ni mélange de profils. |
| **P1.3** | Accueil, bibliothèque et fiche série avec vocabulaire commun ; recherche annulable, genres et filtres persistants. | Élevé × M–L | Parcours trouver → reprendre → retour lisible, réactif et identique dans sa logique sur web/Android. S'appuyer sur P1.1/P1.2. |
| **P2.1** | Manifeste versionné, chapitres logiques et mapping du CBZ actuel ; migration compatible des positions. | Élevé × M–L | Une fiche pour 217 chapitres, ordre 172 → 172.5 → 173, aucune suppression des IDs actuels nécessaire. |
| **P2.2** | Scroll vertical virtualisé Android et web, tuiles, passage automatique de chapitre, prélecture/éviction. | Très élevé × L | Dépend du moteur sûr P0.2 et de P2.1 ; lecture complète sans croissance mémoire proportionnelle au nombre de pages. |
| **P2.3** | Téléchargements ciblés, reprises et cache borné ; politique offline par série/chapitre. | Élevé × M–L | Interruption réseau, cache évincé, disque plein et suppression locale gérés ; aucune archive partielle annoncée comme complète. |
| **P3** | Normalisation œuvres/formats/genres, collections personnelles, suivi des nouveautés, FTS et finition accessibilité. | Moyen à élevé × L | Migrations sauvegardées et vérifiées sur copie, ID/ancres préservés, index validés par plans SQL. |

### Recette incontournable

- **Mémoire/lecteur :** archive actuelle et pages extrêmes, ouverture à froid en ligne/offline, longues séquences avant/arrière, saut direct en fin, zoom/rotation, arrière-plan et destruction du processus. La consommation atteint un plateau dans le budget fixé ; pas de croissance avec 10 → 100 → 969 pages. Mesurer avant/après, sans exiger de garder les 969 bitmaps pour tester.
- **Continuité :** fin de chapitre → suivant sans écran intermédiaire ; reprise au bon endroit dans une page longue après redémarrage ; anciens index migrés ; ordre du chapitre décimal ; changement de version du contenu détecté.
- **Robustesse :** une image volontairement invalide dans une fixture, image géante valide, CBR réel, serveur absent, session expirée, fichier local manquant, disque plein, cache ancien. Une page en erreur n'empêche pas toutes les autres de se lire.
- **Bibliothèque :** catalogue > 50, filtres combinés, genres multiples, page finale, doublons de formats, ajout récent vs édition de métadonnées, œuvres terminées dans historique, profil différent. Ne pas traiter une réponse d'erreur serveur comme une bibliothèque vide réussie.
- **SQLite :** reproductions sur copies/fixtures, worker lent simultané à progression et import ; rollback/close vérifiés, temps de réponse mesuré, aucune fuite de transaction. Réutiliser/adapter les tests existants de progression, pagination et grouped, sans casser leur contrat par accident.

## 9. Callback court prévu pour chef

> ANALYSE BookHaven (GPT-6 Astra) : crash Android = OOM très probable, 695 Mio d'images retenus par ComicReaderFragment.kt:117 puis bitmaps natifs sans réduction (ComicPageAdapter.kt:29) ; logcat indisponible. Archive actuelle : 969 pages/217 chapitres, CRC et décodage PC OK. Scroll continu sans crash = fusion CBZ KO avec lecteur actuel, OK avec accès à la demande et tuiles ; cible une série + chapitres logiques + lecteur virtualisé. Refonte = Accueil/Reprendre, Bibliothèque paginée avec tris lu/ajouté, catégories/genres, fiche série, téléchargements et synchro fiable. Bug DB verrou = FK échouée sans rollback/close dans bookhaven.py:1290-1303, logs FK puis locked ; worker garde aussi ses transactions pendant le réseau. Fix : transactions courtes et rollback/close garantis ; WAL déjà actif. Plan priorisé écrit dans docs/bookhaven-redesign-astra.md. Aucun code modifié, aucun commit.
