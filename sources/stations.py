"""English station names to the Korean names the Seoul subway APIs expect.

The realtime-arrivals and route APIs only accept Korean names ('강남',
'홍대입구'). Models usually translate, but not always, and people type English.
This table covers the stations visitors and commuters ask about most; anything
else must be given in Korean. Values are the API names without '역' (the route
lookup adds '역' back for stations like 서울역 that keep it).
"""
import re

_NAMES = {
    # Line 2 loop
    "city hall": "시청", "euljiro 1 ga": "을지로입구", "euljiro ipgu": "을지로입구",
    "euljiro 3 ga": "을지로3가", "euljiro 4 ga": "을지로4가",
    "dongdaemun history and culture park": "동대문역사문화공원", "ddp": "동대문역사문화공원",
    "sindang": "신당", "sangwangsimni": "상왕십리", "wangsimni": "왕십리",
    "hanyang university": "한양대", "ttukseom": "뚝섬", "seongsu": "성수",
    "konkuk university": "건대입구", "kondae": "건대입구", "guui": "구의", "gangbyeon": "강변",
    "jamsillaru": "잠실나루", "jamsil naru": "잠실나루", "jamsil": "잠실", "jamsilsaenae": "잠실새내",
    "sports complex": "종합운동장", "samseong": "삼성", "samsung": "삼성", "coex": "삼성",
    "seolleung": "선릉", "yeoksam": "역삼", "gangnam": "강남", "gyodae": "교대",
    "seocho": "서초", "bangbae": "방배", "sadang": "사당", "nakseongdae": "낙성대",
    "seoul national university": "서울대입구", "snu": "서울대입구", "sillim": "신림",
    "guro digital complex": "구로디지털단지", "daerim": "대림", "sindorim": "신도림",
    "mullae": "문래", "yeongdeungpo gu office": "영등포구청", "dangsan": "당산",
    "hapjeong": "합정", "hongik university": "홍대입구", "hongdae": "홍대입구",
    "sinchon": "신촌", "ewha womans university": "이대", "ewha": "이대", "ahyeon": "아현",
    "chungjeongno": "충정로", "sangsu": "상수", "mangwon": "망원",
    # Line 1 / central
    "seoul": "서울", "seoul station": "서울", "jonggak": "종각", "jongno 3 ga": "종로3가",
    "jongno 5 ga": "종로5가", "dongdaemun": "동대문", "dongmyo": "동묘앞", "dongmyo ap": "동묘앞",
    "sinseol dong": "신설동", "cheongnyangni": "청량리", "hoegi": "회기",
    "yongsan": "용산", "noryangjin": "노량진", "yeongdeungpo": "영등포",
    "gasan digital complex": "가산디지털단지",
    # Line 3 / 4
    "gyeongbokgung": "경복궁", "anguk": "안국", "chungmuro": "충무로", "myeongdong": "명동",
    "hoehyeon": "회현", "namdaemun market": "회현", "hyehwa": "혜화", "daehangno": "혜화",
    "sinsa": "신사", "apgujeong": "압구정", "express bus terminal": "고속터미널",
    "yangjae": "양재", "nambu bus terminal": "남부터미널", "suseo": "수서",
    "samgakji": "삼각지", "ichon": "이촌", "suyu": "수유", "mia": "미아", "nowon": "노원",
    # Line 5 / 6 / 7 / 9 / Suin-Bundang
    "gwanghwamun": "광화문", "gongdeok": "공덕", "mapo": "마포", "yeouido": "여의도",
    "yeouinaru": "여의나루", "gimpo airport": "김포공항", "itaewon": "이태원",
    "noksapyeong": "녹사평", "hangangjin": "한강진", "digital media city": "디지털미디어시티",
    "dmc": "디지털미디어시티", "cheongdam": "청담", "gangnam gu office": "강남구청",
    "nonhyeon": "논현", "sinnonhyeon": "신논현", "seonjeongneung": "선정릉",
    "bongeunsa": "봉은사", "apgujeong rodeo": "압구정로데오", "seoul forest": "서울숲",
    "seokchon": "석촌", "songpa": "송파", "garak market": "가락시장", "magongnaru": "마곡나루",
}

_DROP = re.compile(r"\b(station|stn|subway|metro|line \d+)\b")


def _key(name: str) -> str:
    """'Hongik Univ. Station' -> 'hongik university'; 'Euljiro 1(il)-ga' -> 'euljiro 1 ga'."""
    s = name.lower().replace("&", " and ").replace("'", "")
    s = re.sub(r"\(.*?\)", " ", s)
    s = re.sub(r"\buniv\b\.?", "university", s)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    s = _DROP.sub(" ", s)
    return " ".join(s.split())


def to_korean(name: str) -> str:
    """Korean names pass through; known English names are translated; other
    English raises ValueError with a hint (the tool returns it as an error)."""
    if not re.search(r"[A-Za-z]", name):
        return name
    ko = _NAMES.get(_key(name))
    if ko is None:
        raise ValueError(f"unknown English station name {name.strip()!r}: "
                         "use the Korean name, e.g. '강남', '홍대입구'")
    return ko
