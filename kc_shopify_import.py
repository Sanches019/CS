#!/usr/bin/env python3
from __future__ import annotations

import json
import mimetypes
import os
import re
import sys
import time
import unicodedata
from pathlib import Path
from typing import Any

import requests

STORE = os.environ.get("SHOPIFY_STORE_DOMAIN", "").strip()
TOKEN = os.environ.get("SHOPIFY_ADMIN_TOKEN", "").strip()
API_VERSION = os.environ.get("SHOPIFY_API_VERSION", "2026-07").strip()
CATALOG_PATH = Path(os.environ.get("CATALOG_PATH", "catalog_v3/resolved.json"))
SHARD_COUNT = max(1, int(os.environ.get("SHARD_COUNT", "1")))
SHARD_INDEX = int(os.environ.get("SHARD_INDEX", "0"))
MAX_PRODUCTS = max(0, int(os.environ.get("MAX_PRODUCTS", "0")))
MAX_IMAGES = max(0, int(os.environ.get("MAX_IMAGES_PER_PRODUCT", "0")))
REQUEST_TIMEOUT = int(os.environ.get("REQUEST_TIMEOUT", "90"))
DOWNLOAD_TIMEOUT = int(os.environ.get("DOWNLOAD_TIMEOUT", "90"))
REPORT_DIR = Path(os.environ.get("REPORT_DIR", "import_reports"))
REPORT_DIR.mkdir(parents=True, exist_ok=True)

if STORE.startswith("https://"):
    STORE = STORE[8:]
STORE = STORE.rstrip("/")
if not STORE or not TOKEN:
    raise SystemExit("SHOPIFY_STORE_DOMAIN and SHOPIFY_ADMIN_TOKEN are required.")
if not (0 <= SHARD_INDEX < SHARD_COUNT):
    raise SystemExit("SHARD_INDEX must be in range [0, SHARD_COUNT).")
if not CATALOG_PATH.exists():
    raise SystemExit(f"Missing catalogue: {CATALOG_PATH}")

GRAPHQL_URL = f"https://{STORE}/admin/api/{API_VERSION}/graphql.json"
SESSION = requests.Session()
SESSION.headers.update({
    "X-Shopify-Access-Token": TOKEN,
    "Content-Type": "application/json",
    "User-Agent": "KickCrate-Catalog-Importer/1.0",
})

NON_SHIRT_RE = re.compile(
    r"\b(shorts?|socks?|jacket|windbreaker|hoodie|tracksuit|training|train|pants?|trousers?|polo|vest|kit)\b",
    re.I,
)

FIND_PRODUCT = """
query KCFindProduct($q:String!){
  products(first:10,query:$q,sortKey:CREATED_AT){
    nodes{
      id title handle status createdAt vendor productType tags
      metafield(namespace:"kickcrate",key:"media_imported"){value}
    }
  }
}
"""

CREATE_PRODUCT = """
mutation KCCreateProductWithMedia($product:ProductCreateInput!,$media:[CreateMediaInput!]){
  productCreate(product:$product,media:$media){
    product{id title handle status}
    userErrors{field message}
  }
}
"""

UPDATE_PRODUCT = """
mutation KCUpdateProductWithMedia($product:ProductUpdateInput!,$media:[CreateMediaInput!]){
  productUpdate(product:$product,media:$media){
    product{id title handle status}
    userErrors{field message}
  }
}
"""

STAGE_IMAGES = """
mutation KCStageImages($input:[StagedUploadInput!]!){
  stagedUploadsCreate(input:$input){
    stagedTargets{
      url
      resourceUrl
      parameters{name value}
    }
    userErrors{field message}
  }
}
"""


def slugify(value: str) -> str:
    value = unicodedata.normalize("NFKD", value or "")
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    return value[:180] or "football-shirt"


def clean_title(item: dict[str, Any]) -> str:
    title = (item.get("title") or f"{item.get('team', 'Football')} Football Jersey").strip()
    title = re.sub(r"\bFootball Jersey\b", "Football Shirt", title, flags=re.I)
    title = re.sub(r"\bJersey\b", "Football Shirt", title, flags=re.I)
    title = re.sub(r"\s+", " ", title).strip()
    return title


def source_url(item: dict[str, Any]) -> str:
    url = (item.get("source_url") or "").strip()
    if url:
        return url
    return f"https://194939.x.yupoo.com/albums/{item['album_id']}?uid=1"


def professional_description(item: dict[str, Any], title: str) -> str:
    existing = (item.get("description_html") or "").strip()
    if existing:
        return existing.replace("Football Jersey", "Football Shirt").replace("football jersey", "football shirt")
    team = item.get("team") or "Team"
    country = item.get("country") or ""
    league = item.get("league") or ""
    edition = []
    if item.get("year"):
        edition.append(str(item["year"]))
    if item.get("design"):
        edition.append(str(item["design"]))
    detail = " ".join(edition).strip()
    detail_html = f"<li>Edition: {detail}</li>" if detail else ""
    return (
        f"<p><strong>{title}</strong></p>"
        "<p>Football shirt from the authorised supplier catalogue, prepared as a draft for final commercial review.</p>"
        "<ul>"
        f"<li>Team: {team}</li>"
        f"<li>Country: {country}</li>"
        f"<li>League / competition: {league}</li>"
        f"{detail_html}"
        "</ul>"
        "<p>Price, sizes and inventory remain intentionally unset until final store configuration.</p>"
    )


def build_tags(item: dict[str, Any]) -> list[str]:
    tags = list(item.get("tags") or [])
    required = [
        "catalog:football-shirts",
        "source:yupoo-194939",
        f"source-album:{item['album_id']}",
        f"country:{item.get('country', '')}",
        f"league:{item.get('league', '')}",
        f"team:{item.get('team', '')}",
        f"kind:{item.get('kind', '')}",
    ]
    if item.get("year"):
        required.append(f"season:{item['year']}")
    if item.get("design"):
        required.append(f"design:{item['design']}")
    seen = set()
    out = []
    for tag in tags + required:
        tag = str(tag).strip()
        if not tag or tag.endswith(":") or tag in seen:
            continue
        seen.add(tag)
        out.append(tag)
    return out


def product_payload(item: dict[str, Any], media_imported: bool) -> dict[str, Any]:
    title = clean_title(item)
    album_id = str(item["album_id"])
    handle = f"{slugify(title)}-yupoo-{album_id}"
    metafields = [
        {"namespace": "kickcrate", "key": "source_album_id", "type": "single_line_text_field", "value": album_id},
        {"namespace": "kickcrate", "key": "source_url", "type": "url", "value": source_url(item)},
    ]
    if media_imported:
        metafields.append({
            "namespace": "kickcrate",
            "key": "media_imported",
            "type": "boolean",
            "value": "true",
        })
    return {
        "title": title,
        "handle": handle,
        "descriptionHtml": professional_description(item, title),
        "vendor": "KickCrate AU",
        "productType": "Football Shirt",
        "status": "DRAFT",
        "tags": build_tags(item),
        "metafields": metafields,
        "seo": {
            "title": title[:70],
            "description": f"{title} from the KickCrate AU football shirt catalogue."[:320],
        },
    }


def graphql(query: str, variables: dict[str, Any] | None = None, attempts: int = 7) -> dict[str, Any]:
    payload = {"query": query, "variables": variables or {}}
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            resp = SESSION.post(GRAPHQL_URL, json=payload, timeout=REQUEST_TIMEOUT)
            if resp.status_code in {429, 500, 502, 503, 504}:
                wait = min(30, 2 ** attempt)
                print(f"HTTP {resp.status_code}; retrying in {wait}s", flush=True)
                time.sleep(wait)
                continue
            resp.raise_for_status()
            body = resp.json()
            if body.get("errors"):
                messages = "; ".join(str(x.get("message", x)) for x in body["errors"])
                if any(term in messages.lower() for term in ("throttled", "temporarily", "internal")):
                    wait = min(30, 2 ** attempt)
                    print(f"GraphQL transient error: {messages}; retrying in {wait}s", flush=True)
                    time.sleep(wait)
                    continue
                raise RuntimeError(f"GraphQL errors: {messages}")
            throttle = (((body.get("extensions") or {}).get("cost") or {}).get("throttleStatus") or {})
            available = throttle.get("currentlyAvailable")
            restore = throttle.get("restoreRate") or 50
            if isinstance(available, (int, float)) and available < 100:
                time.sleep(max(0.25, min(3.0, (100 - available) / max(1, restore))))
            return body["data"]
        except (requests.RequestException, ValueError, RuntimeError) as exc:
            last_error = exc
            if attempt + 1 == attempts:
                break
            wait = min(30, 2 ** attempt)
            print(f"Request error: {exc}; retrying in {wait}s", flush=True)
            time.sleep(wait)
    raise RuntimeError(f"GraphQL request failed after retries: {last_error}")


def check_user_errors(payload: dict[str, Any], key: str) -> None:
    errors = payload[key].get("userErrors") or payload[key].get("mediaUserErrors") or []
    if errors:
        raise RuntimeError("; ".join(f"{e.get('field')}: {e.get('message')}" for e in errors))


def find_existing(album_id: str) -> list[dict[str, Any]]:
    q = f'tag:"source-album:{album_id}"'
    data = graphql(FIND_PRODUCT, {"q": q})
    nodes = data["products"]["nodes"]
    nodes.sort(key=lambda x: x.get("createdAt") or "")
    return nodes


def image_meta(content_type: str, url: str) -> tuple[str, str]:
    mime = (content_type or "").split(";")[0].strip().lower()
    allowed = {
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "image/gif": ".gif",
    }
    if mime not in allowed:
        guessed, _ = mimetypes.guess_type(url)
        mime = guessed if guessed in allowed else "image/jpeg"
    return mime, allowed.get(mime, ".jpg")


def download_images(item: dict[str, Any]) -> list[dict[str, Any]]:
    urls = [str(x).strip() for x in (item.get("images") or []) if str(x).strip()]
    if MAX_IMAGES:
        urls = urls[:MAX_IMAGES]
    if not urls:
        return []
    album_url = source_url(item)
    downloaded = []
    for idx, url in enumerate(urls, 1):
        for attempt in range(5):
            try:
                r = requests.get(
                    url,
                    headers={
                        "Referer": album_url,
                        "User-Agent": "Mozilla/5.0 KickCrate-Catalog-Importer/1.0",
                    },
                    timeout=DOWNLOAD_TIMEOUT,
                )
                if r.status_code in {429, 500, 502, 503, 504, 567}:
                    time.sleep(min(15, 2 ** attempt))
                    continue
                r.raise_for_status()
                if not r.content:
                    raise RuntimeError("empty image response")
                mime, ext = image_meta(r.headers.get("Content-Type", ""), url)
                downloaded.append({
                    "bytes": r.content,
                    "mime": mime,
                    "filename": f"kickcrate-{item['album_id']}-{idx:02d}{ext}",
                    "alt": f"{clean_title(item)} — image {idx}",
                })
                break
            except Exception as exc:
                if attempt == 4:
                    raise RuntimeError(f"Image download failed {url}: {exc}") from exc
                time.sleep(min(15, 2 ** attempt))
    return downloaded


def stage_images(images: list[dict[str, Any]]) -> list[dict[str, str]]:
    if not images:
        return []
    inputs = [
        {
            "resource": "IMAGE",
            "filename": img["filename"],
            "mimeType": img["mime"],
            "httpMethod": "POST",
        }
        for img in images
    ]
    data = graphql(STAGE_IMAGES, {"input": inputs})
    errors = data["stagedUploadsCreate"].get("userErrors") or []
    if errors:
        raise RuntimeError("; ".join(f"{e.get('field')}: {e.get('message')}" for e in errors))
    targets = data["stagedUploadsCreate"]["stagedTargets"]
    if len(targets) != len(images):
        raise RuntimeError(f"Expected {len(images)} staged targets, received {len(targets)}")
    media = []
    for img, target in zip(images, targets):
        params = {p["name"]: p["value"] for p in target.get("parameters") or []}
        upload = requests.post(
            target["url"],
            data=params,
            files={"file": (img["filename"], img["bytes"], img["mime"])},
            timeout=REQUEST_TIMEOUT,
        )
        if upload.status_code not in {200, 201, 204}:
            raise RuntimeError(f"Staged upload failed ({upload.status_code}): {upload.text[:300]}")
        media.append({
            "mediaContentType": "IMAGE",
            "originalSource": target["resourceUrl"],
            "alt": img["alt"],
        })
    return media


def create_or_update(item: dict[str, Any]) -> dict[str, Any]:
    album_id = str(item["album_id"])
    existing = find_existing(album_id)
    keep = existing[0] if existing else None
    if len(existing) > 1:
        print(
            f"WARN album {album_id} has {len(existing)} Shopify products; using oldest {keep['id']} and not deleting automatically.",
            flush=True,
        )

    already_has_media = bool(keep and ((keep.get("metafield") or {}).get("value") == "true"))
    media = []
    media_imported = already_has_media
    if not already_has_media:
        downloaded = download_images(item)
        if downloaded:
            media = stage_images(downloaded)
            media_imported = bool(media)

    payload = product_payload(item, media_imported=media_imported)

    if keep:
        payload["id"] = keep["id"]
        data = graphql(UPDATE_PRODUCT, {"product": payload, "media": media or None})
        check_user_errors(data, "productUpdate")
        product = data["productUpdate"]["product"]
        action = "updated"
    else:
        data = graphql(CREATE_PRODUCT, {"product": payload, "media": media or None})
        check_user_errors(data, "productCreate")
        product = data["productCreate"]["product"]
        action = "created"

    return {
        "action": action,
        "album_id": album_id,
        "product_id": product["id"],
        "handle": product.get("handle"),
        "title": product.get("title"),
        "images_submitted": len(media),
    }


def load_catalog() -> list[dict[str, Any]]:
    data = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    out = []
    for item in data:
        source_title = str(item.get("source_title") or "")
        if NON_SHIRT_RE.search(source_title):
            continue
        if not item.get("album_id") or not item.get("team") or not item.get("country") or not item.get("league"):
            continue
        out.append(item)
    return out


def write_report(report: dict[str, Any]) -> Path:
    path = REPORT_DIR / f"shard-{SHARD_INDEX:02d}-of-{SHARD_COUNT:02d}.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def main() -> None:
    catalog = load_catalog()
    selected = [item for idx, item in enumerate(catalog) if idx % SHARD_COUNT == SHARD_INDEX]
    if MAX_PRODUCTS:
        selected = selected[:MAX_PRODUCTS]

    report: dict[str, Any] = {
        "store": STORE,
        "api_version": API_VERSION,
        "catalog_total_after_shirt_filter": len(catalog),
        "shard_count": SHARD_COUNT,
        "shard_index": SHARD_INDEX,
        "selected_products": len(selected),
        "created": 0,
        "updated": 0,
        "failed": 0,
        "results": [],
        "failures": [],
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    print(
        f"KickCrate import shard {SHARD_INDEX + 1}/{SHARD_COUNT}: "
        f"{len(selected)} of {len(catalog)} shirt records",
        flush=True,
    )

    try:
        for pos, item in enumerate(selected, 1):
            album_id = str(item.get("album_id"))
            try:
                result = create_or_update(item)
                report[result["action"]] += 1
                report["results"].append(result)
                print(
                    f"[{pos}/{len(selected)}] {result['action'].upper()} "
                    f"{album_id} | {result['title']} | images={result['images_submitted']}",
                    flush=True,
                )
            except Exception as exc:
                report["failed"] += 1
                failure = {
                    "album_id": album_id,
                    "title": clean_title(item),
                    "error": str(exc),
                }
                report["failures"].append(failure)
                print(f"[{pos}/{len(selected)}] FAILED {album_id}: {exc}", file=sys.stderr, flush=True)

            if pos % 25 == 0:
                write_report(report)
    finally:
        report["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        path = write_report(report)
        print(
            f"REPORT {path}: created={report['created']} updated={report['updated']} failed={report['failed']}",
            flush=True,
        )

    if report["failed"]:
        raise SystemExit(f"{report['failed']} products failed; rerun is safe and idempotent.")


if __name__ == "__main__":
    main()
