from __future__ import annotations

import csv
import html
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable
from urllib.parse import urljoin, urlparse, parse_qs, urlencode, urlunparse

import requests
from bs4 import BeautifulSoup

BASE = "https://194939.x.yupoo.com"
OUT = Path("out")
OUT.mkdir(exist_ok=True)

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0 Safari/537.36"
HEADERS = {"User-Agent": UA, "Referer": "https://x.yupoo.com/", "Accept-Language": "en-US,en;q=0.9"}

# We intentionally keep only football/team shirts.  Generic fashion, shorts,
# training wear, jackets and other sports are excluded even if they share a category.
EXCLUDE_RE = re.compile(
    r"\b(shorts|short pants?|trousers?|pants?|jacket|jackets|tracksuits?|track suits?|"
    r"training suits?|windbreakers?|hoodies?|sweatshirts?|polos?|socks?|caps?|hats?|bags?|"
    r"perfumes?|shoes?|sneakers?|basketball|nba|rugby|formula\s*1|\bf1\b)\b",
    re.I,
)
STRONG_SHIRT_RE = re.compile(r"\b(jersey|shirt|football|soccer|kit top|goalkeeper)\b", re.I)
CATEGORY_INCLUDE_RE = re.compile(
    r"world cup|brasileiro|premier league|la liga|serie a|bundesliga|ligue 1|national team|"
    r"jersey|football|soccer|retro|player version|women|kids|long sleeves?|other team|shirt",
    re.I,
)
CATEGORY_EXCLUDE_RE = re.compile(
    r"training|jacket|windbreaker|shorts|socks|perfume|nba|basketball|rugby|formula|\bf1\b|"
    r"shoes|sneaker|bag|cap|hat|polo",
    re.I,
)

LEAGUE_BY_CATEGORY = [
    (re.compile(r"premier league", re.I), ("England", "Premier League")),
    (re.compile(r"la liga", re.I), ("Spain", "La Liga")),
    (re.compile(r"bundesliga", re.I), ("Germany", "Bundesliga")),
    (re.compile(r"ligue\s*1", re.I), ("France", "Ligue 1")),
    (re.compile(r"brasileiro", re.I), ("Brazil", "Brasileiro Série A")),
    (re.compile(r"serie\s*a", re.I), ("Italy", "Serie A")),
    (re.compile(r"world cup|national team", re.I), ("International", "National Teams")),
]

# Canonical club label -> (country, league, aliases).  The mapping is deliberately
# broader than the six headline leagues because the supplier has "other team" albums too.
CLUBS: dict[str, tuple[str, str, list[str]]] = {
    # England
    "Arsenal": ("England", "Premier League", ["arsenal"]),
    "Aston Villa": ("England", "Premier League", ["aston villa", "villa"]),
    "Bournemouth": ("England", "Premier League", ["bournemouth"]),
    "Brentford": ("England", "Premier League", ["brentford"]),
    "Brighton & Hove Albion": ("England", "Premier League", ["brighton", "brighton hove"]),
    "Burnley": ("England", "Premier League", ["burnley"]),
    "Chelsea": ("England", "Premier League", ["chelsea"]),
    "Crystal Palace": ("England", "Premier League", ["crystal palace"]),
    "Everton": ("England", "Premier League", ["everton"]),
    "Fulham": ("England", "Premier League", ["fulham"]),
    "Leeds United": ("England", "Premier League", ["leeds united", "leeds"]),
    "Liverpool": ("England", "Premier League", ["liverpool"]),
    "Manchester City": ("England", "Premier League", ["manchester city", "man city"]),
    "Manchester United": ("England", "Premier League", ["manchester united", "man utd", "man united"]),
    "Newcastle United": ("England", "Premier League", ["newcastle united", "newcastle"]),
    "Nottingham Forest": ("England", "Premier League", ["nottingham forest", "nott'm forest"]),
    "Sunderland": ("England", "Premier League", ["sunderland"]),
    "Tottenham Hotspur": ("England", "Premier League", ["tottenham hotspur", "tottenham", "spurs"]),
    "West Ham United": ("England", "Premier League", ["west ham united", "west ham"]),
    "Wolverhampton Wanderers": ("England", "Premier League", ["wolverhampton", "wolves"]),
    "Leicester City": ("England", "English Clubs", ["leicester city", "leicester"]),
    "Southampton": ("England", "English Clubs", ["southampton"]),
    "Ipswich Town": ("England", "English Clubs", ["ipswich"]),
    "Blackburn Rovers": ("England", "English Clubs", ["blackburn"]),
    "West Bromwich Albion": ("England", "English Clubs", ["west brom"]),
    # Spain
    "Real Madrid": ("Spain", "La Liga", ["real madrid"]),
    "FC Barcelona": ("Spain", "La Liga", ["barcelona", "barca", "barça"]),
    "Atlético Madrid": ("Spain", "La Liga", ["atletico madrid", "atlético madrid", "atl madrid"]),
    "Athletic Club": ("Spain", "La Liga", ["athletic bilbao", "athletic club"]),
    "Real Betis": ("Spain", "La Liga", ["real betis", "betis"]),
    "Real Sociedad": ("Spain", "La Liga", ["real sociedad"]),
    "Sevilla": ("Spain", "La Liga", ["sevilla"]),
    "Valencia": ("Spain", "La Liga", ["valencia"]),
    "Villarreal": ("Spain", "La Liga", ["villarreal"]),
    "Girona": ("Spain", "La Liga", ["girona"]),
    "Celta Vigo": ("Spain", "La Liga", ["celta vigo", "celta"]),
    "Rayo Vallecano": ("Spain", "La Liga", ["rayo vallecano", "rayo"]),
    "Espanyol": ("Spain", "La Liga", ["espanyol"]),
    "Mallorca": ("Spain", "La Liga", ["mallorca"]),
    "Osasuna": ("Spain", "La Liga", ["osasuna"]),
    "Getafe": ("Spain", "La Liga", ["getafe"]),
    "Alavés": ("Spain", "La Liga", ["alaves", "alavés"]),
    "Real Oviedo": ("Spain", "La Liga", ["real oviedo", "oviedo"]),
    "Levante": ("Spain", "La Liga", ["levante"]),
    "Elche": ("Spain", "La Liga", ["elche"]),
    # Italy
    "Inter Milan": ("Italy", "Serie A", ["inter milan", "internazionale", "inter"]),
    "AC Milan": ("Italy", "Serie A", ["ac milan", "milan"]),
    "Juventus": ("Italy", "Serie A", ["juventus", "juve"]),
    "Napoli": ("Italy", "Serie A", ["napoli"]),
    "AS Roma": ("Italy", "Serie A", ["as roma", "roma"]),
    "Lazio": ("Italy", "Serie A", ["lazio"]),
    "Atalanta": ("Italy", "Serie A", ["atalanta"]),
    "Fiorentina": ("Italy", "Serie A", ["fiorentina"]),
    "Bologna": ("Italy", "Serie A", ["bologna"]),
    "Torino": ("Italy", "Serie A", ["torino"]),
    "Udinese": ("Italy", "Serie A", ["udinese"]),
    "Genoa": ("Italy", "Serie A", ["genoa"]),
    "Parma": ("Italy", "Serie A", ["parma"]),
    "Como": ("Italy", "Serie A", ["como"]),
    "Cagliari": ("Italy", "Serie A", ["cagliari"]),
    "Hellas Verona": ("Italy", "Serie A", ["hellas verona", "verona"]),
    "Lecce": ("Italy", "Serie A", ["lecce"]),
    "Sassuolo": ("Italy", "Serie A", ["sassuolo"]),
    "Pisa": ("Italy", "Serie A", ["pisa"]),
    "Cremonese": ("Italy", "Serie A", ["cremonese"]),
    # Germany
    "Bayern Munich": ("Germany", "Bundesliga", ["bayern munich", "bayern münchen", "bayern"]),
    "Borussia Dortmund": ("Germany", "Bundesliga", ["borussia dortmund", "dortmund", "bvb"]),
    "Bayer Leverkusen": ("Germany", "Bundesliga", ["bayer leverkusen", "leverkusen"]),
    "RB Leipzig": ("Germany", "Bundesliga", ["rb leipzig", "leipzig"]),
    "Eintracht Frankfurt": ("Germany", "Bundesliga", ["eintracht frankfurt", "frankfurt"]),
    "VfB Stuttgart": ("Germany", "Bundesliga", ["vfb stuttgart", "stuttgart"]),
    "Werder Bremen": ("Germany", "Bundesliga", ["werder bremen", "bremen"]),
    "Borussia Mönchengladbach": ("Germany", "Bundesliga", ["monchengladbach", "mönchengladbach", "gladbach"]),
    "VfL Wolfsburg": ("Germany", "Bundesliga", ["wolfsburg"]),
    "SC Freiburg": ("Germany", "Bundesliga", ["freiburg"]),
    "Mainz 05": ("Germany", "Bundesliga", ["mainz 05", "mainz"]),
    "Union Berlin": ("Germany", "Bundesliga", ["union berlin"]),
    "FC Augsburg": ("Germany", "Bundesliga", ["augsburg"]),
    "Hoffenheim": ("Germany", "Bundesliga", ["hoffenheim"]),
    "St. Pauli": ("Germany", "Bundesliga", ["st pauli", "st. pauli"]),
    "Hamburger SV": ("Germany", "Bundesliga", ["hamburger sv", "hamburg"]),
    "1. FC Köln": ("Germany", "Bundesliga", ["koln", "köln", "cologne"]),
    "Schalke 04": ("Germany", "German Clubs", ["schalke 04", "schalke"]),
    # France
    "Paris Saint-Germain": ("France", "Ligue 1", ["paris saint-germain", "paris saint germain", "psg"]),
    "Marseille": ("France", "Ligue 1", ["marseille", "olympique marseille"]),
    "Lyon": ("France", "Ligue 1", ["olympique lyon", "lyon"]),
    "Monaco": ("France", "Ligue 1", ["as monaco", "monaco"]),
    "Lille": ("France", "Ligue 1", ["lille"]),
    "Nice": ("France", "Ligue 1", ["ogc nice", "nice"]),
    "Lens": ("France", "Ligue 1", ["rc lens", "lens"]),
    "Rennes": ("France", "Ligue 1", ["rennes"]),
    "Strasbourg": ("France", "Ligue 1", ["strasbourg"]),
    "Nantes": ("France", "Ligue 1", ["nantes"]),
    "Toulouse": ("France", "Ligue 1", ["toulouse"]),
    "Brest": ("France", "Ligue 1", ["brest"]),
    "Auxerre": ("France", "Ligue 1", ["auxerre"]),
    # Brazil
    "Flamengo": ("Brazil", "Brasileiro Série A", ["flamengo"]),
    "Palmeiras": ("Brazil", "Brasileiro Série A", ["palmeiras"]),
    "Corinthians": ("Brazil", "Brasileiro Série A", ["corinthians"]),
    "São Paulo": ("Brazil", "Brasileiro Série A", ["sao paulo", "são paulo"]),
    "Santos": ("Brazil", "Brasileiro Série A", ["santos"]),
    "Fluminense": ("Brazil", "Brasileiro Série A", ["fluminense"]),
    "Botafogo": ("Brazil", "Brasileiro Série A", ["botafogo"]),
    "Vasco da Gama": ("Brazil", "Brasileiro Série A", ["vasco da gama", "vasco"]),
    "Grêmio": ("Brazil", "Brasileiro Série A", ["gremio", "grêmio"]),
    "Internacional": ("Brazil", "Brasileiro Série A", ["internacional", "inter porto alegre"]),
    "Cruzeiro": ("Brazil", "Brasileiro Série A", ["cruzeiro"]),
    "Atlético Mineiro": ("Brazil", "Brasileiro Série A", ["atletico mineiro", "atlético mineiro", "atletico mg"]),
    "Bahia": ("Brazil", "Brasileiro Série A", ["bahia"]),
    "Fortaleza": ("Brazil", "Brasileiro Série A", ["fortaleza"]),
    "Ceará": ("Brazil", "Brasileiro Série A", ["ceara", "ceará"]),
    "Sport Recife": ("Brazil", "Brasileiro Série A", ["sport recife"]),
    "Vitória": ("Brazil", "Brasileiro Série A", ["vitoria", "vitória"]),
    "Athletico Paranaense": ("Brazil", "Brazilian Clubs", ["athletico paranaense", "athletico pr"]),
    # Portugal
    "Benfica": ("Portugal", "Primeira Liga", ["benfica"]),
    "FC Porto": ("Portugal", "Primeira Liga", ["fc porto", "porto"]),
    "Sporting CP": ("Portugal", "Primeira Liga", ["sporting cp", "sporting lisbon", "sporting"]),
    "Braga": ("Portugal", "Primeira Liga", ["braga"]),
    # Netherlands
    "Ajax": ("Netherlands", "Eredivisie", ["ajax"]),
    "PSV Eindhoven": ("Netherlands", "Eredivisie", ["psv eindhoven", "psv"]),
    "Feyenoord": ("Netherlands", "Eredivisie", ["feyenoord"]),
    # Scotland
    "Celtic": ("Scotland", "Scottish Premiership", ["celtic"]),
    "Rangers": ("Scotland", "Scottish Premiership", ["rangers"]),
    # Turkey
    "Galatasaray": ("Turkey", "Süper Lig", ["galatasaray"]),
    "Fenerbahçe": ("Turkey", "Süper Lig", ["fenerbahce", "fenerbahçe"]),
    "Beşiktaş": ("Turkey", "Süper Lig", ["besiktas", "beşiktaş"]),
    # Saudi Arabia
    "Al Nassr": ("Saudi Arabia", "Saudi Pro League", ["al nassr", "al-nassr"]),
    "Al Hilal": ("Saudi Arabia", "Saudi Pro League", ["al hilal", "al-hilal"]),
    "Al Ittihad": ("Saudi Arabia", "Saudi Pro League", ["al ittihad", "al-ittihad"]),
    "Al Ahli": ("Saudi Arabia", "Saudi Pro League", ["al ahli", "al-ahli"]),
    # USA / MLS
    "Inter Miami": ("United States", "MLS", ["inter miami"]),
    "LA Galaxy": ("United States", "MLS", ["la galaxy", "los angeles galaxy"]),
    "Los Angeles FC": ("United States", "MLS", ["los angeles fc", "lafc"]),
    "Minnesota United": ("United States", "MLS", ["minnesota united"]),
    "Atlanta United": ("United States", "MLS", ["atlanta united"]),
    "Seattle Sounders": ("United States", "MLS", ["seattle sounders"]),
    "New York City FC": ("United States", "MLS", ["new york city fc", "nycfc"]),
    # Mexico
    "Club América": ("Mexico", "Liga MX", ["club america", "club américa", "america mexico"]),
    "Guadalajara": ("Mexico", "Liga MX", ["chivas", "guadalajara"]),
    "Tigres UANL": ("Mexico", "Liga MX", ["tigres uanl", "tigres"]),
    "Monterrey": ("Mexico", "Liga MX", ["monterrey", "rayados"]),
    "Cruz Azul": ("Mexico", "Liga MX", ["cruz azul"]),
    "Pumas UNAM": ("Mexico", "Liga MX", ["pumas unam", "pumas"]),
    # Argentina
    "Boca Juniors": ("Argentina", "Liga Profesional Argentina", ["boca juniors", "boca"]),
    "River Plate": ("Argentina", "Liga Profesional Argentina", ["river plate"]),
    "Racing Club": ("Argentina", "Liga Profesional Argentina", ["racing club"]),
    "Independiente": ("Argentina", "Liga Profesional Argentina", ["independiente"]),
    # Others frequently represented
    "Olympiacos": ("Greece", "Super League Greece", ["olympiacos"]),
    "Panathinaikos": ("Greece", "Super League Greece", ["panathinaikos"]),
    "Red Star Belgrade": ("Serbia", "Serbian SuperLiga", ["red star belgrade", "crvena zvezda"]),
    "Dinamo Zagreb": ("Croatia", "Croatian Football League", ["dinamo zagreb"]),
    "Shakhtar Donetsk": ("Ukraine", "Ukrainian Premier League", ["shakhtar donetsk", "shakhtar"]),
    "Dynamo Kyiv": ("Ukraine", "Ukrainian Premier League", ["dynamo kyiv", "dynamo kiev"]),
}

NATIONAL_TEAMS = [
    "Argentina", "Australia", "Austria", "Albania", "Algeria", "Angola", "Belgium", "Bolivia", "Bosnia and Herzegovina",
    "Brazil", "Cameroon", "Canada", "Cape Verde", "Chile", "China", "Colombia", "Costa Rica", "Croatia", "Czech Republic",
    "Denmark", "Ecuador", "Egypt", "England", "France", "Germany", "Ghana", "Greece", "Hungary", "Iceland", "India",
    "Indonesia", "Iran", "Iraq", "Ireland", "Israel", "Italy", "Ivory Coast", "Côte d'Ivoire", "Jamaica", "Japan", "Jordan",
    "Mexico", "Morocco", "Netherlands", "New Zealand", "Nigeria", "North Macedonia", "Northern Ireland", "Norway", "Panama",
    "Paraguay", "Peru", "Poland", "Portugal", "Qatar", "Romania", "Saudi Arabia", "Scotland", "Senegal", "Serbia", "Slovakia",
    "Slovenia", "South Africa", "South Korea", "Spain", "Sweden", "Switzerland", "Tunisia", "Turkey", "Ukraine", "United States",
    "Uruguay", "Uzbekistan", "Venezuela", "Wales"
]
NATIONAL_ALIASES = {
    "usa": "United States", "u.s.a": "United States", "usmnt": "United States", "korea": "South Korea",
    "cote d'ivoire": "Côte d'Ivoire", "cote d ivoire": "Côte d'Ivoire", "ivory coast": "Côte d'Ivoire",
    "czechia": "Czech Republic", "bosnia": "Bosnia and Herzegovina",
}

@dataclass
class Album:
    album_id: str
    source_title: str
    source_url: str
    category_id: str
    category_name: str
    thumbnail: str = ""


def session() -> requests.Session:
    s = requests.Session()
    s.headers.update(HEADERS)
    return s


def fetch(url: str, attempts: int = 5) -> str:
    last = None
    for i in range(attempts):
        try:
            r = requests.get(url, headers=HEADERS, timeout=35)
            if r.status_code == 200 and len(r.text) > 100:
                return r.text
            last = RuntimeError(f"HTTP {r.status_code} {url}")
        except Exception as e:
            last = e
        time.sleep(min(1.5 * (i + 1), 8))
    raise RuntimeError(f"Fetch failed after {attempts} attempts: {url}: {last}")


def clean_text(s: str) -> str:
    s = html.unescape(s or "")
    s = re.sub(r"[\u4e00-\u9fff]+", " ", s)
    s = re.sub(r"\b(?:whats?app|wechat|supplier|factory)\b.*", "", s, flags=re.I)
    s = re.sub(r"\b(?:QQ|VX|TEL)\s*[:：]?\s*[\w+\-]{5,}\b", "", s, flags=re.I)
    s = re.sub(r"\b\d{7,}\b", "", s)
    s = re.sub(r"\s+", " ", s).strip(" -_|/.,")
    return s


def canonical_album_url(href: str) -> str:
    u = urljoin(BASE, href)
    p = urlparse(u)
    qs = parse_qs(p.query)
    keep = {}
    if qs.get("uid"):
        keep["uid"] = qs["uid"][0]
    return urlunparse((p.scheme or "https", p.netloc or "194939.x.yupoo.com", p.path, "", urlencode(keep), ""))


def normalize_image(src: str) -> str:
    if not src:
        return ""
    src = html.unescape(src.strip())
    if src.startswith("//"):
        src = "https:" + src
    elif src.startswith("/"):
        src = urljoin(BASE, src)
    return src


def discover_categories() -> list[dict]:
    raw = fetch(BASE + "/categories?lang=en-US")
    soup = BeautifulSoup(raw, "lxml")
    found: dict[str, str] = {}
    for a in soup.find_all("a", href=True):
        m = re.search(r"/categories/(\d+)", a["href"])
        if not m:
            continue
        cid = m.group(1)
        name = clean_text(a.get_text(" ", strip=True) or a.get("title", ""))
        if name and len(name) <= 180:
            # Keep the most descriptive occurrence.
            if cid not in found or len(name) > len(found[cid]):
                found[cid] = name
    all_categories = [{"id": k, "name": v} for k, v in found.items()]
    selected = []
    for c in all_categories:
        n = c["name"]
        if CATEGORY_INCLUDE_RE.search(n) and not CATEGORY_EXCLUDE_RE.search(n):
            selected.append(c)
    (OUT / "categories_all.json").write_text(json.dumps(all_categories, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "categories_selected.json").write_text(json.dumps(selected, ensure_ascii=False, indent=2), encoding="utf-8")
    return selected


def parse_album_cards(page_html: str, category_id: str, category_name: str) -> list[Album]:
    soup = BeautifulSoup(page_html, "lxml")
    albums: list[Album] = []
    for a in soup.select("a.album__main"):
        href = a.get("href", "")
        m = re.search(r"/albums/(\d+)", href)
        if not m:
            continue
        title = clean_text(a.get("title", "") or a.get_text(" ", strip=True))
        if not title:
            # Most Yupoo layouts keep title in a nearby album__title node.
            parent = a.parent
            t = parent.select_one(".album__title") if parent else None
            title = clean_text(t.get_text(" ", strip=True) if t else "")
        img = a.find("img")
        thumb = ""
        if img:
            thumb = normalize_image(img.get("data-origin-src") or img.get("data-src") or img.get("src") or "")
        albums.append(Album(m.group(1), title or f"Album {m.group(1)}", canonical_album_url(href), category_id, category_name, thumb))
    return albums


def scrape_category(c: dict) -> list[Album]:
    out: list[Album] = []
    seen: set[str] = set()
    for page in range(1, 301):
        url = f"{BASE}/categories/{c['id']}?lang=en-US&page={page}"
        try:
            h = fetch(url)
        except Exception as e:
            print(f"WARN category {c['name']} page {page}: {e}")
            break
        cards = parse_album_cards(h, c["id"], c["name"])
        fresh = [x for x in cards if x.album_id not in seen]
        if not cards or not fresh:
            break
        for x in fresh:
            seen.add(x.album_id)
            out.append(x)
        print(f"CATEGORY {c['name']!r} page={page} +{len(fresh)} total={len(out)}")
        # Yupoo normally uses <= 120 albums/page. If the page is visibly short and has no next link, stop.
        soup = BeautifulSoup(h, "lxml")
        has_next = bool(soup.select_one("a.pager__item--next, a[rel='next']"))
        if len(cards) < 20 and not has_next:
            break
        time.sleep(0.15)
    return out


def detect_club(text: str):
    low = text.casefold()
    # Longest aliases first avoids "Milan" stealing "Inter Milan".
    candidates = []
    for club, (country, league, aliases) in CLUBS.items():
        for alias in aliases:
            candidates.append((len(alias), alias.casefold(), club, country, league))
    for _, alias, club, country, league in sorted(candidates, reverse=True):
        if re.search(r"(?<![\w])" + re.escape(alias) + r"(?![\w])", low):
            return club, country, league
    return None


def detect_national(text: str):
    low = text.casefold()
    for alias, canonical in NATIONAL_ALIASES.items():
        if re.search(r"(?<![\w])" + re.escape(alias.casefold()) + r"(?![\w])", low):
            return canonical
    for country in sorted(NATIONAL_TEAMS, key=len, reverse=True):
        if re.search(r"(?<![\w])" + re.escape(country.casefold()) + r"(?![\w])", low):
            return country
    return None


def category_context(name: str):
    for rx, value in LEAGUE_BY_CATEGORY:
        if rx.search(name):
            return value
    return ("International", "Other Clubs")


def classify(a: Album) -> dict | None:
    raw = clean_text(a.source_title)
    combined = f"{raw} {a.category_name}"
    # "short sleeve" is a jersey attribute; plural shorts/pants are not.
    exc_target = re.sub(r"short[- ]sleeved?", "", combined, flags=re.I)
    if EXCLUDE_RE.search(exc_target):
        return None

    club = detect_club(raw)
    category_country, category_league = category_context(a.category_name)
    national_context = category_league == "National Teams" or bool(re.search(r"national team|world cup", a.category_name, re.I))
    national = detect_national(raw) if national_context else None

    if national:
        team = national
        country = national
        league = "National Teams"
        kind = "National Team"
    elif club:
        team, country, league = club
        kind = "Club"
    else:
        # For highly specific football categories, preserve unknown teams rather than silently dropping them.
        is_specific_football = bool(re.search(r"premier league|la liga|serie a|bundesliga|ligue 1|brasileiro|other team|retro|player version|jersey", a.category_name, re.I))
        if not is_specific_football and not STRONG_SHIRT_RE.search(raw):
            return None
        # Use a sanitized leading title as the team/subject and flag it for QA.
        candidate = re.sub(r"\b(19|20)\d{2}\b", "", raw)
        candidate = re.sub(r"\b(home|away|third|4th|fourth|player|version|jersey|shirt|football|soccer|retro|kids?|women'?s?|long[- ]sleeved?|goalkeeper|gk|fan)\b", " ", candidate, flags=re.I)
        candidate = re.sub(r"\b(?:[2-6]XL|XS|S|M|L|XL|XXL|XXXL)\b", " ", candidate, flags=re.I)
        candidate = re.sub(r"[^A-Za-zÀ-ÿ0-9&.' -]+", " ", candidate)
        candidate = re.sub(r"\s+", " ", candidate).strip(" -")
        if not candidate or len(candidate) < 2:
            candidate = f"Team Album {a.album_id}"
        team = candidate[:70]
        country, league = category_country, category_league
        kind = "Unresolved"

    year_m = re.search(r"\b((?:19|20)\d{2})(?:[-/](\d{2,4}))?\b", raw)
    year = year_m.group(0).replace("/", "-") if year_m else ""
    role = ""
    if re.search(r"\bhome\b", raw, re.I): role = "Home"
    elif re.search(r"\baway\b", raw, re.I): role = "Away"
    elif re.search(r"\b(third|3rd)\b", raw, re.I): role = "Third"
    elif re.search(r"\b(fourth|4th)\b", raw, re.I): role = "Fourth"
    attrs = []
    if re.search(r"\bplayer(?:\s+version|\s+edition)?\b", raw, re.I): attrs.append("Player Edition")
    if re.search(r"\bretro\b", combined, re.I): attrs.append("Retro")
    if re.search(r"\bkids?\b|\bchildren\b|\byouth\b", raw, re.I): attrs.append("Kids")
    if re.search(r"\bwomen'?s?\b|\bfemale\b", raw, re.I): attrs.append("Women")
    if re.search(r"\blong[- ]sleeved?\b", raw, re.I): attrs.append("Long-Sleeve")
    if re.search(r"\bgoalkeeper\b|\bGK\b", raw, re.I): attrs.append("Goalkeeper")
    size_m = re.findall(r"\b(?:3XL|4XL|5XL|6XL|XXXL|XXXXL)\b", raw, re.I)
    sizes = sorted(set(x.upper() for x in size_m))

    parts = [team]
    if year: parts.append(year)
    if role: parts.append(role)
    parts.extend(attrs)
    title = " ".join(dict.fromkeys(parts)) + " Football Jersey"
    title = re.sub(r"\s+", " ", title).strip()

    bullets = [f"Team: {team}"]
    if country != "International": bullets.append(f"Country: {country}")
    if league: bullets.append(f"Competition / group: {league}")
    if year: bullets.append(f"Season / year shown in source: {year}")
    if role: bullets.append(f"Design: {role}")
    for x in attrs: bullets.append(f"Edition: {x}")
    if sizes: bullets.append("Extended size reference in source: " + ", ".join(sizes))
    desc = (
        f"<p><strong>{html.escape(title)}</strong> from the authorised KickCrate AU football-shirt catalogue. "
        f"This listing is prepared from the supplier's official product album and keeps the source-specific edition details visible to shoppers.</p>"
        "<ul>" + "".join(f"<li>{html.escape(x)}</li>" for x in bullets) + "</ul>"
        "<p>Product imagery is sourced from the authorised catalogue. Final size availability, price and inventory are managed in Shopify before publication.</p>"
    )
    tags = [
        "catalog:football-shirts", "source:yupoo-194939", f"country:{country}", f"league:{league}", f"team:{team}",
        f"kind:{kind}", f"source-category:{a.category_name}",
    ]
    if year: tags.append(f"season:{year}")
    if role: tags.append(f"design:{role.lower()}")
    for x in attrs: tags.append("edition:" + x.lower().replace(" ", "-"))
    for x in sizes: tags.append("source-size:" + x)
    return {
        "album_id": a.album_id, "source_title": raw, "source_url": a.source_url,
        "category_id": a.category_id, "category_name": a.category_name,
        "team": team, "country": country, "league": league, "kind": kind,
        "year": year, "design": role, "attributes": attrs, "source_sizes": sizes,
        "title": title, "description_html": desc, "tags": tags,
        "thumbnail": a.thumbnail,
    }


def extract_images(item: dict) -> dict:
    try:
        h = fetch(item["source_url"], attempts=4)
        soup = BeautifulSoup(h, "lxml")
        imgs = []
        # Preferred original sources in the actual album photo blocks.
        for node in soup.select("div.showalbum__children"):
            wrap = node.select_one(".image__imagewrap")
            if wrap and (wrap.get("data-type") or "").lower() == "video":
                continue
            img = node.find("img")
            if not img:
                continue
            src = img.get("data-origin-src") or img.get("data-original") or img.get("data-src") or img.get("src") or ""
            src = normalize_image(src)
            if src and src not in imgs and "photo.yupoo.com" in src:
                imgs.append(src)
        # Fallback selectors for alternate Yupoo layout revisions.
        if not imgs:
            for img in soup.select("img[data-origin-src], img[src*='photo.yupoo.com'], img[data-src*='photo.yupoo.com']"):
                src = normalize_image(img.get("data-origin-src") or img.get("data-src") or img.get("src") or "")
                if src and "photo.yupoo.com" in src and src not in imgs:
                    imgs.append(src)
        if not imgs and item.get("thumbnail"):
            imgs = [item["thumbnail"]]
        # Keep a useful gallery without flooding a Shopify product with near-identical photos.
        item["images"] = imgs[:12]
        item["image_count_source_detected"] = len(imgs)
        item["detail_error"] = ""
    except Exception as e:
        item["images"] = [item["thumbnail"]] if item.get("thumbnail") else []
        item["image_count_source_detected"] = len(item["images"])
        item["detail_error"] = str(e)
    return item


def main():
    started = time.time()
    categories = discover_categories()
    print(f"Selected categories: {len(categories)}")
    for c in categories:
        print(f"  {c['id']} {c['name']}")

    all_albums: dict[str, Album] = {}
    membership: dict[str, set[str]] = {}
    for c in categories:
        albums = scrape_category(c)
        for a in albums:
            membership.setdefault(a.album_id, set()).add(a.category_name)
            old = all_albums.get(a.album_id)
            # Prefer a specific competition category over generic mixed buckets.
            if old is None or len(a.category_name) < len(old.category_name):
                all_albums[a.album_id] = a

    (OUT / "albums_raw.json").write_text(json.dumps([asdict(x) for x in all_albums.values()], ensure_ascii=False, indent=2), encoding="utf-8")

    accepted = []
    excluded = []
    for a in all_albums.values():
        x = classify(a)
        if x:
            x["source_categories"] = sorted(membership.get(a.album_id, {a.category_name}))
            accepted.append(x)
        else:
            excluded.append(asdict(a))
    print(f"Albums unique={len(all_albums)} accepted shirts={len(accepted)} excluded={len(excluded)}")

    # Fetch detail galleries concurrently, but conservatively enough not to hammer the source.
    detailed = []
    with ThreadPoolExecutor(max_workers=10) as ex:
        futs = {ex.submit(extract_images, x): x["album_id"] for x in accepted}
        for n, fut in enumerate(as_completed(futs), 1):
            detailed.append(fut.result())
            if n % 100 == 0 or n == len(futs):
                print(f"DETAIL {n}/{len(futs)}")

    detailed.sort(key=lambda x: (x["country"], x["league"], x["team"], x["title"], x["album_id"]))
    unresolved = [x for x in detailed if x["kind"] == "Unresolved"]
    no_images = [x for x in detailed if not x["images"]]
    detail_errors = [x for x in detailed if x.get("detail_error")]

    collections = {
        "countries": sorted({x["country"] for x in detailed}),
        "leagues": sorted({(x["country"], x["league"]) for x in detailed}),
        "teams": sorted({(x["country"], x["league"], x["team"]) for x in detailed}),
    }
    collections["leagues"] = [{"country": a, "league": b} for a, b in collections["leagues"]]
    collections["teams"] = [{"country": a, "league": b, "team": c} for a, b, c in collections["teams"]]

    summary = {
        "source": BASE,
        "selected_categories": categories,
        "unique_albums_in_selected_categories": len(all_albums),
        "accepted_football_shirt_products": len(detailed),
        "excluded_non_shirts": len(excluded),
        "unresolved_team_classifications": len(unresolved),
        "products_without_images": len(no_images),
        "detail_fetch_errors": len(detail_errors),
        "countries": len(collections["countries"]),
        "leagues": len(collections["leagues"]),
        "teams": len(collections["teams"]),
        "elapsed_seconds": round(time.time() - started, 2),
    }

    (OUT / "catalog.json").write_text(json.dumps(detailed, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "excluded.json").write_text(json.dumps(excluded, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "unresolved.json").write_text(json.dumps(unresolved, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "no_images.json").write_text(json.dumps(no_images, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "collections.json").write_text(json.dumps(collections, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    with (OUT / "catalog.csv").open("w", encoding="utf-8-sig", newline="") as f:
        fields = ["album_id", "title", "team", "country", "league", "category_name", "source_title", "source_url", "kind", "year", "design", "image_count_source_detected"]
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for x in detailed:
            w.writerow({k: x.get(k, "") for k in fields})

    print("SUMMARY", json.dumps(summary, ensure_ascii=False))
    if no_images:
        print("QA_FAIL: products without images", len(no_images))
    # Do not fail on unresolved classifications: they remain explicitly flagged for a second pass.


if __name__ == "__main__":
    main()
