"""Seoul's 25 districts (구): Korean name, English aliases, KMA forecast grid (nx, ny).

KMA doesn't take lat/lon. It takes grid cells. Values below are the KMA grid
for each district office. Verify against KMA's official grid file
(기상청 동네예보 격자 좌표 엑셀) if something looks off.
"""

DISTRICTS = {
    # korean: (english, nx, ny)
    "종로구": ("Jongno", 60, 127),
    "중구": ("Jung", 60, 127),
    "용산구": ("Yongsan", 60, 126),
    "성동구": ("Seongdong", 61, 127),
    "광진구": ("Gwangjin", 62, 126),
    "동대문구": ("Dongdaemun", 61, 127),
    "중랑구": ("Jungnang", 62, 128),
    "성북구": ("Seongbuk", 61, 127),
    "강북구": ("Gangbuk", 61, 128),
    "도봉구": ("Dobong", 61, 129),
    "노원구": ("Nowon", 61, 129),
    "은평구": ("Eunpyeong", 59, 127),
    "서대문구": ("Seodaemun", 59, 127),
    "마포구": ("Mapo", 59, 127),
    "양천구": ("Yangcheon", 58, 126),
    "강서구": ("Gangseo", 58, 126),
    "구로구": ("Guro", 58, 125),
    "금천구": ("Geumcheon", 59, 124),
    "영등포구": ("Yeongdeungpo", 58, 126),
    "동작구": ("Dongjak", 59, 125),
    "관악구": ("Gwanak", 59, 125),
    "서초구": ("Seocho", 61, 125),
    "강남구": ("Gangnam", 61, 126),
    "송파구": ("Songpa", 62, 126),
    "강동구": ("Gangdong", 62, 126),
}


def resolve(name: str) -> str:
    """'Mapo', 'mapo-gu', '마포', '마포구' -> '마포구'. Raises ValueError if unknown."""
    q = name.strip().lower().replace("-gu", "").replace(" gu", "").replace(" ", "")
    for ko, (en, _, _) in DISTRICTS.items():
        if q in (ko, ko.removesuffix("구"), en.lower()):
            return ko
    raise ValueError(f"Unknown Seoul district: {name!r}. Try e.g. 'Mapo' or '마포구'.")


def grid(name: str) -> tuple[int, int]:
    _, nx, ny = DISTRICTS[resolve(name)]
    return nx, ny
