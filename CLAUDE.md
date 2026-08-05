# BookHaven

Flask-based book reader web server with EPUB/PDF/CBZ/CBR/MOBI support, AI genre classification (Ollama), and local user auth. Runs **only** as a Docker container — never as a standalone Python server.

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
- **SQLite** en WAL mode dans un volume Docker nommé (`bookhaven_data`) — pas en bind mount (incompatible WAL sur Windows).
- **Ollama local** pour la classification de genre (modèle `llama3.1:latest`).
- **Bibliothèque** : `H:\Books` montée en `/books` dans le conteneur (lecture/écriture).
- **Auth locale** (pas Jellyfin) : table `users` avec sélection sur la page d'accueil.

## Lancement

Le projet ne tourne **que** via Docker Compose :

```bash
docker compose up -d
```

Ne **jamais** lancer `python bookhaven.py` en standalone — la version standalone a été supprimée du Startup Windows pour éviter les conflits.
