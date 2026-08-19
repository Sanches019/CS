from __future__ import annotations

import csv
import html
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from pathlib import Path

from bs4 import BeautifulSoup

import scrape_yupoo as base

OUT = Path("out")
OUT.mkdir(exist_ok=True)

SPECIFIC_CONTEXT = {
    "Brasileiro Série A ，OPEN 2 PAGE": ("Brazil", "Brasileiro Série A"),
    "Premier League": ("England", "Premier League"),
    "La Liga": ("Spain", "La Liga"),
    "Serie A": ("Italy", "Serie A"),
    "Bundesliga": ("Germany", "Bundesliga"),
    "Ligue 1": ("France", "Ligue 1"),
}

# Supplier naming is sometimes translated, abbreviated or misspelled. These are
# high-confidence aliases visible repeatedly in the authorised catalogue.
CLUB_ALIASES = {
    "paris": ("Paris Saint-Germain", "France", "Ligue 1"),
    "seville": ("Sevilla", "Spain", "La Liga"),
    "venice": ("Venezia", "Italy", "Italian Clubs"),
    "blue cross": ("Cruz Azul", "Mexico", "Liga MX"),
    "cougar": ("Pumas UNAM", "Mexico", "Liga MX"),
    "cougars": ("Pumas UNAM", "Mexico", "Liga MX"),
    "tiger": ("Tigres UANL", "Mexico", "Liga MX"),
    "tigers": ("Tigres UANL", "Mexico", "Liga MX"),
    "toluca": ("Deportivo Toluca", "Mexico", "Liga MX"),
    "miami": ("Inter Miami CF", "United States", "Major League Soccer"),
    "colo colo": ("Colo-Colo", "Chile", "Chilean Primera División"),
    "club universidad de chile": ("Universidad de Chile", "Chile", "Chilean Primera División"),
    "universidad de chile": ("Universidad de Chile", "Chile", "Chilean Primera División"),
    "university of chile": ("Universidad de Chile", "Chile", "Chilean Primera División"),
    "penarol": ("Peñarol", "Uruguay", "Uruguayan Primera División"),
    "san lorenzo": ("San Lorenzo", "Argentina", "Liga Profesional Argentina"),
    "maccabi haifa": ("Maccabi Haifa", "Israel", "Israeli Premier League"),
    "copenhagen": ("FC Copenhagen", "Denmark", "Danish Superliga"),
    "fcsb": ("FCSB", "Romania", "Liga I"),
    "houston dynamo": ("Houston Dynamo FC", "United States", "Major League Soccer"),
    "leon": ("Club León", "Mexico", "Liga MX"),
    "eindhoven": ("PSV Eindhoven", "Netherlands", "Eredivisie"),
    "clover": ("Shamrock Rovers", "Ireland", "League of Ireland Premier Division"),
    "the americas": ("Club América", "Mexico", "Liga MX"),
    "americas": ("Club América", "Mexico", "Liga MX"),
    "new moon": ("Al Hilal", "Saudi Arabia", "Saudi Pro League"),
    "moon": ("Al Hilal", "Saudi Arabia", "Saudi Pro League"),
    "riyadh crescent": ("Al Hilal", "Saudi Arabia", "Saudi Pro League"),
    "jeddah united": ("Al-Ittihad", "Saudi Arabia", "Saudi Pro League"),
    "ittihad jeddah united": ("Al-Ittihad", "Saudi Arabia", "Saudi Pro League"),
    "national athletics": ("Atlético Nacional", "Colombia", "Categoría Primera A"),
    "catholicism": ("Universidad Católica", "Chile", "Chilean Primera División"),
    "deportivo universidad católica": ("Universidad Católica", "Chile", "Chilean Primera División"),
    "olympia": ("Club Olimpia", "Paraguay", "Paraguayan Primera División"),
    "austin": ("Austin FC", "United States", "Major League Soccer"),
    "tijuana": ("Club Tijuana", "Mexico", "Liga MX"),
    "monterey": ("CF Monterrey", "Mexico", "Liga MX"),
    "monterrey": ("CF Monterrey", "Mexico", "Liga MX"),
    "paysandu": ("Paysandu", "Brazil", "Brazilian Clubs"),
    "remo": ("Clube do Remo", "Brazil", "Brazilian Clubs"),
    "santa cruz": ("Santa Cruz", "Brazil", "Brazilian Clubs"),
    "nautico capibaribe": ("Náutico", "Brazil", "Brazilian Clubs"),
    "coritiba": ("Coritiba", "Brazil", "Brazilian Clubs"),
    "rb bragantino": ("Red Bull Bragantino", "Brazil", "Brasileiro Série A"),
    "america mineiro": ("América Mineiro", "Brazil", "Brazilian Clubs"),
    "recife": ("Sport Recife", "Brazil", "Brasileiro Série A"),
    "victoria": ("Vitória", "Brazil", "Brasileiro Série A"),
    "sao paul": ("São Paulo", "Brazil", "Brasileiro Série A"),
    "corinthian": ("Corinthians", "Brazil", "Brasileiro Série A"),
    "almeria": ("UD Almería", "Spain", "Spanish Clubs"),
    "aravis": ("Alavés", "Spain", "La Liga"),
    "albacete": ("Albacete", "Spain", "Spanish Clubs"),
    "malaga": ("Málaga", "Spain", "Spanish Clubs"),
    "las palmas": ("UD Las Palmas", "Spain", "Spanish Clubs"),
    "santander": ("Racing Santander", "Spain", "Spanish Clubs"),
    "zaragoza": ("Real Zaragoza", "Spain", "Spanish Clubs"),
    "cordoba": ("Córdoba CF", "Spain", "Spanish Clubs"),
    "burgos": ("Burgos CF", "Spain", "Spanish Clubs"),
    "bilbao": ("Athletic Club", "Spain", "La Liga"),
    "portsmouth": ("Portsmouth", "England", "English Clubs"),
    "middlesbrough": ("Middlesbrough", "England", "English Clubs"),
    "sheffield united": ("Sheffield United", "England", "English Clubs"),
    "birmingham": ("Birmingham City", "England", "English Clubs"),
    "aberdeen": ("Aberdeen", "Scotland", "Scottish Premiership"),
    "coventry": ("Coventry City", "England", "English Clubs"),
    "dusseldorf": ("Fortuna Düsseldorf", "Germany", "German Clubs"),
    "bielefeld": ("Arminia Bielefeld", "Germany", "German Clubs"),
    "kaiserslautern": ("1. FC Kaiserslautern", "Germany", "German Clubs"),
    "hamburger": ("Hamburger SV", "Germany", "German Clubs"),
    "menxing": ("Borussia Mönchengladbach", "Germany", "Bundesliga"),
    "lance": ("Lens", "France", "Ligue 1"),
    "lyons": ("Lyon", "France", "Ligue 1"),
    "bordeaux": ("Bordeaux", "France", "French Clubs"),
    "ange": ("Angers", "France", "Ligue 1"),
    "avellaneda athletic": ("Racing Club", "Argentina", "Liga Profesional Argentina"),
    "atlas": ("Atlas FC", "Mexico", "Liga MX"),
    "necaxa": ("Club Necaxa", "Mexico", "Liga MX"),
    "millionaire": ("Millonarios FC", "Colombia", "Categoría Primera A"),
    "nacional montevideo": ("Club Nacional de Football", "Uruguay", "Uruguayan Primera División"),
    "aik": ("AIK", "Sweden", "Allsvenskan"),
    "big board cherry blossom": ("Cerezo Osaka", "Japan", "J1 League"),
    "osaka cherry blossoms": ("Cerezo Osaka", "Japan", "J1 League"),
    "orlando": ("Orlando City SC", "United States", "Major League Soccer"),
    "belgrade red star": ("Red Star Belgrade", "Serbia", "Serbian SuperLiga"),
    "cerro porteno": ("Cerro Porteño", "Paraguay", "Paraguayan Primera División"),
    "kashima antlers": ("Kashima Antlers", "Japan", "J1 League"),
    "aek athens": ("AEK Athens", "Greece", "Super League Greece"),
    "chicago": ("Chicago Fire FC", "United States", "Major League Soccer"),
    "hull city": ("Hull City", "England", "English Clubs"),
    "kawasaki": ("Kawasaki Frontale", "Japan", "J1 League"),
    "kobe": ("Vissel Kobe", "Japan", "J1 League"),
    "newells old boys": ("Newell's Old Boys", "Argentina", "Liga Profesional Argentina"),
    "plymouth": ("Plymouth Argyle", "England", "English Clubs"),
    "rosario central": ("Rosario Central", "Argentina", "Liga Profesional Argentina"),
    "yokohama marinos": ("Yokohama F. Marinos", "Japan", "J1 League"),
}

NATIONAL_ALIASES = {
    "usa": "United States", "korea": "South Korea", "korean": "South Korea",
    "columbia": "Colombia", "spanish": "Spain", "dutch": "Netherlands",
    "welsh": "Wales", "algerian": "Algeria", "senegalese": "Senegal",
    "palestine": "Palestine", "palestinian": "Palestine", "palestines": "Palestine",
    "armenia": "Armenia", "honduras": "Honduras", "guatemala": "Guatemala",
    "burkina faso": "Burkina Faso", "el salvador": "El Salvador", "haiti": "Haiti",
    "mali": "Mali", "congo": "DR Congo", "curacao": "Curaçao",
    "malaysia": "Malaysia", "united arab emirates": "United Arab Emirates",
    "georgia": "Georgia", "finland": "Finland", "guinea": "Guinea",
    "the philippines": "Philippines",
}
for n in base.NATIONAL_TEAMS:
    NATIONAL_ALIASES.setdefault(n.casefold(), n)
for a, n in base.NATIONAL_ALIASES.items():
    NATIONAL_ALIASES.setdefault(a.casefold(), n)

NOISE = re.compile(
    r"\b(home|away|guest|third|3rd|fourth|4th|player|players|version|jersey|shirt|retro|kids?|"
    r"women'?s?|woman|long[- ]sleeved?|goalkeeper|gk|fan|aaa|football|soccer)\b", re.I
)


def candidate(raw: str) -> str:
    s = base.clean_text(raw)
    s = re.sub(r"\b(?:19|20)?\d{2}\s*[/\-]\s*(?:19|20)?\d{2}\b", " ", s)
    s = re.sub(r"\b(?:19|20)\d{2}\b", " ", s)
    # Compact season codes such as 2425/2627, while preserving club names such as 1860 München.
    s = re.sub(r"\b(?:0\d|1\d|2\d)(?:0\d|1\d|2\d)\b", " ", s)
    s = re.sub(r"\b(?:XS|S|M|L|XL|XXL|XXXL|XXXXL|[2-6]XL)\b", " ", s, flags=re.I)
    s = re.sub(r"\b[A-Z]\d{3,5}\b", " ", s, flags=re.I)
    s = re.sub(r"\b\d{3,4}\b", " ", s)
    s = re.sub(r"\b1\s*:\s*1\b", " ", s)
    s = NOISE.sub(" ", s)
    s = re.sub(r"[^A-Za-zÀ-ÿ0-9&.' -]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip(" -.")
    return s


def key(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", s.casefold())).strip()


def parse_max_pages(html_text: str, current: int = 1) -> int | None:
    soup = BeautifulSoup(html_text, "lxml")
    text = soup.get_text(" ", strip=True)
    # Yupoo renders pagination as e.g. "1 / 26". Prefer the match whose left side is current.
    matches = re.findall(r"(?<!\d)(\d+)\s*/\s*(\d+)(?!\d)", text)
    for left, right in matches:
        if int(left) == current and int(right) >= current:
            return int(right)
    # Fallback: largest plausible denominator.
    denoms = [int(r) for _, r in matches if int(r) >= current and int(r) <= 500]
    return max(denoms) if denoms else None


def scrape_category(c: dict) -> list[base.Album]:
    out: list[base.Album] = []
    seen: set[str] = set()
    max_pages = None
    page = 1
    while page <= 300:
        if max_pages is not None and page > max_pages:
            break
        url = f"{base.BASE}/categories/{c['id']}?lang=en-US&page={page}"
        try:
            h = base.fetch(url)
        except Exception as e:
            print(f"WARN category {c['name']} page {page}: {e}")
            break
        if max_pages is None:
            max_pages = parse_max_pages(h, page)
            print(f"PAGER {c['name']!r}: max_pages={max_pages}")
        cards = base.parse_album_cards(h, c["id"], c["name"])
        fresh = [x for x in cards if x.album_id not in seen]
        if not cards or not fresh:
            break
        for x in fresh:
            seen.add(x.album_id)
            out.append(x)
        print(f"CATEGORY {c['name']!r} page={page}/{max_pages or '?'} +{len(fresh)} total={len(out)}")
        if max_pages is None:
            soup = BeautifulSoup(h, "lxml")
            has_next = bool(soup.select_one("a.pager__item--next, a[rel='next']"))
            if len(cards) < 20 and not has_next:
                break
        page += 1
        time.sleep(0.15)
    return out


def apply_alias(item: dict) -> bool:
    cand = candidate(item["source_title"])
    k = key(cand)
    # Normalise a few residual size/source suffixes.
    k = re.sub(r"\b4lx\b.*$", "", k).strip()
    if k in NATIONAL_ALIASES:
        n = NATIONAL_ALIASES[k]
        item.update(team=n, country=n, league="National Teams", kind="National Team")
        item["resolution"] = "national-alias"
        return True
    if k in CLUB_ALIASES:
        t, c, l = CLUB_ALIASES[k]
        item.update(team=t, country=c, league=l, kind="Club")
        item["resolution"] = "club-alias"
        return True
    return False


def professional_name(cand: str) -> str:
    words = []
    for w in cand.split():
        if w.upper() in {"AIK", "FCSB", "PSV", "RB", "FC", "AC", "AS", "CF", "SC", "SV", "UD"}:
            words.append(w.upper())
        else:
            words.append(w.capitalize())
    return " ".join(words)


def rebuild_copy(item: dict) -> None:
    team = item["team"]
    parts = [team]
    if item.get("year"):
        parts.append(item["year"])
    if item.get("design"):
        parts.append(item["design"])
    parts.extend(item.get("attributes") or [])
    title = " ".join(dict.fromkeys(parts)) + " Football Jersey"
    title = re.sub(r"\s+", " ", title).strip()
    item["title"] = title

    facts = [f"Team: {team}"]
    if item.get("country") and item["country"] != "International":
        facts.append(f"Country: {item['country']}")
    if item.get("league"):
        facts.append(f"League / competition: {item['league']}")
    if item.get("year"):
        facts.append(f"Season shown by supplier: {item['year']}")
    if item.get("design"):
        facts.append(f"Design: {item['design']}")
    for attr in item.get("attributes") or []:
        facts.append(f"Edition: {attr}")
    if item.get("source_sizes"):
        facts.append("Extended size references shown by supplier: " + ", ".join(item["source_sizes"]))

    item["description_html"] = (
        f"<p><strong>{html.escape(title)}</strong></p>"
        "<p>Football shirt listing prepared from the supplier's authorised catalogue. "
        "The product gallery is copied from the corresponding supplier album so the visual details of this specific edition remain attached to the correct listing.</p>"
        "<ul>" + "".join(f"<li>{html.escape(f)}</li>" for f in facts) + "</ul>"
        "<p>Final price, available sizes and stock can be configured in Shopify before this draft is published.</p>"
    )
    tags = [
        "catalog:football-shirts", "source:yupoo-194939", f"source-album:{item['album_id']}",
        f"country:{item['country']}", f"league:{item['league']}", f"team:{item['team']}", f"kind:{item['kind']}"
    ]
    if item.get("year"):
        tags.append(f"season:{item['year']}")
    if item.get("design"):
        tags.append(f"design:{item['design'].lower()}")
    for a in item.get("attributes") or []:
        tags.append("edition:" + a.lower().replace(" ", "-"))
    item["tags"] = tags


def main():
    started = time.time()
    categories = base.discover_categories()
    print(f"Selected categories: {len(categories)}")
    for c in categories:
        print(f"  {c['id']} {c['name']}")

    all_albums: dict[str, base.Album] = {}
    membership: dict[str, set[str]] = {}
    per_category_counts = {}
    for c in categories:
        albums = scrape_category(c)
        per_category_counts[c["name"]] = len(albums)
        for a in albums:
            membership.setdefault(a.album_id, set()).add(a.category_name)
            old = all_albums.get(a.album_id)
            if old is None or len(a.category_name) < len(old.category_name):
                all_albums[a.album_id] = a

    (OUT / "albums_raw.json").write_text(json.dumps([asdict(x) for x in all_albums.values()], ensure_ascii=False, indent=2), encoding="utf-8")

    accepted, excluded = [], []
    for a in all_albums.values():
        # User requested shirts only: exclude pet items as well as base non-shirt exclusions.
        if re.search(r"\bpet\b", a.source_title, re.I):
            excluded.append(asdict(a))
            continue
        x = base.classify(a)
        if x:
            x["source_categories"] = sorted(membership.get(a.album_id, {a.category_name}))
            if x["kind"] == "Unresolved":
                apply_alias(x)
            accepted.append(x)
        else:
            excluded.append(asdict(a))

    # Second pass: every plausible team name that sits in a league-specific category can
    # safely inherit that country/league. Build an exact dictionary and use it to classify
    # identical supplier labels occurring in generic Player/Retro/Long-Sleeve buckets.
    inferred = {}
    junk = {"", "album", "1", "ac", "aaa", "nike", "nike 90"}
    for x in accepted:
        if x["kind"] != "Unresolved" or x["category_name"] not in SPECIFIC_CONTEXT:
            continue
        cand = candidate(x["source_title"])
        k = key(cand)
        if not k or k in junk or k.isdigit():
            continue
        country, league = SPECIFIC_CONTEXT[x["category_name"]]
        team = professional_name(cand)
        x.update(team=team, country=country, league=league, kind="Club", resolution="league-category")
        inferred.setdefault(k, (team, country, league))

    for x in accepted:
        if x["kind"] != "Unresolved":
            continue
        cand = candidate(x["source_title"])
        k = key(cand)
        if k in inferred:
            t, c, l = inferred[k]
            x.update(team=t, country=c, league=l, kind="Club", resolution="cross-category")
        else:
            apply_alias(x)

    # Rebuild customer-facing copy after all classification changes.
    for x in accepted:
        rebuild_copy(x)

    print(f"Albums unique={len(all_albums)} accepted shirts={len(accepted)} excluded={len(excluded)}")

    detailed = []
    with ThreadPoolExecutor(max_workers=10) as ex:
        futs = {ex.submit(base.extract_images, x): x["album_id"] for x in accepted}
        for n, fut in enumerate(as_completed(futs), 1):
            detailed.append(fut.result())
            if n % 100 == 0 or n == len(futs):
                print(f"DETAIL {n}/{len(futs)}")

    detailed.sort(key=lambda x: (x["country"], x["league"], x["team"], x["title"], x["album_id"]))
    unresolved = [x for x in detailed if x["kind"] == "Unresolved"]
    no_images = [x for x in detailed if not x["images"]]
    detail_errors = [x for x in detailed if x.get("detail_error")]

    collections = {
        "countries": sorted({x["country"] for x in detailed if x["country"]}),
        "leagues": sorted({(x["country"], x["league"]) for x in detailed if x["league"]}),
        "teams": sorted({(x["country"], x["league"], x["team"]) for x in detailed if x["team"]}),
    }
    collections["leagues"] = [{"country": a, "league": b} for a, b in collections["leagues"]]
    collections["teams"] = [{"country": a, "league": b, "team": c} for a, b, c in collections["teams"]]

    summary = {
        "source": base.BASE,
        "selected_categories": categories,
        "per_category_album_counts": per_category_counts,
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
        "qa_pass": len(no_images) == 0 and len(detail_errors) == 0,
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
    if detail_errors:
        print("QA_WARN: detail fetch errors", len(detail_errors))
    if unresolved:
        print("QA_WARN: unresolved classifications", len(unresolved))


if __name__ == "__main__":
    main()
