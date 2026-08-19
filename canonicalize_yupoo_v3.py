from __future__ import annotations

import json
import re
import time
import unicodedata
from collections import Counter, defaultdict
from dataclasses import asdict
from pathlib import Path

import scrape_yupoo as base
import scrape_yupoo_v2 as v2

SRC = Path("previous_v3/catalog.json")
OUT = Path("out_v3")
OUT.mkdir(exist_ok=True)

BAD_TOKENS = {
    "album", "https", "http", "uid", "yupoo", "baby", "size", "meses", "mes", "months",
    "nike", "adidas", "aaa", "link", "quick", "whatsapp", "wechat", "supplier", "factory",
}

EXTRA_CLUB_ALIASES = {
    "monaco": ("Monaco", "France", "Ligue 1"),
    "al ittihad": ("Al-Ittihad", "Saudi Arabia", "Saudi Pro League"),
    "sao paulo": ("São Paulo", "Brazil", "Brasileiro Série A"),
    "sao paul": ("São Paulo", "Brazil", "Brasileiro Série A"),
    "paris": ("Paris Saint-Germain", "France", "Ligue 1"),
}

ALLOWED_DIGIT_TEAMS = {
    "1. FC Köln", "Schalke 04", "1. FC Kaiserslautern", "Mainz 05", "1860 München",
}


def norm_key(value: str) -> str:
    value = unicodedata.normalize("NFKD", value or "")
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = value.casefold()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", value)).strip()


NORMALIZED_ALIASES = {norm_key(k): v for k, v in v2.CLUB_ALIASES.items()}
NORMALIZED_ALIASES.update(EXTRA_CLUB_ALIASES)


def national_context(item: dict) -> bool:
    cats = " ".join(item.get("source_categories") or [item.get("category_name", "")])
    return bool(re.search(r"national team|world cup|fifa world cup", cats, re.I))


def clean_candidate(raw: str) -> str:
    s = v2.candidate(raw)
    # Remove URLs and source IDs that can be glued to a valid club name.
    s = re.sub(r"https?\S*", " ", s, flags=re.I)
    s = re.sub(r"(?<=[A-Za-zÀ-ÿ])\d{3,}\b", " ", s)
    s = re.sub(r"\b\d{5,}(?=[A-Za-zÀ-ÿ])", " ", s)
    # Compact seasons such as 2627Manchester City and year prefixes such as 1982Corinthian.
    s = re.sub(r"^(?:19|20)\d{2}(?=[A-Za-zÀ-ÿ])", "", s, flags=re.I)
    s = re.sub(r"^(?:2\d){2}(?=[A-Za-zÀ-ÿ])", "", s, flags=re.I)
    # Residual size/source fragments seen in the supplier labels.
    s = re.sub(r"[- ]?s?[- ]?(?:[2-6]xl|xxl|xxxl|xxxxl|4lx)\b.*$", " ", s, flags=re.I)
    s = re.sub(r"\b(?:kids?)\s*\d{1,2}\s*[-/]\s*\d{1,2}\b", " ", s, flags=re.I)
    s = re.sub(r"\b(?:16|18|20|22|24)\s*mes(?:es)?\b", " ", s, flags=re.I)
    # Standalone trailing supplier sequence numbers are not part of an unresolved team name.
    s = re.sub(r"(?:\s*-?\s*)\d{1,2}(?:\s+[A-Z])?$", " ", s)
    s = re.sub(r"\s+", " ", s).strip(" -._")
    return s


def plausible_candidate(cand: str) -> bool:
    if not cand or len(cand) < 2 or len(cand) > 48:
        return False
    if re.search(r"\d", cand):
        return False
    k = norm_key(cand)
    if not k or k in {"ac", "fc", "sc", "cf", "as", "rb", "aaa", "album"}:
        return False
    words = k.split()
    if len(words) > 6 or any(w in BAD_TOKENS for w in words):
        return False
    if not re.search(r"[A-Za-zÀ-ÿ]", cand):
        return False
    return True


def resolve_known(item: dict) -> bool:
    raw = item["source_title"]
    cand = clean_candidate(raw)

    # National teams are accepted only in an explicit national-team / World Cup source context.
    national = base.detect_national(raw)
    if national and national_context(item):
        item.update(team=national, country=national, league="National Teams", kind="National Team", resolution="national-context")
        return True

    # If a country name occurs in a club-league bucket, do not turn it into a club by fallback.
    if national and not national_context(item):
        return False

    club = base.detect_club(raw) or (base.detect_club(cand) if cand else None)
    if club:
        team, country, league = club
        item.update(team=team, country=country, league=league, kind="Club", resolution="known-club")
        return True

    alias = NORMALIZED_ALIASES.get(norm_key(cand))
    if alias:
        team, country, league = alias
        item.update(team=team, country=country, league=league, kind="Club", resolution="club-alias-v3")
        return True
    return False


def album_from(item: dict) -> base.Album:
    return base.Album(
        str(item["album_id"]),
        item.get("source_title", ""),
        item.get("source_url", ""),
        str(item.get("category_id", "")),
        item.get("category_name", ""),
        item.get("thumbnail", ""),
    )


def carry_gallery(dst: dict, src: dict) -> None:
    for field in ("images", "source_sizes", "source_image_count_detected", "detail_error", "thumbnail"):
        if field in src:
            dst[field] = src[field]
    dst["source_categories"] = list(src.get("source_categories") or [src.get("category_name", "")])


def main() -> None:
    started = time.time()
    if not SRC.exists():
        raise SystemExit(f"Missing source catalogue: {SRC}")
    source = json.loads(SRC.read_text(encoding="utf-8"))

    items = []
    excluded = []
    for old in source:
        x = base.classify(album_from(old))
        if not x:
            excluded.append(old)
            continue
        carry_gallery(x, old)
        if x["kind"] == "Unresolved":
            resolve_known(x)
        else:
            # Re-run known detection to force canonical spelling even for records already resolved by v1.
            resolve_known(x)
        items.append(x)

    # Conservative league-category fallback: only plausible labels repeated at least twice in that
    # specific league are allowed to become a club. One-off unknowns stay unresolved for later QA.
    candidates = {}
    freq = Counter()
    for x in items:
        if x["kind"] != "Unresolved" or x["category_name"] not in v2.SPECIFIC_CONTEXT:
            continue
        if base.detect_national(x["source_title"]):
            continue
        cand = clean_candidate(x["source_title"])
        if not plausible_candidate(cand):
            continue
        k = norm_key(cand)
        country, league = v2.SPECIFIC_CONTEXT[x["category_name"]]
        candidates[x["album_id"]] = (k, cand, country, league)
        freq[(country, league, k)] += 1

    inferred_by_key = defaultdict(set)
    for x in items:
        info = candidates.get(x["album_id"])
        if not info or x["kind"] != "Unresolved":
            continue
        k, cand, country, league = info
        if freq[(country, league, k)] < 2:
            continue
        alias = NORMALIZED_ALIASES.get(k)
        if alias:
            team, country, league = alias
        else:
            team = v2.professional_name(cand)
        x.update(team=team, country=country, league=league, kind="Club", resolution="repeated-league-label-v3")
        inferred_by_key[k].add((team, country, league))

    # Generic Player/Retro/Long-Sleeve buckets may reuse an exact label that has one unambiguous
    # league-specific resolution. Reuse only when there is exactly one possible club tuple.
    for x in items:
        if x["kind"] != "Unresolved":
            continue
        if national_context(x):
            resolve_known(x)
            if x["kind"] != "Unresolved":
                continue
        cand = clean_candidate(x["source_title"])
        if not plausible_candidate(cand):
            continue
        k = norm_key(cand)
        matches = inferred_by_key.get(k, set())
        if len(matches) == 1:
            team, country, league = next(iter(matches))
            x.update(team=team, country=country, league=league, kind="Club", resolution="cross-category-v3")

    # Normalize spelling variants that collapse to the same accent-insensitive team key inside the
    # same country/league. Explicit aliases win; otherwise the most frequent spelling wins.
    groups = defaultdict(list)
    for x in items:
        if x["kind"] == "Unresolved":
            continue
        groups[(x["country"], x["league"], norm_key(x["team"]))].append(x)

    for (country, league, k), group in groups.items():
        explicit = NORMALIZED_ALIASES.get(k)
        if explicit and explicit[1] == country:
            canonical = explicit[0]
        else:
            counts = Counter(x["team"] for x in group)
            canonical = sorted(counts, key=lambda name: (-counts[name], len(name), name.casefold()))[0]
        for x in group:
            x["team"] = canonical

    for x in items:
        v2.rebuild_copy(x)

    items.sort(key=lambda x: (x["kind"] == "Unresolved", x["country"], x["league"], x["team"], x["title"], str(x["album_id"])))
    unresolved = [x for x in items if x["kind"] == "Unresolved"]
    resolved = [x for x in items if x["kind"] != "Unresolved"]
    no_images = [x for x in items if not x.get("images")]
    detail_errors = [x for x in items if x.get("detail_error")]

    countries = sorted({x["country"] for x in resolved if x.get("country")})
    leagues = sorted({(x["country"], x["league"]) for x in resolved if x.get("league")})
    teams = sorted({(x["country"], x["league"], x["team"]) for x in resolved if x.get("team")})

    suspicious_digit = sorted({x["team"] for x in resolved if re.search(r"\d", x["team"]) and x["team"] not in ALLOWED_DIGIT_TEAMS})
    normalized_dupes = []
    check = defaultdict(set)
    for x in resolved:
        check[(x["country"], x["league"], norm_key(x["team"]))].add(x["team"])
    for key, names in check.items():
        if len(names) > 1:
            normalized_dupes.append({"country": key[0], "league": key[1], "key": key[2], "names": sorted(names)})

    collections = {
        "countries": countries,
        "leagues": [{"country": a, "league": b} for a, b in leagues],
        "teams": [{"country": a, "league": b, "team": c} for a, b, c in teams],
    }
    summary = {
        "source_products": len(source),
        "products_after_reclassification": len(items),
        "resolved_products": len(resolved),
        "unresolved_products": len(unresolved),
        "excluded_products": len(excluded),
        "products_without_images": len(no_images),
        "detail_fetch_errors": len(detail_errors),
        "countries": len(countries),
        "leagues": len(leagues),
        "teams": len(teams),
        "suspicious_digit_team_names": suspicious_digit,
        "normalized_duplicate_groups": len(normalized_dupes),
        "elapsed_seconds": round(time.time() - started, 2),
        "qa_images_pass": not no_images and not detail_errors,
        "qa_team_names_pass": not suspicious_digit and not normalized_dupes,
    }

    (OUT / "catalog.json").write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "resolved.json").write_text(json.dumps(resolved, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "unresolved.json").write_text(json.dumps(unresolved, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "collections.json").write_text(json.dumps(collections, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "normalized_dupes.json").write_text(json.dumps(normalized_dupes, ensure_ascii=False, indent=2), encoding="utf-8")

    print("SUMMARY", json.dumps(summary, ensure_ascii=False))
    if suspicious_digit:
        print("QA_FAIL suspicious digit teams", suspicious_digit)
    if normalized_dupes:
        print("QA_FAIL normalized duplicate groups", len(normalized_dupes))
    if no_images or detail_errors:
        raise SystemExit("Image QA regression detected")


if __name__ == "__main__":
    main()
