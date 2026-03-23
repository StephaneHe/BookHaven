"""Genre classification via local LLM (Ollama)."""
import json
import logging
import requests

logger = logging.getLogger("bookhaven.genre_ai")

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "llama3.1:latest"
TIMEOUT = 30  # seconds

KNOWN_GENRES = [
    "Article", "Aventure", "Biographie", "Bit-Lit", "Drame", "Espionnage",
    "Essai", "Fantastique", "Fantasy", "Historique", "Horreur", "Humour",
    "Jeunesse", "Philosophie", "Policier", "Poésie", "Romance",
    "Science-Fiction", "Thriller",
]

_PROMPT_TEMPLATE = """Tu es un classificateur de livres. À partir du titre et de l'auteur, donne le genre littéraire le plus adapté parmi cette liste :

{genres}

Réponds UNIQUEMENT avec le nom du genre, un seul mot ou expression, sans explication.
Si tu ne connais pas le livre ou que le genre ne correspond à aucun de la liste, réponds "Autres".

Titre : {title}
Auteur : {author}

Genre :"""


def classify_genre(title, author=""):
    """Ask the local LLM to classify a book's genre.

    Returns a genre string from KNOWN_GENRES, or "" if the LLM is unavailable.
    """
    if not title:
        return ""

    prompt = _PROMPT_TEMPLATE.format(
        genres=", ".join(KNOWN_GENRES),
        title=title,
        author=author or "inconnu",
    )

    try:
        resp = requests.post(
            OLLAMA_URL,
            json={
                "model": MODEL,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.1, "num_predict": 20},
            },
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        answer = resp.json().get("response", "").strip()

        # Match against known genres (case-insensitive)
        for genre in KNOWN_GENRES:
            if genre.lower() in answer.lower():
                return genre

        # If the LLM returned something not in the list
        if answer and answer.lower() not in ("autres", "unknown", "inconnu"):
            logger.info(f"LLM suggested unknown genre '{answer}' for '{title}' - using Autres")
        return "Autres"

    except requests.ConnectionError:
        logger.debug("Ollama not reachable - skipping AI genre classification")
        return ""
    except Exception as e:
        logger.debug(f"AI genre classification failed for '{title}': {e}")
        return ""
