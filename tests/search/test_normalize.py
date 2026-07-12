"""Unit tests for Vietnamese-aware search normalization."""

from minder.core.context_engineering.search.normalize import (
    normalize_for_search,
    strip_diacritics,
)


def test_strip_diacritics_vietnamese():
    assert strip_diacritics("cà phê yên tĩnh") == "ca phe yen tinh"
    assert strip_diacritics("Đà Nẵng") == "Da Nang"
    assert strip_diacritics("đường") == "duong"


def test_normalize_lowercases_and_collapses_whitespace():
    assert normalize_for_search("  Quán   Cà Phê\n Yên Tĩnh ") == "quan ca phe yen tinh"


def test_normalize_is_idempotent_on_ascii():
    assert normalize_for_search("coffee shop") == "coffee shop"
