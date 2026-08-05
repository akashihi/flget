from collections.abc import Iterable, Mapping
from dataclasses import dataclass

import typer

from flget.mirror import BookEntry

# Static ISO-639-1 code -> English name map for the languages commonly found in
# Flibusta. The DB dumps carry no language-name table, so titles on the
# `filters languages` page come from here. Codes absent from this map render a
# blank title.
LANGUAGE_NAMES: dict[str, str] = {
    "ru": "Russian",
    "en": "English",
    "uk": "Ukrainian",
    "be": "Belarusian",
    "de": "German",
    "fr": "French",
    "es": "Spanish",
    "it": "Italian",
    "pl": "Polish",
    "pt": "Portuguese",
    "nl": "Dutch",
    "sv": "Swedish",
    "no": "Norwegian",
    "da": "Danish",
    "fi": "Finnish",
    "cs": "Czech",
    "sk": "Slovak",
    "bg": "Bulgarian",
    "sr": "Serbian",
    "hr": "Croatian",
    "sl": "Slovenian",
    "ro": "Romanian",
    "hu": "Hungarian",
    "el": "Greek",
    "tr": "Turkish",
    "lt": "Lithuanian",
    "lv": "Latvian",
    "et": "Estonian",
    "ka": "Georgian",
    "hy": "Armenian",
    "az": "Azerbaijani",
    "kk": "Kazakh",
    "uz": "Uzbek",
    "tg": "Tajik",
    "he": "Hebrew",
    "ar": "Arabic",
    "fa": "Persian",
    "zh": "Chinese",
    "ja": "Japanese",
    "ko": "Korean",
    "la": "Latin",
}


def language_display(lang: str) -> str:
    """Render a language code for display: ``Russian (ru)`` when a human-readable
    name is known, the bare code (no brackets) when it is not, and empty for an
    empty code."""
    if not lang:
        return ""
    name = LANGUAGE_NAMES.get(lang.lower())
    return f"{name} ({lang})" if name else lang


def genre_display_names(genres: Iterable[str], titles: Mapping[str, str]) -> list[str]:
    """Map genre codes to their human-readable titles, falling back to the raw
    code when no title is known. ``titles`` keys are lowercased codes (see the
    ``genre_titles`` build in ``dbsync``)."""
    return [titles.get(g.lower(), g) for g in genres]


_SIZE_UNITS = {
    "": 1,
    "B": 1,
    "K": 1024,
    "KB": 1024,
    "M": 1024**2,
    "MB": 1024**2,
    "G": 1024**3,
    "GB": 1024**3,
}


def parse_size(text: str) -> int:
    """Parse a human size (``500K``, ``2M``, ``1.5G``, ``KB/MB/GB`` or plain bytes)
    into a byte count. Units are base 1024. Raises ``typer.BadParameter`` on
    malformed input."""
    raw = text.strip()
    if not raw:
        raise typer.BadParameter(f"Invalid size: '{text}'")

    upper = raw.upper()
    unit = ""
    for suffix in ("KB", "MB", "GB", "B", "K", "M", "G"):
        if upper.endswith(suffix):
            unit = suffix
            upper = upper[: -len(suffix)]
            break

    number = upper.strip()
    try:
        value = float(number)
    except ValueError:
        raise typer.BadParameter(f"Invalid size: '{text}'") from None
    if value < 0:
        raise typer.BadParameter(f"Invalid size: '{text}'")

    return int(value * _SIZE_UNITS[unit])


@dataclass(frozen=True)
class BookFilter:
    genres: frozenset[str] = frozenset()
    formats: frozenset[str] = frozenset()
    languages: frozenset[str] = frozenset()
    year_from: int | None = None
    year_to: int | None = None
    min_size: int | None = None
    max_size: int | None = None

    def is_empty(self) -> bool:
        return not (
            self.genres
            or self.formats
            or self.languages
            or self.year_from is not None
            or self.year_to is not None
            or self.min_size is not None
            or self.max_size is not None
        )

    def matches(self, book: BookEntry) -> bool:
        if self.genres:
            book_genres = {g.lower() for g in book.genres}
            if not book_genres & self.genres:
                return False

        if self.formats and (book.ext or "").lower() not in self.formats:
            return False

        if self.languages and book.lang.lower() not in self.languages:
            return False

        if self.year_from is not None or self.year_to is not None:
            year = book.year
            if year is None:
                return False
            if self.year_from is not None and year < self.year_from:
                return False
            if self.year_to is not None and year > self.year_to:
                return False

        if self.min_size is not None and (
            book.filesize is None or book.filesize < self.min_size
        ):
            return False
        if self.max_size is not None and (
            book.filesize is None or book.filesize > self.max_size
        ):
            return False

        return True
