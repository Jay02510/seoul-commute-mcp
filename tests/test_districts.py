import pytest

from sources.districts import DISTRICTS, grid, resolve


def test_all_25_districts():
    assert len(DISTRICTS) == 25


@pytest.mark.parametrize("name", ["Mapo", "mapo", "mapo-gu", "Mapo Gu", "마포", "마포구", " MAPO "])
def test_resolve_spellings(name):
    assert resolve(name) == "마포구"


def test_resolve_jung_gu():
    assert resolve("Jung-gu") == "중구"


@pytest.mark.parametrize("name", ["Bundang", "Incheon", "", "구"])
def test_resolve_unknown_raises(name):
    with pytest.raises(ValueError):
        resolve(name)


def test_grid():
    assert grid("Gangnam") == (61, 126)
