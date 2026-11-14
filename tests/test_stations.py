"""English station names are translated before any API call."""
import asyncio

import pytest

import server
from sources import stations
from sources.http import check_name


@pytest.mark.parametrize("name, expected", [
    ("Gangnam", "강남"),
    ("Hongik Univ. Station", "홍대입구"),
    ("hongdae", "홍대입구"),
    ("Seoul Station", "서울"),
    ("Euljiro 1(il)-ga", "을지로입구"),
    ("Dongdaemun History & Culture Park", "동대문역사문화공원"),
    ("COEX", "삼성"),
    ("Gangnam-gu Office", "강남구청"),
    ("강남역", "강남"),                      # Korean passes through, '역' dropped
    ("  공덕 ", "공덕"),
])
def test_check_name_translates(name, expected):
    assert check_name(name) == expected


def test_unknown_english_name_is_a_clear_error():
    with pytest.raises(ValueError, match="use the Korean name"):
        check_name("Atlantis")


def test_every_value_is_korean():
    assert all(not any(c.isascii() and c.isalpha() for c in v) for v in stations._NAMES.values())


def test_tool_returns_error_text_for_unknown_name():
    out = asyncio.run(server.next_trains("Atlantis"))
    assert "use the Korean name" in out
