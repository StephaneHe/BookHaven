# BookHaven

Flask-based book reader web server with EPUB/PDF/CBZ/CBR/MOBI support, AI genre classification (Ollama), and local user auth. Tourne comme **processus Python standalone sous Windows** — Docker n'est pas installé sur la machine et n'est plus utilisé.

## Règles standing du fleet (2026-04-30)

### Règle 1 — Versioning visible et incrémenté
- Source de vérité : `__version__` dans `bookhaven.py` (module principal Python).
- Visibilité : footer de `templates/index.html` (`BookHaven v{{ version }}`) **et** endpoint `GET /api/version` qui retourne `{"version": "X.Y.Z"}`.
- Démarrage : 1.0.0.
- Bump à **chaque** release/commit fonctionnel, sans exception :
  - patch (1.0.0 → 1.0.1) pour fix ou petit changement
  - minor (→ 1.1.0) pour nouvelle feature
  - major (→ 2.0.0) pour breaking change

### Règle 2 — Changelog
- `CHANGELOG.md` à la racine, format [Keep a Changelog](https://keepachangelog.com).
- Sections autorisées : `Added`, `Changed`, `Fixed`, `Removed`, `Deprecated`, `Security`.
- En-tête d'entrée : `## [X.Y.Z] - YYYY-MM-DD`.
- Couplage : aucune release sans bump `__version__` **ET** entrée changelog correspondante.

## Architecture

- **Python/Flask** monolithe (`bookhaven.py`) avec modules séparés : `database.py`, `scanner.py`, `genre_ai.py`, `media_worker.py`, `config.py`.
- **SQLite** en WAL mode : `data/bookhaven.db` (chemin `config.DB_PATH`).
- **Ollama local** pour la classification de genre (modèle `llama3.1:latest`).
- **Bibliothèque** : `H:\Books` (sous-dossiers `Books`, `Comics`, `Education`, `Magazines`, `Professionel`).
- **Auth locale** (pas Jellyfin) : table `users` avec sélection sur la page d'accueil, sans mot de passe.

## Lancement

Processus Python standalone, port 8097, piloté par le Planificateur de tâches Windows :

| Tâche | Action | Rôle |
|---|---|---|
| `BookHaven-server` | `scripts\start-server.cmd` | Démarre au logon. Idempotent : tue le process sur le port 8097 puis relance. |
| `BookHaven-watchdog` | `node scripts\bookhaven-watchdog.mjs` | Sonde `http://127.0.0.1:8097/` toutes les 10 s, relance après 2 échecs consécutifs. |

Redémarrage manuel :

```powershell
# Arrêter proprement le watchdog avant toute intervention longue,
# sinon il relancera le serveur en parallèle.
New-Item C:\Dev\BookHaven\logs\watchdog.stop -ItemType File
& C:\Dev\BookHaven\scripts\start-server.cmd
Start-ScheduledTask -TaskName BookHaven-watchdog
```

`debug=False` : **aucun rechargement à chaud du code Python**. Toute modification de
`.py` exige un redémarrage. Seuls les templates se rechargent seuls
(`TEMPLATES_AUTO_RELOAD=True`).

## Configuration

`.env` à la racine (non versionné, couvert par `.gitignore`) — voir `.env.example`.

- `BOOKHAVEN_SECRET_KEY` : **obligatoire**, minimum 32 caractères. `config.py` lève
  une `RuntimeError` au démarrage si la clé est absente, trop courte, ou égale à
  l'ancienne valeur de dev. Génération : `python -c "import secrets; print(secrets.token_hex(32))"`.
- `BOOKS_ROOT` : racine de la bibliothèque.

⚠️ **Dette connue** : `BOOKS_ROOT` vaut actuellement `/mnt/h/Books` (reliquat WSL/Docker).
Les lectures fonctionnent grâce à `_resolve_book_path()`, qui retraduit `/mnt/X/...` en
`X:\...`, mais les **écritures** (upload) ne passent pas par cette traduction et créent
des dossiers fantômes `I:\mnt\h\Books\...`. Corriger `BOOKS_ROOT` en `H:\Books` implique
une migration des chemins des ~9500 livres en base.
