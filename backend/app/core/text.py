import re
import unicodedata


def normalize(text: str) -> str:
    """Lowercase, strip accents and collapse whitespace, for accent-insensitive matching."""
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    without_accents = "".join(char for char in decomposed if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", without_accents).strip()


def slugify(text: str) -> str:
    """Turn text into a tag slug (Rejeição 539 -> rejeicao-539).

    Used both when storing and when filtering tags, so the two always agree.
    """
    return "-".join(normalize(text).split())


def contains_phrase(normalized_text: str, phrase: str) -> bool:
    """Whole-word match of `phrase` inside text already passed through `normalize`."""
    pattern = rf"(?<!\w){re.escape(normalize(phrase))}(?!\w)"
    return re.search(pattern, normalized_text) is not None
