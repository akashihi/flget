import pytest

from flget.naming import build_book_filename, transliterate


@pytest.mark.parametrize(
    ("text", "lang", "expected"),
    [
        ("Война и мир", "ru", "Vojna-i-mir"),
        ("Подъезд Объём Мальчик", "ru", "Podezd-Obyom-Malchik"),
        ("Щука Ёжик Юла Ящик", "ru", "SHHuka-YOzhik-Yula-Yashhik"),
        ("Київ Їжак Єва ґанок", "uk", "Kyjiv-Jizak-Jeva-ganok"),
        ("Беларусь ў", "be", "Belarus-u"),
        ("Ζεύς Αθήνα", "el", "Zeys-Athhna"),
        ("Café Ñandú", "en", "Cafe-Nandu"),
        ("O'Brien", "en", "OBrien"),
    ],
)
def test_transliterate(text: str, lang: str, expected: str) -> None:
    assert transliterate(text, lang) == expected


def test_transliterate_language_code_is_case_insensitive() -> None:
    assert transliterate("Київ", "UK") == transliterate("Київ", "uk") == "Kyjiv"


@pytest.mark.parametrize("lang", ["xx", "", "en"])
def test_transliterate_falls_back_to_russian(lang: str) -> None:
    assert transliterate("Київ", lang) == transliterate("Київ", "ru") == "Kiyiv"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Hello,  World!!  (2nd ed.)", "Hello-World-2nd-ed"),
        ("--a__b--", "a-b"),
        ("«Ёлка» — 2", "YOlka-2"),
        ("!!!", ""),
        ("", ""),
    ],
)
def test_transliterate_cleans_separators(text: str, expected: str) -> None:
    assert transliterate(text) == expected


def test_build_book_filename_all_parts() -> None:
    name = build_book_filename(
        "Лев Толстой", "Война и мир", 2, "Том второй", 123, "fb2"
    )
    assert name == "Lev-Tolstoj_Vojna-i-mir_2_Tom-vtoroj.123.fb2"


@pytest.mark.parametrize("serno", [0, None])
def test_build_book_filename_drops_unknown_serno(serno: int | None) -> None:
    name = build_book_filename(
        "Лев Толстой", "Война и мир", serno, "Том второй", 123, "fb2"
    )
    assert name == "Lev-Tolstoj_Vojna-i-mir_Tom-vtoroj.123.fb2"


def test_build_book_filename_without_author_and_series() -> None:
    assert build_book_filename(None, None, 4, "Книга", 7, "epub") == "Kniga.7.epub"


def test_build_book_filename_skips_parts_that_transliterate_to_nothing() -> None:
    # The series number goes with the series, so it is dropped too.
    assert build_book_filename("!!!", "???", 3, "Книга", 7, "fb2") == "Kniga.7.fb2"


def test_build_book_filename_falls_back_to_id() -> None:
    assert build_book_filename(None, None, None, "!!!", 5, "epub") == "5.epub"


def test_build_book_filename_truncates_title() -> None:
    # 119 letters, a separator, one more letter: the cut lands right after the
    # separator, which must not be left dangling.
    title = "а" * 119 + " б"
    assert build_book_filename(None, None, None, title, 8, "fb2") == (
        "a" * 119 + ".8.fb2"
    )


def test_build_book_filename_uses_language() -> None:
    assert build_book_filename("Київ", None, None, "Їжак", 1, "fb2", "uk") == (
        "Kyjiv_Jizak.1.fb2"
    )
