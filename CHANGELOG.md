# Changelog

All notable changes to BookHaven will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.4.0] - 2026-08-28

Préparation à la publication (dépôt portfolio). Aucune donnée de la collection
n'est touchée ; le modèle d'exécution (processus Python standalone) est inchangé.

### Security
- **SSRF sur l'enrichissement de métadonnées.** `media_worker._fetch_json` et
  `_fetch_image` recevaient une URL issue des réponses d'Open Library / Google
  Books et la passaient telle quelle à `urllib.request.urlopen`, qui accepte
  aussi `file://`/`ftp://` et les hôtes privés. Ajout de `_is_safe_url()` :
  schéma `http(s)` uniquement, et rejet des hôtes résolvant vers une IP
  loopback / privée / lien-local / réservée (endpoints de métadonnées cloud
  inclus). Couvert par `tests/test_media_worker_ssrf.py`.
- **Android : suppression du `usesCleartextTraffic="true"` global** au profit
  d'un `network_security_config.xml` dédié et documenté (le cleartext reste
  permis pour le serveur auto-hébergé privé/VPN, cas d'usage nominal).
  `android:allowBackup` passe à `false`.

### Changed
- **Portabilité de l'exploitation** : `scripts/*.cmd` et `tests/conftest.py`
  dérivent la racine du dépôt de leur propre emplacement et l'interpréteur
  Python de `BOOKHAVEN_PYTHON` (repli sur `python` / `sys.executable`), au lieu
  de chemins machine en dur.
- `.env.example` : `BOOKHAVEN_COOKIE_SECURE` documenté ; variables `JELLYFIN_*`
  vestigiales retirées (l'auth est locale, plus aucune référence en code).

### Removed
- Six lanceurs `.bat`/`.ps1` et `start-wsl.sh` obsolètes à la racine (pointaient
  vers un répertoire qui n'existe plus ; les lanceurs actifs sont dans `scripts/`).
- `CLAUDE.md` retiré du suivi git (instructions de travail internes).

### Fixed
- **Lecteur EPUB web : la progression ne pouvait plus être écrasée par une
  position vide.** Un événement `relocated` transitoire sans CFI (émis par
  epub.js pendant le reflow d'un changement de taille de police / resize) était
  persisté tel quel, remplaçant un CFI valide par une chaîne vide et figeant la
  progression enregistrée à la position de départ de la session. Désormais un
  `relocated` sans CFI est ignoré, et `saveCurrentProgress()` refuse d'écrire une
  `current_location` vide (ne jamais renvoyer le lecteur — ou l'app Android qui
  se synchronise depuis le serveur — au début). La position EPUB reste un CFI,
  indépendant de la taille de police. Diagnostic vérifié sur le vrai lecteur
  (port 8097) : la progression continue d'avancer après un changement de police.

## [2.3.1] - 2026-08-17

### Security
- **Durcissement du verrou anti brute-force du PIN de connexion** pour qu'un
  client bloqué ne verrouille plus le client web humain partageant son IP (cas
  réel : l'app Android, buildée avant l'activation du PIN, rejouait
  `/api/auth/login` **sans PIN** à chaque lancement ; ces échecs se cumulaient
  sur l'IP VPN du téléphone avec les essais du navigateur → lockout en
  ~4 essais). Deux règles, toutes deux sûres contre le brute-force :
  - un PIN **vide ou absent** ne compte plus jamais comme un échec (ce n'est pas
    une tentative de deviner le PIN configuré, qui est non vide) ;
  - seuls les **PIN distincts** non vides font avancer le compteur : répéter le
    même mauvais PIN est inoffensif, alors qu'un vrai brute-force doit essayer
    des PIN différents pour explorer l'espace. Le seuil reste 5 (désormais 5
    PIN distincts) et le verrou 300 s. La recherche exhaustive d'un PIN 4
    chiffres est donc toujours coupée à 5 essais sur 10 000.

## [2.3.0] - 2026-08-14

Optimisation de `GET /api/books/grouped`, l'endpoint qui alimente la page
d'accueil. Développée en TDD contre une copie gelée de l'implémentation 2.2.0
(`tests/legacy_grouped.py`) servant d'oracle de parité.

### Changed
- **`/api/books/grouped` ne charge plus toute la table en mémoire** : l'agrégation
  des collections et le regroupement des variantes de format sont faits en SQL,
  et l'hydratation (`SELECT *`, qui trimballe la colonne `description`) est
  limitée à la page demandée. Sur la bibliothèque réelle (9 512 livres, 3 158
  items au niveau racine) : ~2× plus rapide (≈100 ms → ≈45 ms). Sur une base
  synthétique de 10 000 livres : 13 400 lignes lues → 3 700, dont 3 400 lignes
  complètes → au plus `per_page`.
- Le tri final reste en Python (`title.lower()`) et non en SQL : `lower()` SQLite
  ne replie que l'ASCII, un `ORDER BY lower(title)` réordonnerait une
  bibliothèque française (« École », « Éric »).
- **Réponse JSON inchangée**, vérifiée contre l'oracle sur fixtures (matrice
  filtres × pagination × préfixes) et sur la base de production (24/24
  combinaisons identiques). Trois divergences volontaires, toutes des valeurs
  qui dépendaient auparavant du plan d'exécution SQLite et sont désormais
  déterministes :
  - `cover_book_id` d'une collection = plus petit id ayant une couverture
    (avant : « la première ligne rencontrée ») — impact purement visuel, sur
    certaines vignettes de collections filtrées ;
  - l'ordre relatif de deux items au titre identique est désormais stable ;
  - l'ordre des variantes de même priorité de format dans `formats` (deux
    fichiers de même nom de base ET de même format) est désormais trié par id.
  Sur la base de production, seule la deuxième s'observe réellement (19/24
  combinaisons sont identiques octet pour octet, les 5 autres ne diffèrent que
  par l'ordre de deux livres partageant exactement le même titre).
- La connexion SQLite de l'endpoint est désormais fermée aussi sur le chemin
  d'erreur.

### Added
- Index `idx_books_collection_path` sur `books(collection_path)`.
- `scripts/check_grouped_parity.py` : compare l'endpoint à l'implémentation 2.2.0
  sur la vraie base, en **lecture seule** (`file:...?mode=ro`).

### Fixed
- Rien : la parité était l'objectif. Deux bizarreries pré-existantes sont
  **volontairement conservées** et désormais couvertes par des tests, faute de
  quoi elles auraient disparu par accident : la navigation par `prefix` fait un
  `LIKE prefix || '/%'` sans `ESCAPE` (un `%` ou `_` dans un nom de collection
  agit donc en joker et fait apparaître des collections voisines), et un livre
  isolé fusionne avec la variante d'une collection mono-livre de même nom de
  base. À traiter séparément, en connaissance de cause.

## [2.2.0] - 2026-08-14

Seconde passe de remédiation TDD (revue critique n°2). Le PIN `BOOKHAVEN_PIN`
étant désormais actif en production, la priorité est la protection du login.
Chaque correctif est couvert par des tests dans `tests/`.

### Security
- **Anti brute-force sur le PIN** : 5 échecs de PIN depuis une même IP verrouillent `/api/auth/login` **et** `POST /api/auth/users` (même oracle) pendant 5 min (HTTP 429), même avec le bon PIN ensuite. Compteur remis à zéro après connexion réussie. Indispensable : un PIN 4 chiffres se brute-force en secondes depuis le LAN.
- **`_check_pin` ne crashe plus (500) sur un PIN non-ASCII ou d'un type inattendu** : comparaison à temps constant sur octets UTF-8, valeurs non-chaîne rejetées.
- **Session régénérée au login** (`session.clear()` avant pose de `user_id`) : anti fixation de session.
- **`/api/scan/status` et `/api/convert/status` ne fuient plus `str(e)`** : message générique côté client, détail en log serveur uniquement.
- **`PUT /api/books/<id>/epub-locations` borné** : payload limité à 2 Mo (413) et le livre doit exister en base (404) — c'était une écriture disque arbitraire et répétable jusqu'à 512 Mo par requête.
- **TLS in-process refusé au démarrage** : la présence de `server.crt`/`server.key` rebasculait silencieusement sur le serveur de dev Werkzeug (annulant le fix waitress). Le serveur refuse désormais de démarrer avec un message clair : terminer le TLS dans un reverse proxy.
- **waitress `max_request_body_size` aligné sur `BOOKHAVEN_MAX_UPLOAD_MB`** : par défaut waitress spoolait jusqu'à ~1 Go sur disque avant que Flask ne rejette à 512 Mo.

### Fixed
- **Races TOCTOU sur les flags `running`** (`/api/scan`, `/api/books/<id>/convert-epub`, `/api/enrichment/start`) : test-and-set sous `threading.Lock` avant de lancer le thread — deux POST rapprochés pouvaient lancer deux workers concurrents (ex. deux Calibre sur le même fichier). Le flag est libéré si les pré-vérifications échouent ou si le worker crashe.
- **Timeout de conversion Calibre effectif** : `proc.wait(timeout=600)` était inatteignable (la boucle de lecture bloque jusqu'à EOF) ; un watchdog `threading.Timer` tue désormais le process après 10 min.
- **`_pending_uploads` protégé par lock** (threads waitress : un double pop concurrent provoquait un 500) et **purge au démarrage des fichiers temporaires orphelins** dans `data/uploads`.
- **`server.log` borné** : le handler stdout ne laisse passer que WARNING+ quand stdout est redirigé (le détail INFO reste dans `bookhaven.log` qui tourne), et `start-server.cmd` fait tourner `server.log`/`server_err.log` en `.1` à chaque lancement.

### Removed
- Handler mort `except subprocess.TimeoutExpired` dans `api_optimize_epub` (aucun subprocess appelé).

## [2.1.0] - 2026-08-13

Release de sécurité (passe de remédiation TDD post-audit) : chaque correctif est
couvert par des tests dans `tests/`.

### Security
- **XSS stocké via `/api/epub-resource`** : un `.html` embarqué dans un EPUB était servi en `text/html` sur l'origine de l'application. Seuls images/CSS/polices sont désormais servis inline avec leur vrai MIME ; tout le reste part en `application/octet-stream` + `Content-Disposition: attachment`, avec `nosniff` et une CSP `default-src 'none'` (neutralise aussi les scripts SVG).
- **PIN de connexion optionnel** (`BOOKHAVEN_PIN` dans `.env`) : exigé à la connexion et à la création d'utilisateur quand configuré (comparaison à temps constant). Le bind `0.0.0.0` est conservé pour l'accès LAN/VPN ; PIN vide = comportement antérieur, documenté dans `.env.example`.
- **Taille de requête bornée** : `MAX_CONTENT_LENGTH` configuré via `BOOKHAVEN_MAX_UPLOAD_MB` (défaut 512 Mo) — upload trop gros → 413.
- **`/api/books/<id>/file` streame depuis le disque** (`send_file` + Range/206) au lieu de charger le fichier entier en RAM à chaque requête.
- **Cookies de session durcis** : `SameSite=Lax` (bloque le CSRF par formulaire cross-site, ex. `/api/upload/analyze`), `HttpOnly` explicite, `Secure` opt-in via `BOOKHAVEN_COOKIE_SECURE`.
- **Headers de sécurité globaux** (`after_request`) : CSP, `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy` sur toutes les réponses.
- **Les détails d'exception ne sont plus renvoyés au client** : 15 handlers renvoyaient `str(e)` ; message générique côté client, détail loggé côté serveur.
- **waitress remplace le serveur de développement Flask** (le chemin TLS et le fallback sans waitress conservent Flask). Point d'entrée inchangé : `scripts\start-server.cmd` et le watchdog fonctionnent tels quels.
- **Uploads validés par magic bytes** (ZIP/RAR/%PDF/BOOKMOBI) en plus de l'extension.
- **`BOOKHAVEN_TEST_MODE` verrouillé** : refuse de démarrer (RuntimeError) si `BOOKHAVEN_ENV` n'est pas un environnement de dev — le bypass d'auth ne peut plus fuiter en production.
- **`/api/books/<id>/cover` et `/api/enrichment/status`** exigent désormais une session.
- **Jokers SQL `%`/`_` échappés** dans les filtres LIKE (recherche, genre, auteur).

### Fixed
- `import subprocess` au niveau module : `except subprocess.TimeoutExpired` dans `optimize-epub` levait un `NameError` qui masquait l'erreur réelle.
- Les uploads en attente expirent après 1 h (fuite mémoire + fichiers temporaires dans `data/uploads`).
- `requirements.txt` : ajout de `PyMuPDF` (utilisé par 4 modules) et `waitress`, toutes les versions épinglées.
- Rotation de `bookhaven.log` (5 Mo × 3 sauvegardes) — le fichier avait atteint 42 Mo.
- `page`/`per_page`/`n` validés et bornés (plus de 500 sur entrée non numérique, `per_page` ≤ 200).

### Changed
- Suppression du doublon mort `_base_filename`/`_group_format_variants` (la première définition était écrasée par la seconde) ; sémantique active épinglée par des tests de caractérisation.

## [2.0.0] - 2026-08-06

Version majeure : le serveur **refuse désormais de démarrer** avec une configuration
antérieure. Voir « Breaking » ci-dessous avant de mettre à jour.

### Breaking
- **`BOOKHAVEN_SECRET_KEY` obligatoire, 32 caractères minimum.** `config.py` lève une `RuntimeError` au démarrage si la clé est absente, trop courte, ou égale à l'ancienne valeur de développement `bookhaven-dev-secret`. Générer avec `python -c "import secrets; print(secrets.token_hex(32))"`.
- **`BOOKS_ROOT` doit être un chemin Windows natif** (`H:\Books`) et non un chemin WSL (`/mnt/h/Books`).
- **`docker-compose.yml` supprimé.** Le projet ne tourne plus sous Docker : processus Python standalone piloté par le Planificateur de tâches Windows (`BookHaven-server` + `BookHaven-watchdog`).

### Security
- **XSS en contexte d'attribut** : `esc()` passait par `textContent`/`innerHTML`, qui n'échappe pas les guillemets — toute valeur insérée dans un attribut restait injectable. `esc()` échappe maintenant aussi `"` et `'`, et une fonction `jsq()` a été ajoutée pour les gestionnaires inline, où le navigateur décode l'attribut avant que JS ne l'analyse. 8 sites corrigés (carte utilisateur, liens de série, édition de genre, suggestions d'auteur, fil d'Ariane, cartes de collection, badges de format). Les métadonnées de livre provenant de fichiers EPUB uploadés, elles sont contrôlables par un tiers.
- **Traversée de répertoire à l'upload** : `dest_folder` est validé contre `LIBRARY_PATHS` avant tout accès disque, avec comparaison sur séparateur pour empêcher qu'un dossier voisin (`…\Books2`) satisfasse le préfixe de `…\Books`.
- **Nom de fichier à l'upload** : composantes de chemin, caractères illégaux et noms réservés Windows neutralisés par `_safe_filename()`, qui préserve l'Unicode.
- **epub.js** : `allowScriptedContent` passé à `false`.

### Fixed
- **Chemins de la bibliothèque migrés** de `/mnt/h/Books/...` (reliquat WSL/Docker) vers `H:\Books\...`. Les lectures fonctionnaient via `_resolve_book_path()`, mais les écritures contournaient cette traduction : les uploads créaient des dossiers fantômes (`I:\mnt\h\Books`, `C:\mnt\h\Books`) hors de la bibliothèque. 9511 lignes migrées, 4803 vignettes déplacées vers leur nouveau hash `md5(chemin)`, 9512/9512 chemins vérifiés présents sur disque. Outil : `scripts/migrate_books_root.py` (dry-run par défaut, sauvegarde et journal de correspondance).
- **Isolation des tests** : `test_config.py` retirait `config` de `sys.modules` sans le restaurer ; `database.py` conservant une référence à l'objet d'origine, la redirection de `config.DB_PATH` d'un autre test était sans effet et celui-ci écrivait dans la base de production. Garde-fou ajouté dans `conftest.py`.
- **`SyntaxWarning`** sur la docstring de `_resolve_book_path` (séquence d'échappement `\.`).

### Added
- `scripts/migrate_books_root.py` : migration des chemins, idempotente, dry-run par défaut.
- Tests de sécurité : 28 cas couvrant la clé secrète, la traversée de répertoire, la sanitisation des noms de fichiers et la préservation de l'Unicode.

## [1.2.47] - 2026-08-04

### Fixed
- **Résolution de chemins** : le serveur Windows Python ne pouvait pas accéder aux fichiers dont le chemin en base est au format WSL (`/mnt/h/...`) — `_resolve_book_path` traduit maintenant ces chemins en chemins Windows (`H:\...`) avant de tenter l'accès disque.

## [1.2.46] - 2026-07-30

### Fixed
- **Lecteur Android EPUB** : calcul des positions (`generate()`) maintenant mis en cache côté serveur — lectures suivantes du même livre chargent les positions instantanément depuis `/api/books/<id>/epub-locations` au lieu de recalculer.

## [1.2.45] - 2026-07-30

### Fixed
- **Lecteur web EPUB** : `epub-resource` retournait 404 pour les chemins relatifs à l'OPF (`Text/ch.xhtml` vs `OEBPS/Text/ch.xhtml`) — fallback via `container.xml` pour retrouver le préfixe correct.
- **Lecteur web EPUB** : prefetch d'images spammait le serveur de requêtes 404 en boucle (delete → retry infini) — les non-200 sont maintenant marqués définitivement échoués.
- **Lecteur web EPUB** : chunk size de `generate()` passé de 1024 à 1600 (même valeur qu'Android) — calcul des positions plus rapide.

## [1.2.44] - 2026-07-30

### Added
- **Lecteur web EPUB** : barre de navigation en bas (seekbar + pill page X/total). Spinner pendant le calcul des positions (`generate()`), seekbar activée quand prête. Clic sur la pill ouvre un saut direct à une position.

## [1.2.43] - 2026-07-30

### Fixed
- **Lecteur web EPUB** : `ePub(url)` sans suffixe `.epub` était interprété par epub.js comme un manifest OPF au lieu d'un zip — ajout de `{ openAs: 'epub' }` pour forcer le bon mode de chargement.
- **Scanner** : si 0 fichiers sont trouvés (ex. disque débranché) mais que la DB contient des livres, le scan n'efface plus le catalogue (garde-fou anti-déconnexion du Seagate).
- **Config WSL** : ajout de `BOOKS_ROOT=/mnt/h/Books` dans `.env` — le chemin Windows `H:\Books` n'est pas accessible depuis Python/WSL.

## [1.2.42] - 2026-07-26

### Changed
- **EPUB reader (app)** : boutons A−/A+ déplacés du centre-haut (sur le texte) vers le coin bas-droit, à côté des ronds de thème — ils ne gênent plus la lecture.

## [1.2.41] - 2026-07-26

### Added
- **EPUB reader (app)** : icône spinner discret au bas de l'écran pendant le calcul des positions (`locations.generate()`) — indique à l'utilisateur que la barre de navigation arrive, sans bloquer la lecture.

### Fixed
- **EPUB reader (app)** : téléchargement partiel de l'EPUB laissait un zip tronqué — epub.js affichait le premier chapitre mais `generate()` échouait silencieusement sur les chapitres manquants, laissant la barre désactivée à jamais. Le fichier partiel est maintenant supprimé avant chaque tentative, avec retry automatique (2 essais).
- **EPUB reader (app)** : un échec de `generate()` appelait `Android.onError` ("Cannot open book") alors que le livre était bien lisible. L'erreur est désormais loguée sans afficher de toast.

## [1.2.40] - 2026-07-26

### Fixed
- **EPUB reader (app)** : confirmé et validé sur émulateur — pastille page, SeekBar, drag, saut manuel de page tous fonctionnels (build de test).

## [1.2.39] - 2026-07-26

### Fixed
- **EPUB reader (app)** : la pastille de page restait invisible à jamais — la règle CSS `#page-pill { display: none }` reprenait le dessus dès que `pagePill.style.display = ''` supprimait le style inline. Le display inline est désormais forcé à `inline-block` (dans `updatePill` et `closeJump`).
- **EPUB reader (app)** : relâcher la SeekBar avant la fin de `book.locations.generate()` renvoyait à la page 1 — la garde de `seekToProgress` testait `locations.length()` (déjà > 0 dès la première section) au lieu de `locations.total`. Garde corrigée sur `total`.
- **EPUB reader (app)** : la position sauvegardée était écrasée par un curseur à 0 — avant la fin de `generate()`, `location.start.percentage` valait 0 et Kotlin remettait le curseur à zéro. Le handler `relocated` calcule maintenant `pct` via `percentageFromCfi` seulement quand les locations sont prêtes, et ne pousse plus `onPageChange` tant que `total == 0` (il envoie `onProgressCfi` pour la seule sauvegarde du CFI).
- **EPUB reader (app)** : SeekBar bloquée en état désactivé si `currentLocation()` renvoyait `undefined` après `generate()` — l'activation de la barre passe désormais par un nouveau callback `onLocationsReady`, appelé inconditionnellement dès que les locations sont prêtes.
- **EPUB reader (app)** : un échec de `book.locations.generate()` détruisait tout le lecteur via le `.catch` global. Le catch de `generate()` est isolé : une erreur de génération des locations n'efface plus le contenu affiché.

## [1.2.38] - 2026-07-26

### Fixed
- **EPUB reader (app)** : la SeekBar était utilisable avant que `book.locations.generate()` termine — `seekToProgress` retournait immédiatement (locations vides), puis le premier `relocated` remettait la barre à la page 1. Correction : la SeekBar est désactivée (alpha 0.5) jusqu'à ce que `onPageChange` reçoive un `total > 0` ; en parallèle, `seekToProgress` mémorise le dernier seek demandé et l'exécute dès que les locations sont prêtes.

## [1.2.37] - 2026-07-26

### Fixed
- **EPUB reader (app)** : barre de progression (SeekBar) bloquée à "0 / 0" — `Android.onPageChange` n'était pas appelé après `book.locations.generate()`, donc `totalPages` restait à 0 côté Kotlin. Le callback `.then()` appelle désormais `Android.onPageChange` avec le total correct.
- **EPUB reader (app)** : pastille de page, boutons A−/A+ et points de thème quasi-invisibles en thème clair — les backgrounds `rgba(0,0,0,0.30)` disparaissaient sur fond blanc. Opacité portée à 0.55, texte en blanc pur.

## [1.2.36] - 2026-07-26

### Added
- **EPUB reader (app + web)** : trois thèmes de lecture — Clair (blanc/noir), Sépia (#f6f1e7 / brun foncé) et Sombre (#1e1e1e / gris clair). Sur le web : trois petits points colorés dans la barre de lecture, à droite des boutons A−/A+. Sur l'app : trois petits points en bas à droite. Le thème persiste entre les sessions (localStorage côté web). Changement instantané sans rechargement du chapitre : la balise `<style id="reader-theme">` dans chaque iframe epub.js est mise à jour en direct.

## [1.2.35] - 2026-07-26

### Fixed
- **EPUB reader (web)** : augmenter la taille de la police envoyait le texte sous le footer sans possibilité de scroller. Après `themes.fontSize()`, appel de `rendition.resize()` pour forcer epub.js à recalculer la mise en page paginée dans les dimensions fixes du conteneur.

## [1.2.34] - 2026-07-26

### Added
- **EPUB reader (app + web)** : contrôles A− / A+ pour diminuer ou augmenter la taille de la police par paliers de 10 % (de 60 % à 200 %). Sur l'app : deux boutons discrets en haut au centre (zone sécurisée entre les tap zones). Sur le web : dans la barre de lecture, entre le titre et l'indicateur de progression. La taille est réinitialisée à 100 % à chaque ouverture de livre.

### Fixed
- **EPUB reader (app)** : le numéro de page n'apparaissait pas — la pastille n'était mise à jour que par l'événement `relocated`, qui ne reffire pas après la génération des locations. Ajout d'un callback sur `book.locations.generate().then()` pour afficher le numéro immédiatement dès que les locations sont prêtes.

## [1.2.33] - 2026-07-25

### Added
- **EPUB reader** : pastille de numéro de page en bas au centre (`42 / 890`), semi-transparente, visible dès que les locations epub.js sont générées. Tap sur la pastille → champ de saisie avec le numéro courant pré-rempli et le total affiché ; valider avec Entrée ou taper en dehors pour naviguer directement à la page souhaitée. Hors du formulaire, tap en dehors annule sans naviguer.

## [1.2.32] - 2026-07-23

### Fixed
- **EPUB texte** : les séquences `<`, `>`, `&`, etc. s'affichaient littéralement au lieu d'être interprétées. Ces escapes JSON se retrouvent dans les EPUB générés à partir d'APIs web (Royal Road, Webnovel…) où le convertisseur n'a pas décodé le JSON avant d'écrire le XHTML. Le hook `content` parcourt désormais tous les nœuds texte et décode les séquences `\uXXXX` → caractère Unicode correspondant. Fix appliqué sur l'app Android et le site web.

## [1.2.31] - 2026-07-23

### Fixed
- **EPUB pages blanches / navigation bloquée** : le hook `content` injectait `overflow-x: hidden` sur `html/body`, ce qui clippait les colonnes CSS qu'epub.js crée pour la pagination (les pages 2..N de chaque chapitre devenaient invisibles). La fonction `clearImageAncestors()` écrasait aussi les règles `max-height` et `object-fit: contain` qu'epub.js injecte lui-même pour contraindre les images à la hauteur d'une page. Les `setTimeout`/MutationObserver post-layout altéraient la géométrie après mesure, désalignant les offsets de page. Tout supprimé : le hook se limite désormais à une palette de couleurs + un filet de sécurité image compatible colonnes + la réécriture des `src` blob manquants.
- **`doNav` lock** : la promise de `rendition.next()`/`prev()` était ignorée ; en cas de rejet asynchrone, `navPending` restait vrai jusqu'au timeout de 2 s. Le lock se libère maintenant aussi via `.catch()`.

## [1.2.30] - 2026-07-23

### Fixed
- **EPUB navigation** : supprimé `flow: 'scrolled-doc'` — ce mode charge un chapitre entier et fait naviguer `prev()`/`next()` entre chapitres plutôt qu'entre pages. Alignement avec l'app web qui utilise le mode paginé par défaut : chaque tap avance/recule d'une page, le chapitre change quand on atteint la fin ou le début.

## [1.2.29] - 2026-07-23

### Fixed
- **EPUB navigation** : tentative de scroll page par page en `scrolled-doc` — remplacé en 1.2.30.

## [1.2.28] - 2026-07-20

### Fixed
- **EPUB navigation** : supprimé `contents.expand()` dans le hook `img.onload` — en scrolled-doc, `expand()` déclenche `IframeView.relocated()` dans epub.js, ce qui fire `rendition.relocated` et libère `navPending` prématurément tout en mettant à jour la position interne. Le `next()` suivant partait d'une position avancée, sautant un chapitre par tap.

## [1.2.27] - 2026-07-17

### Fixed
- **EPUB images** : supprimé le bloc `aspect-ratio + min()` introduit en 1.2.26 — incompatible avec les WebView Android < Chrome 79 (la fonction CSS `min()` est ignorée silencieusement, les images se rendaient à leur taille naturelle). Remplacé par `width: 100% !important` en CSS et en inline style directement sur chaque `<img>` via `clearImageAncestors()`. Ajouté `overflow: visible !important` et `width: 100% !important` dans le walk des ancêtres pour neutraliser les conteneurs à `overflow: hidden` ou à largeur figée qui faisaient apparaître l'image derrière le texte.

## [1.2.26] - 2026-07-17

### Fixed
- **EPUB images** : supprimé `width: auto !important` sur `img` qui détruisait la réservation d'espace native du navigateur (dérivée des attributs HTML `width`/`height`). Ajouté réservation explicite via `aspect-ratio` + `width: min(100%, Npx)` pour les images avec dimensions déclarées. Remplacé `iframeWin.dispatchEvent('resize')` (no-op pour epub.js) par `contents.expand()` dans le hook `img.onload`, qui déclenche la re-mesure et le recadrage correct de l'iframe epub.js.

## [1.2.25] - 2026-07-16

### Fixed
- **EPUB images**: renforcé la neutralisation des styles EPUB qui causent l'affichage d'images derrière le texte en scrolled-doc. Ajout de `height: auto` / `max-height: none` / `min-height: 0` sur `figure` pour tuer les conteneurs à hauteur figée ; détection du padding-bottom hack (`height:0 + padding-bottom`) ; correction des marges négatives sur les éléments siblings ; guard d'idempotence dans `forceStyle` pour éviter les boucles MutationObserver ; hook `img.onload` pour re-appliquer les corrections quand une image lourde finit de charger ; durée de vie de l'observer portée à 8 s.

## [1.2.24] - 2026-07-16

### Fixed
- **EPUB images**: removed `overflow: hidden` from figure (it could collapse figure height in scrolled-doc mode, letting the image render behind subsequent text). Added `position: relative !important` and `width: auto !important` directly on `img` elements; set `width: 100%` on `figure` to establish a width context. Removed column-specific `break-inside` rules.

## [1.2.23] - 2026-07-16

### Fixed
- **EPUB images**: replaced `max-width: <pxValue>` with `max-width: 100%` on `img` elements and added `overflow: hidden` on `figure` — prevents wide images from overflowing the viewport horizontally in scrolled-doc mode. Added `height: auto` to preserve aspect ratio.

## [1.2.22] - 2026-07-16

### Fixed
- **EPUB images**: switched epub.js render flow from `paginated` (CSS columns) to `scrolled-doc`. CSS column layout was causing figure elements to visually overlap text when they couldn't fit within a column height, regardless of float/position rules. Scrolled-doc mode renders chapters as continuous documents where images flow naturally with text.

## [1.2.21] - 2026-07-16

### Fixed
- **EPUB loading**: external cache path (`/sdcard/Android/data/.../cache/`) checked as fallback when internal cache is empty — allows pushing epub files via adb without root access.

## [1.2.20] - 2026-07-16

### Changed
- **EPUB reader**: enabled WebView remote debugging (`setWebContentsDebuggingEnabled(true)`) to allow Chrome DevTools inspection via `adb forward tcp:9222 localabstract:chrome_devtools_remote`.

## [1.2.19] - 2026-07-16

### Fixed
- **EPUB images**: MutationObserver on body (3 s window) re-runs float/position clearing on any subsequent DOM or style changes. Style tag re-appended last in `<head>` on each pass to win cascade against async epub stylesheets.

## [1.2.18] - 2026-07-16

### Fixed
- **EPUB loading**: OkHttp pre-download skips download if temp file already exists and is non-empty — avoids `unexpected end of stream` on repeated opens when the epub is already cached.

## [1.2.17] - 2026-07-16

### Fixed
- **EPUB renderer**: removed `[class*="right"]` and `[class*="image"]` CSS selectors introduced in 1.2.16 — they matched epub.js internal layout classes and destroyed column pagination, causing a blank white page.

## [1.2.16] - 2026-07-16

### Fixed
- **EPUB images**: multiple CSS selector strategies for float/position clearing; timed retry at 100/400/1000 ms to catch async-loaded epub stylesheets.

## [1.2.15] - 2026-07-15

### Fixed
- **EPUB images**: added DOM traversal from each image up to body — any ancestor with float or position:absolute has it cleared at runtime. CSS alone could not reach floated parent containers.

## [1.2.14] - 2026-07-15

### Added
- **EPUB reader**: the SeekBar shows a page-number bubble (currentPage / totalPages) above the thumb while dragging, positioned dynamically over the thumb.

### Fixed
- **EPUB images**: added `float:none` / `display:block` to injected CSS — epub `float:right` was causing images to overlap text instead of sitting in the document flow.

## [1.2.13] - 2026-07-15

### Added
- **EPUB reader**: progress bar replaced with a SeekBar (thumb indicator shows current position). Dragging and releasing seeks to the corresponding book location via `book.locations.cfiFromPercentage()`.

### Fixed
- **EPUB images**: removed `width:auto` / `height:auto` / `object-fit` from injected CSS — those properties were pulling images out of the text flow. Only `max-width`, `max-height`, and `break-inside` remain.

## [1.2.12] - 2026-07-15

### Fixed
- **EPUB images**: injected CSS constrains img/image/svg to the exact page dimensions (max-width/max-height in pixels from the iframe viewport) and prevents images from being split across page boundaries (break-inside: avoid). Uses !important to override conflicting epub CSS.

## [1.2.11] - 2026-07-15

### Fixed
- **EPUB navigation**: touch listeners moved out of the epub.js iframe (`hooks.content.register`) into fixed overlay divs in the main page. Iframe coordinate system changes on chapter transitions were causing direction inversions. The two overlay zones (left 33% = prev, right 33% = next) operate in stable main-page coordinates. The center third is uncovered so epub content links work normally.

## [1.2.10] - 2026-07-15

### Fixed
- **EPUB reader position not restored on reopen**: `savedCfi` was loaded from Room but never passed to epub.js. It is now injected as `window.__SAVED_CFI` and passed to `rendition.display()`.
- **EPUB reader lost progress when leaving**: the position save ran in `onDestroyView()` on `viewLifecycleOwner.lifecycleScope`, which is already cancelled at that point, so the write never started. Moved to `onStop()` using the Fragment `lifecycleScope`.
- **EPUB navigation**: the `navPending` lock now releases on the `relocated` event (page visually ready) rather than waiting for the Promise alone, fixing the alternating-direction loop at chapter boundaries.

## [1.2.9] - 2026-07-15

### Fixed
- **EPUB navigation**: replaced the fixed 600 ms debounce with a Promise-based lock that releases as soon as epub.js settles the page transition. The old timeout was releasing before chapter-boundary renders completed, causing the rendition queue to jam after back-and-forth navigation.

## [1.2.8] - 2026-07-15

### Fixed
- **EPUB reader black text pages**: the EPUB body was transparent and the dark outer page bled through the iframe. The content hook (`rendition.hooks.content.register`) now forces a white background.
- **EPUB reader froze on rapid page turns**: added a debounce guard (600 ms lock) around `rendition.next` / `rendition.prev`.
- **Downloaded book vanished from "Continue Reading"**: opening a downloaded EPUB reports 0% momentarily (epub.js renders from page 1), and the Android reader pushed that 0 to the server, which filters `progress > 0` out of the in-progress list — so the book disappeared on the next refresh. `DownloadRepository.saveProgress` now mirrors the web client's guard: a book with a real reading location is never stored below 1%, keeping it in "Continue Reading".

## [1.2.7] - 2026-07-14

### Added
- **Offline reading progress sync**: progress is saved locally (Room) immediately and pushed to the server when online. On reconnect and at startup, local and server positions are reconciled — highest progress always wins. Books read on the web or another device are pulled into local history via `/api/continue-reading`.

### Fixed
- **EPUB text layout**: the epub.js rendition now receives pixel dimensions (`window.innerWidth` / `window.innerHeight`) instead of `100%` strings, with `minSpreadWidth: 9999` to enforce single-column layout — fixing incorrect pagination on Android WebView.

## [1.2.5] - 2026-07-14

### Added
- **Android EPUB page navigation**: the reader had no way to turn pages. A touch handler is now registered on the epub.js content document (inside the rendered iframe) — tap the left third for the previous page, the right third for the next, or swipe horizontally.

### Fixed
- **Android offline list showed no titles**: `OfflineAdapter` built its TextViews programmatically in the ViewHolder constructor. Replaced with a proper `item_offline_book.xml` layout bound via `ItemOfflineBookBinding`, showing title and an author · format · size subtitle.

### Changed
- **Android errors shown as toasts**: `showError()` now displays a non-blocking Toast instead of a copyable AlertDialog.

## [1.2.4] - 2026-07-14

### Fixed
- **Android EPUB offline black screen**: with `loadDataWithBaseURL(null, …)` the reader page had an opaque `about:blank` origin, so epub.js/JSZip could not XHR the local temp EPUB (`allowUniversalAccessFromFileURLs` only relaxes `file://`-origin pages). Base URL is now `file:///android_asset/`, giving the page a `file://` origin with access to the cached EPUB.
- **Android library reloaded from scratch on every tab switch**: `LibraryViewModel` is now scoped with `activityViewModels()` (survives Fragment recreation), and `loadBooks` no longer flashes the loading spinner when content is already shown.

### Added
- **Android offline library cache**: successful unfiltered library loads are snapshotted into a new Room table (`cached_books`, DB v3); when the network is unreachable the grid falls back to this snapshot with a "Mode hors-ligne" toast instead of an error.
- **Android offline reading from the library**: tapping a downloaded book now opens it from its local file (offline), and the "Continue Reading" row supports the same long-press menu (Lire / Télécharger / Détails) as the grid.

## [1.2.3] - 2026-07-14

### Fixed
- **Android EPUB reader black screen (root cause)**: WebView sandbox drops the TCP connection mid-body when fetching a large binary over `http://` via XHR (confirmed via `fetch().arrayBuffer()` returning `TypeError: Failed to fetch` after receiving HTTP 200 headers). Fix: `EpubReaderFragment` now pre-downloads the EPUB via OkHttp (which has no such restriction) into a cache temp file, then loads epub.js from `file://` — no HTTP fetch from the WebView at all. Books already downloaded offline reuse their local file directly.

## [1.2.2] - 2026-07-14

### Fixed
- **Android EPUB reader black screen**: the reader HTML was loaded from `file:///android_asset/…#bookId|serverUrl|` and the `|` fragment separator was percent-encoded (`%7C`) by WebView (Chromium), so the JS `split('|')` produced an empty `serverUrl` and epub.js fetched a nonexistent relative path — book.ready never resolved and the 20 s guard fired. The reader is now loaded via `loadDataWithBaseURL(serverUrl, …)` with params injected as JS globals (`window.__BOOK_ID` / `__SERVER_URL` / `__LOCAL_PATH`); streaming XHRs are same-origin with the server so the session cookie is sent. The epub.js / jszip libraries are inlined into the document so relative `<script src>` no longer resolves against the server base URL.

## [1.2.0] - 2026-07-14

### Added
- **Route `/download`** (public, no authentication): APK download page for the BookHaven Android app.
  - New `templates/download.html` — dark theme matching BookHaven (accent `#7c5cff`), app title, dynamic version, "Download APK" button pointing to `/static/bookhaven-android.apk`, and short install instructions (enable unknown sources → install → enter server URL).

## [1.1.0] - 2026-07-08

### Added
- **EPUB client-side prefetch/cache** (`_epubPrefetch`): when a page is displayed, upcoming spine sections are prefetched in the background so navigation feels instant.
  - On every `relocated` event, `_epubSchedulePrefetch` queues the next 3 spine sections for background fetch, chained sequentially via `requestIdleCallback` (fallback: `setTimeout`) to avoid competing with active page loads.
  - For each section, `_epubPrefetchSection` fetches the XHTML, parses all `<img src>` references (resolving relative paths the same way as the renderer), and fetches each image into an in-memory `Map<url, blob: URL>`.
  - The existing `rendition.hooks.content` image-rewrite hook now checks this map first; if the image was prefetched, the blob: URL is used directly (no HTTP round-trip).
  - Already-visited images are never re-downloaded: the Map is checked before any fetch is initiated.
  - Cache is cleared (blob: URLs revoked, memory freed) when: (a) the user closes the reader, (b) the last page of the book is reached, or (c) a new book is opened.

## [1.0.6] - 2026-06-17

### Fixed
- **EPUB figures not displaying in reader**: For EPUBs with a flat zip structure (all files at the archive root, e.g. `OPS_images_Chap3xFig3-1.jpg`), epub.js's internal URL substitution silently failed to rewrite `<img src>` attributes to blob: URLs, so images rendered as broken boxes. Fixed with two changes:
  - New endpoint `GET /api/books/<id>/epub-resource/<path>` streams any resource directly from the EPUB zip by its internal path, with the correct MIME type and a 1-hour public cache.
  - A `rendition.hooks.content` hook runs after epub.js's own substitution pass; any `<img src>` still pointing at a raw relative path (not yet a `blob:`/`data:` URL) is rewritten to the new server endpoint. Paths are resolved against the chapter's location inside the zip so that subdirectory-relative references (e.g. `../images/fig.jpg`) map correctly. For EPUBs where epub.js already resolved images the hook is a no-op.

## [1.0.5] - 2026-06-17

### Fixed
- **PDF→EPUB images lost**: Calibre was invoked without a `cwd`, so any relative resource paths Calibre resolved internally could silently fail. Subprocess now runs from `os.path.dirname(pdf_path)`. Added `--dont-split-on-page-breaks` flag to reduce layout fragmentation. All Calibre output is now forwarded to the BookHaven log (`[calibre]` prefix) so image-related warnings are visible. Added `_fixup_epub_images()` post-processing step that: (1) detects broken `<img src=...>` paths in the converted HTML and rewrites them using basename lookup, and (2) detects images that Calibre placed in the EPUB zip but never referenced in any HTML file, and appends them as an extra "Extracted Images" page.

## [1.0.4] - 2026-06-09

### Fixed
- **Covers not showing**: DB paths were updated to `H:\Books\...` (Windows) but the cover cache files were still named after the old `/books/...` (Docker-era) MD5 hashes — causing the cover endpoint to always fall back to the SVG placeholder. Fixed in three places:
  - `scanner.get_cover_path`: tries the current hash first, then falls back to the legacy `/books/...` hash and renames the cache file in-place so the next request is fast.
  - `media_worker._save_cover`: same legacy-fallback rename, avoiding redundant re-extraction when the cover already exists under the old hash.
  - `_migrate_legacy_paths` (startup): now also renames cover cache files atomically alongside DB path updates.

## [1.0.3] - 2026-06-06

### Fixed
- **EPUB/optimize-epub "File not found"**: `_resolve_book_path` now reads `config.BOOKS_ROOT` directly instead of re-reading the env var with `""` as default, so legacy `/books/...` DB paths are always remapped correctly even when `BOOKS_ROOT` is not set in the environment.
- **PDF→EPUB conversion**: `ebook-convert` was called by name (not found in PATH). The call now uses `config.CALIBRE_CONVERT` which defaults to `C:\Program Files (x86)\Calibre2\ebook-convert.exe`.
- **Stale conversion state**: replaced fragile `tasklist /FI` shell command with a simple 15-minute elapsed-time guard.

### Changed
- **Docker/Jellyfin cleanup**: removed all Docker mount-point terminology, `JELLYFIN_URL`/`JELLYFIN_API_KEY` config vars, and related startup log line. `config._BOOKS_ROOT` (private) renamed to `config.BOOKS_ROOT` (public). Added `config.CALIBRE_CONVERT`.
- **Startup path migration**: `_migrate_legacy_paths()` now runs on every server start and bulk-updates any remaining `/books/...` paths in the DB to the current `BOOKS_ROOT`, making the translation fully transparent after one restart.

## [1.0.2] - 2026-06-05

### Fixed
- EPUB reader stayed stuck on "Loading EPUB..." when the server returned a non-200 response (e.g. 404 because `_resolve_book_path` did not apply its fallback when `BOOKS_ROOT` was unset). Two fixes: (1) `_resolve_book_path` now falls back to `H:\Books` instead of `""` when the `BOOKS_ROOT` env var is absent, matching the default in `config.py`; (2) `openEpub` now checks `resp.ok` before passing the buffer to epub.js, and wraps `book.opened` in a Promise that rejects on `openFailed` so errors surface immediately instead of hanging forever.

## [1.0.1] - 2026-05-08

### Fixed
- `GET /api/books/<id>/file` returned 404 for books whose path was stored using the legacy Docker mount prefix (`/books/`). Added `_resolve_book_path()` helper that transparently maps old Docker paths to the current `BOOKS_ROOT` filesystem location when running natively or via WSL. Same fix applied to `/api/books/<id>/comic-pages`, `/api/books/<id>/comic-page/<n>`, convert-epub, and optimize-epub endpoints.

## [1.0.0] - 2026-04-30

### Added
- Flask web server with EPUB / PDF / CBZ / CBR / MOBI reading support.
- AI genre classification via local Ollama (`llama3.1:latest`), with up to 3 genres per book.
- Book detail page with deep-linking (`#book/<id>`).
- Local user authentication with user creation and avatar selection (replaces Jellyfin auth).
- Series management: add to series, remove book from series, delete series.
- PDF-to-EPUB conversion with progress bar.
- MOBI cover extraction via PalmDB / EXTH record 201 parsing.
- Hash-based cover caching for EPUB / PDF / CBZ / CBR / MOBI.
- Library scanner with auto-enrichment (covers, descriptions, genres) for new books.
- Docker Compose deployment with `H:\Books` bind mount and named volume for the SQLite database (WAL-compatible).
- `__version__` exposed via `/api/version` endpoint and rendered in the page footer.
