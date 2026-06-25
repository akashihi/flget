import re

import cyrtranslit
from unidecode import unidecode

# ISO 639-1 catalog language code -> cyrtranslit language code. Languages not
# listed fall through to "ru": the call is a no-op on already-Latin text (which
# unidecode then handles), and Russian dominates the library.
_CYR_LANG = {
    "ru": "ru",
    "uk": "ua",
    "be": "by",
    "bg": "bg",
    "sr": "sr",
    "mk": "mk",
    "mn": "mn",
    "tg": "tj",
    "el": "el",
}

# Apostrophes/quotes for ы/ъ/ь cleanup.
_APOSTROPHES = str.maketrans("", "", "'\"`’ʹ")
_ILLEGAL = re.compile(r"[^A-Za-z0-9-]+")
_DASHES = re.compile(r"-{2,}")

_MAX_TITLE = 120


def transliterate(text: str, lang: str = "ru") -> str:
    code = _CYR_LANG.get((lang or "ru").lower(), "ru")
    result = cyrtranslit.to_latin(text, code)
    result = unidecode(result)
    result = result.translate(_APOSTROPHES)
    result = result.replace(" ", "-").replace("_", "-")
    result = _ILLEGAL.sub("-", result)
    result = _DASHES.sub("-", result)
    return result.strip("-")


def build_book_filename(
    author: str | None,
    series: str | None,
    serno: int | None,
    title: str,
    book_id: int,
    ext: str,
    lang: str = "ru",
) -> str:
    parts: list[str] = []
    if author:
        author_part = transliterate(author, lang)
        if author_part:
            parts.append(author_part)
    if series:
        series_part = transliterate(series, lang)
        if series_part:
            parts.append(series_part)
            # serno 0 means "position unknown" in the catalog (~half of links);
            # keep the series name but drop the bogus number.
            if serno:
                parts.append(str(serno))
    title_part = transliterate(title, lang)[:_MAX_TITLE].strip("-")
    if title_part:
        parts.append(title_part)
    if not parts:
        return f"{book_id}.{ext}"
    return f"{'_'.join(parts)}.{book_id}.{ext}"
