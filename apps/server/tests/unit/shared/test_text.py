# ruff: noqa: RUF001 - the odd characters are the point
from public_atlas.shared.text import name_key, normalize_text, repair_mojibake


def test_mojibake_is_repaired_and_clean_text_left_alone():
    assert repair_mojibake("Mattice-Val CÃ´tÃ©") == "Mattice-Val Côté"
    assert repair_mojibake("CafÃ©") == "Café"
    # Cyrillic through Windows-1252, with a byte that encoding leaves undefined.
    assert repair_mojibake("Ð\u009cÐ¾Ñ\u0081ÐºÐ²Ð°") == ("Москва")
    assert repair_mojibake("Côté, plain – text") == "Côté, plain – text"
    # A run that does not decode as UTF-8 stays as it is.
    assert repair_mojibake("ÃÃ") == "ÃÃ"


def test_normalize_text_folds_case_whitespace_and_typographic_punctuation():
    assert normalize_text("  Elm–Oak  Township ") == "elm-oak township"
    assert normalize_text("“Quoted” ‘word’") == "\"quoted\" 'word'"
    assert normalize_text("CafÃ©") == "café"


def test_name_key_reads_joiners_as_spaces_and_ampersand_as_a_word():
    assert name_key("Elm/Oak") == name_key("Elm-Oak") == "elm oak"
    assert name_key("Elm&Oak") == name_key("Elm & Oak") == "elm & oak"
