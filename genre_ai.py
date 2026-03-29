"""Genre classification via local LLM (Ollama)."""
import logging
import requests

logger = logging.getLogger("bookhaven.genre_ai")

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "llama3.1:latest"
TIMEOUT = 30  # seconds

KNOWN_GENRES = [
    "Article", "Autres", "Aventure", "Biographie", "Bit-Lit", "Comics",
    "Drame", "Espionnage", "Essai", "Fantastique", "Fantasy", "Historique",
    "Horreur", "Humour", "Jeunesse", "Philosophie", "Policier",
    "Romance", "Science-Fiction", "Sciences & Tech", "Thriller",
]

# Strict lookup: lowercase -> canonical
_CANONICAL = {g.lower(): g for g in KNOWN_GENRES}

_PROMPT_TEMPLATE = """Voici les informations sur un livre :

Titre : {title}
Auteur : {author}
{description_line}
Parmi cette liste UNIQUEMENT : {genres}

Quel est le genre de ce livre ? Choisis entre 1 et 3 genres de la liste ci-dessus, séparés par des virgules. Le genre principal en premier. Réponds uniquement avec les genres, sans explication.

Genre :"""


def classify_genre(title, author="", description=""):
    """Ask the local LLM to classify a book's genres.

    Returns a comma-separated string of 1-3 genres from KNOWN_GENRES,
    or "" if the LLM is unavailable.
    """
    if not title:
        return ""

    desc_line = ""
    if description:
        # Truncate to avoid blowing up the prompt
        desc_line = "Description : " + description[:300]

    prompt = _PROMPT_TEMPLATE.format(
        genres=", ".join(KNOWN_GENRES),
        title=title,
        author=author or "inconnu",
        description_line=desc_line,
    )

    try:
        resp = requests.post(
            OLLAMA_URL,
            json={
                "model": MODEL,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.0, "num_predict": 30},
            },
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        answer = resp.json().get("response", "").strip().strip(".")

        # Parse comma-separated answer, keep only known genres
        matched = []
        for part in answer.split(","):
            candidate = part.strip().lower()
            if candidate in _CANONICAL and _CANONICAL[candidate] not in matched:
                matched.append(_CANONICAL[candidate])

        # Fuzzy fallback: scan for known genre names in the full answer
        if not matched:
            low = answer.lower()
            for genre in KNOWN_GENRES:
                if genre.lower() in low and genre not in matched:
                    matched.append(genre)

        if not matched:
            logger.info(f"LLM returned '{answer}' for '{title}' - no known genres found")
            return "Autres"

        return ", ".join(matched[:3])

    except requests.ConnectionError:
        logger.debug("Ollama not reachable - skipping AI genre classification")
        return ""
    except Exception as e:
        logger.debug(f"AI genre classification failed for '{title}': {e}")
        return ""
