#!/usr/bin/env python3
"""Extract playable stream URLs from a Stremio addon.

The CNCVerse Bridge addon exposes the normal Stremio endpoints:

    /manifest.json
    /catalog/{type}/{catalog_id}.json
    /meta/{type}/{id}.json
    /stream/{type}/{id}.json

Catalog items use ids such as ``cnc:<base64-json>``.  The base64 payload
contains the upstream URL, cookie, key and key id.  The stream endpoint adds
the playable proxy URL and the ClearKey value.

Examples:
    python extract_cncverse.py --list-catalogs
    python extract_cncverse.py --catalog cnc_JIOTVPlusIND3_tv --limit 3
    python extract_cncverse.py --all --quality highest
    python extract_cncverse.py --all --quality lowest --split-catalogs

The script writes a combined ``cncverse.m3u`` and, with
``--split-catalogs``, one M3U per catalog under ``cncverse_playlists/``.
Expired URLs are dropped, and URLs expiring within ``--min-ttl`` seconds
are retried before being skipped.  It only reads the addon.  It does not
touch the existing USA files.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import html
import json
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

DEFAULT_MANIFEST = (
    "https://cncverse.dpdns.org/u/p_j98yszu454o7/manifest.json"
)
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)
QUALITY_RE = re.compile(r"(\d{3,4})p", re.IGNORECASE)
SOURCE_RE = re.compile(r"Source:\s*([^\n•]+)", re.IGNORECASE)
CNC_ID_RE = re.compile(r"^cnc:(?P<payload>.+)$")
EXP_RE = re.compile(r"exp(?:%3D|=)(\d{9,})", re.IGNORECASE)


def url_expiry(url: str) -> int | None:
    """Return the Unix expiry embedded in a proxied URL, if present."""
    matches = EXP_RE.findall(url or "")
    if not matches:
        return None
    try:
        return int(matches[-1])
    except ValueError:
        return None


def is_expired(url: str, min_ttl: int = 0) -> bool:
    expiry = url_expiry(url)
    return expiry is not None and expiry <= int(time.time()) + min_ttl


def fetch_json(url: str, timeout: int) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


def decode_cnc_id(item_id: str) -> dict | None:
    """Decode the base64 JSON embedded in a ``cnc:`` item id."""
    match = CNC_ID_RE.match(item_id or "")
    if not match:
        return None
    payload = match.group("payload")
    padding = "=" * (-len(payload) % 4)
    for decoder in (base64.urlsafe_b64decode, base64.b64decode):
        try:
            raw = decoder(payload + padding).decode("utf-8", "replace")
        except (ValueError, binascii.Error):
            continue
        # The payload is usually ``CatalogId::{"url": ...}``.
        json_start = raw.find("{")
        if json_start == -1:
            continue
        try:
            decoded = json.loads(raw[json_start:])
        except json.JSONDecodeError:
            continue
        if isinstance(decoded, dict):
            return decoded
    return None


def catalog_url(base: str, catalog: dict, skip: int) -> str:
    catalog_id = urllib.parse.quote(str(catalog["id"]), safe="")
    return f"{base}/catalog/{catalog['type']}/{catalog_id}/skip={skip}.json"


def fetch_catalog(
    base: str,
    catalog: dict,
    timeout: int,
    limit: int,
    page_size: int,
) -> list[dict]:
    """Fetch all pages of a catalog, deduplicating by item id."""
    items: list[dict] = []
    seen: set[str] = set()
    skip = 0
    while True:
        try:
            data = fetch_json(catalog_url(base, catalog, skip), timeout)
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                break
            raise
        metas = data.get("metas") or []
        if not metas:
            break
        added = 0
        for meta in metas:
            item_id = str(meta.get("id") or "")
            if not item_id or item_id in seen:
                continue
            seen.add(item_id)
            items.append(meta)
            added += 1
            if limit and len(items) >= limit:
                return items
        if added == 0 or len(metas) < page_size:
            break
        skip += page_size
    return items


def stream_url(base: str, item: dict) -> str:
    item_id = urllib.parse.quote(str(item["id"]), safe="")
    return f"{base}/stream/{item['type']}/{item_id}.json"


def quality_value(text: str) -> int:
    match = QUALITY_RE.search(text or "")
    if not match:
        return 0
    value = int(match.group(1))
    return value if value >= 100 else value * 100


def select_stream(streams: list[dict], policy: str, min_ttl: int = 0) -> list[dict]:
    """Filter to playable, non-expired URLs and select quality variants."""
    playable: list[dict] = []
    for stream in streams:
        url = str(stream.get("url") or "").strip()
        name = str(stream.get("name") or "")
        title = str(stream.get("title") or "")
        if not url.startswith(("http://", "https://")):
            continue
        if is_expired(url, min_ttl):
            continue
        if "support the project" in name.lower() or "donate" in title.lower():
            continue
        quality = quality_value(f"{title}\n{name}")
        playable.append(
            {
                "url": url,
                "name": name,
                "title": title,
                "quality": quality,
                "clearkey": stream.get("clearkey") or "",
                "behaviorHints": stream.get("behaviorHints") or {},
            }
        )

    if not playable:
        return []
    if policy == "all":
        return playable
    if policy == "highest":
        best = max(item["quality"] for item in playable)
    else:
        best = min(item["quality"] for item in playable)
    return [item for item in playable if item["quality"] == best]


def slugify(value: str) -> str:
    normalized = (
        unicodedata.normalize("NFKD", str(value or ""))
        .encode("ascii", "ignore")
        .decode("ascii")
    )
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", normalized).strip("-").lower()
    return slug or "channel"


def clean_catalog_name(value: str) -> str:
    text = str(value or "")
    text = re.sub(r"[^\x20-\x7E]+", " ", text)
    text = re.sub(r"\(\s*tv\s*\)", "", text, flags=re.IGNORECASE)
    return " ".join(text.split()) or "CNCVerse"


def m3u_attr(value: str) -> str:
    return html.escape(str(value or ""), quote=True)


def kodi_license_key(clearkey: str) -> str:
    """Convert the addon's ``key:keyid`` value to Kodi's ``keyid:key``."""
    parts = str(clearkey or "").split(":")
    if len(parts) != 2:
        return ""
    key, keyid = parts
    if not re.fullmatch(r"[0-9a-fA-F]{32}", key):
        return ""
    if not re.fullmatch(r"[0-9a-fA-F]{32}", keyid):
        return ""
    return f"{keyid}:{key}"


def write_m3u(path: Path, records: list[dict], title: str) -> None:
    """Write a combined or per-catalog M3U playlist."""
    lines = ["#EXTM3U"]
    id_counts: Counter[str] = Counter()
    seen: set[tuple[str, int, str]] = set()

    for record in sorted(
        records,
        key=lambda item: (
            clean_catalog_name(item.get("catalog_name", "")).casefold(),
            str(item.get("channel") or "").casefold(),
            item.get("quality") or 0,
        ),
    ):
        key = (
            str(record.get("channel") or ""),
            int(record.get("quality") or 0),
            str(record.get("url") or ""),
        )
        if key in seen:
            continue
        seen.add(key)

        catalog = clean_catalog_name(record.get("catalog_name", ""))
        channel = str(record.get("channel") or "Channel")
        base_id = f"cncverse-{slugify(catalog)}-{slugify(channel)}"
        id_counts[base_id] += 1
        tvg_id = base_id if id_counts[base_id] == 1 else f"{base_id}-{id_counts[base_id]}"
        quality = int(record.get("quality") or 0)
        quality_text = f" ({quality}p)" if quality else ""
        attrs = [
            f'tvg-id="{m3u_attr(tvg_id)}"',
            f'tvg-name="{m3u_attr(channel)}"',
        ]
        logo = str(record.get("poster") or "").strip()
        if logo:
            attrs.append(f'tvg-logo="{m3u_attr(logo)}"')
        attrs.append(f'group-title="{m3u_attr(f"CNCVerse | {catalog}")}"')
        lines.append(
            f'#EXTINF:-1 {" ".join(attrs)},{m3u_attr(channel + quality_text)}'
        )
        url = str(record.get("url") or "")
        hints = record.get("behaviorHints") or {}
        proxy_headers = (hints.get("proxyHeaders") or {}).get("request") or {}
        is_proxy = url.startswith("http://129.225.106.195/")
        # The CNCVerse proxy rejects VLC's default user-agent with HTTP 500.
        # Direct Jio HLS URLs need the provider's user-agent and cookie.
        vlc_user_agent = "Mozilla/5.0" if is_proxy else (
            str(proxy_headers.get("User-Agent") or "Mozilla/5.0")
        )
        lines.append(f"#EXTVLCOPT:http-user-agent={vlc_user_agent}")
        if proxy_headers.get("Referer"):
            lines.append(f"#EXTVLCOPT:http-referrer={proxy_headers['Referer']}")

        lines.append("#KODIPROP:inputstream=inputstream.adaptive")
        lines.append("#KODIPROP:inputstream.adaptive.manifest_type=hls")
        if proxy_headers:
            header_parts = []
            for header_name in ("User-Agent", "Cookie", "Referer", "Origin"):
                header_value = proxy_headers.get(header_name)
                if header_value:
                    header_parts.append(f"{header_name}={header_value}")
            if header_parts:
                lines.append(
                    "#KODIPROP:inputstream.adaptive.stream_headers="
                    + "&".join(header_parts)
                )
        license_key = kodi_license_key(record.get("clearkey", ""))
        if license_key:
            lines.append("#KODIPROP:inputstream.adaptive.license_type=clearkey")
            lines.append(f"#KODIPROP:inputstream.adaptive.license_key={license_key}")
        lines.append(url)

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"      wrote {title}: {path} ({len(seen)} streams)")


def extract_item(
    base: str,
    catalog: dict,
    item: dict,
    quality: str,
    timeout: int,
    min_ttl: int = 300,
    retries: int = 2,
) -> tuple[list[dict], dict | None]:
    """Fetch one item's stream endpoint and return records or an error."""
    meta = decode_cnc_id(str(item.get("id") or ""))
    last_error = "no playable url"
    for attempt in range(retries + 1):
        try:
            payload = fetch_json(stream_url(base, item), timeout)
        except (urllib.error.URLError, json.JSONDecodeError, TimeoutError) as exc:
            last_error = str(exc)
            if attempt < retries:
                time.sleep(1.5 * (attempt + 1))
                continue
            return [], {
                "catalog": catalog.get("id"),
                "channel": item.get("name"),
                "error": last_error,
            }

        selected = select_stream(payload.get("streams") or [], quality, min_ttl)
        if selected:
            records = []
            for stream in selected:
                records.append(
                    {
                        "catalog": catalog.get("id"),
                        "catalog_name": catalog.get("name"),
                        "channel": item.get("name"),
                        "poster": item.get("poster") or "",
                        "item_id": item.get("id"),
                        "type": item.get("type"),
                        "quality": stream["quality"],
                        "stream_name": stream["name"],
                        "stream_title": stream["title"],
                        "url": stream["url"],
                        "clearkey": stream["clearkey"],
                        "behaviorHints": stream["behaviorHints"],
                        "upstream": meta or {},
                        "expires": url_expiry(stream["url"]),
                    }
                )
            return records, None

        last_error = "no playable url (expired or missing)"
        if attempt < retries:
            time.sleep(1.5 * (attempt + 1))

    return [], {
        "catalog": catalog.get("id"),
        "channel": item.get("name"),
        "error": last_error,
    }


def extract(
    manifest_url: str,
    catalog_filter: str,
    all_catalogs: bool,
    quality: str,
    limit: int,
    timeout: int,
    page_size: int,
    output_json: Path,
    output_m3u: Path,
    split_catalogs: bool,
    playlist_dir: Path,
    workers: int,
    min_ttl: int,
) -> int:
    manifest = fetch_json(manifest_url, timeout)
    base = manifest_url.rsplit("/", 1)[0]
    catalogs = manifest.get("catalogs") or []
    if not catalogs:
        print("No catalogs in manifest", file=sys.stderr)
        return 1

    if catalog_filter:
        catalogs = [
            catalog
            for catalog in catalogs
            if str(catalog.get("id")) == catalog_filter
        ]
        if not catalogs:
            print(f"Catalog not found: {catalog_filter}", file=sys.stderr)
            return 1
    elif not all_catalogs:
        print("Catalogs in manifest:")
        for catalog in catalogs:
            print(f"  {catalog.get('type')}  {catalog.get('id')}  {catalog.get('name')}")
        print("\nUse --catalog ID, or --all to extract every catalog.")
        return 0

    records: list[dict] = []
    errors: list[dict] = []
    for catalog in catalogs:
        print(f"[catalog] {catalog.get('name')} ({catalog.get('id')})")
        items = fetch_catalog(base, catalog, timeout, limit, page_size)
        print(f"          {len(items)} items")
        if workers > 1:
            with ThreadPoolExecutor(max_workers=workers) as executor:
                futures = {
                    executor.submit(
                        extract_item,
                        base,
                        catalog,
                        item,
                        quality,
                        timeout,
                        min_ttl,
                    ): item
                    for item in items
                }
                for index, future in enumerate(as_completed(futures), 1):
                    item_records, error = future.result()
                    records.extend(item_records)
                    if error:
                        errors.append(error)
                    if index % 50 == 0 or index == len(items):
                        print(f"          {index}/{len(items)}")
        else:
            for index, item in enumerate(items, 1):
                item_records, error = extract_item(
                    base, catalog, item, quality, timeout, min_ttl
                )
                records.extend(item_records)
                if error:
                    errors.append(error)
                if index % 10 == 0:
                    print(f"          {index}/{len(items)}")

    output_json.write_text(
        json.dumps(
            {
                "manifest": manifest_url,
                "quality_policy": quality,
                "min_ttl_seconds": min_ttl,
                "generated_at": int(time.time()),
                "records": records,
                "errors": errors,
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    write_m3u(output_m3u, records, "combined playlist")
    if split_catalogs:
        by_catalog: dict[str, list[dict]] = {}
        for record in records:
            by_catalog.setdefault(str(record.get("catalog") or ""), []).append(record)
        for catalog_id, catalog_records in by_catalog.items():
            catalog_name = clean_catalog_name(catalog_records[0].get("catalog_name", ""))
            path = playlist_dir / f"cncverse_{slugify(catalog_name)}.m3u"
            write_m3u(path, catalog_records, f"{catalog_name} playlist")

    print(
        f"\nWrote {output_json} ({len(records)} streams, {len(errors)} errors) "
        f"and {output_m3u}"
    )
    if records:
        print("Quality counts:", dict(Counter(r["quality"] for r in records)))
    if errors:
        print("First errors:")
        for error in errors[:5]:
            print(" ", error)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default=DEFAULT_MANIFEST)
    parser.add_argument("--catalog", default="")
    parser.add_argument("--all", action="store_true", dest="all_catalogs")
    parser.add_argument("--list-catalogs", action="store_true")
    parser.add_argument(
        "--quality",
        choices=("lowest", "highest", "all"),
        default="lowest",
    )
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--page-size", type=int, default=100)
    parser.add_argument(
        "--output-json",
        type=Path,
        default=Path("cncverse_streams.json"),
    )
    parser.add_argument(
        "--output-m3u",
        type=Path,
        default=Path("cncverse.m3u"),
    )
    parser.add_argument(
        "--split-catalogs",
        action="store_true",
        help="also write one M3U per catalog",
    )
    parser.add_argument(
        "--playlist-dir",
        type=Path,
        default=Path("cncverse_playlists"),
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=6,
        help="parallel stream requests (default: 6)",
    )
    parser.add_argument(
        "--min-ttl",
        type=int,
        default=300,
        help="drop URLs expiring within this many seconds (default: 300)",
    )
    args = parser.parse_args()

    return extract(
        args.manifest,
        "" if args.list_catalogs else args.catalog,
        args.all_catalogs,
        args.quality,
        args.limit,
        args.timeout,
        args.page_size,
        args.output_json,
        args.output_m3u,
        args.split_catalogs,
        args.playlist_dir,
        args.workers,
        args.min_ttl,
    )


if __name__ == "__main__":
    raise SystemExit(main())
