#!/usr/bin/env python3
"""Convert the USA TV Next Stremio addon into a clean, EPG-ready M3U.

The upstream addon exposes every stream it knows about, including audio-only
feeds, duplicate quality variants and a few feeds that do not belong to the
channel at all.  This converter:

* drops audio-only, dead, macro-filled and known non-US/junk streams;
* removes duplicate URLs (ignoring tracking parameters);
* gives every feed a unique, readable title (channel + source + quality);
* uses stable XMLTV ids that match ``usa_epg.xml.gz``;
* attaches the generated USA guide through ``url-tvg`` / ``x-tvg-url``;
* sorts channels by genre and name so the output is deterministic.

Usage:
    python convert_stremio_to_m3u.py
    python convert_stremio_to_m3u.py --repo-dir /tmp/opencode/usa-tv-next
"""

from __future__ import annotations

import argparse
import html
import json
import re
import shutil
import subprocess
from collections import Counter
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from usa_epg_common import canonical_id, clean_channel_name

UPSTREAM_REPO = "https://github.com/yowmamasita/usa-tv-next"
DEFAULT_REPO_DIR = Path("/tmp/usa-tv-next")
DEFAULT_OUTPUT = Path("usa_tv_next.m3u")
DEFAULT_EPG_URL = (
    "https://raw.githubusercontent.com/Abinanthankv/tvepgjio/main/usa_epg.xml.gz"
)
ALIASES_FILE = Path("usa_epg_aliases.json")

GROUP_ORDER = [
    "Local",
    "News",
    "Sports",
    "Entertainment",
    "Premium",
    "Lifestyle",
    "Kids",
    "Documentaries",
    "Music",
    "Latino",
    "General",
]
QUALITY_RANK = {"4K": 4, "UHD": 4, "FHD": 3, "HD": 2, "SD": 1}

# Feeds that are clearly not the US channel the catalog entry claims to be.
JUNK_URL_PATTERNS = [
    r"abc-(?:nsw|qld|sa|me|tv-plus)\b",
    r"(?:weather|news|business|sport)_in_90_seconds",
    r"tvpass\.org",
    r"tvkaista\.net",
    r"qvcuk",
]
JUNK_URL_RE = re.compile("|".join(JUNK_URL_PATTERNS), re.IGNORECASE)
MACRO_URL_RE = re.compile(r"\{[A-Z_]+\}")
DEAD_STREAM_RE = re.compile(r"\[dead\]|\bdead\b|\boffline\b|\bnot working\b", re.I)

# Friendly names for the short tags the upstream harvester stores in the
# stream description (``HV:JMP2``, ``HV:SERVICE-STIT``, ...).
TAG_SOURCES = {
    "JMP2": "JMP2",
    "LIVE-MANIFES": "Tubi",
    "LIVE-MANIFEST": "Tubi",
    "SERVICE-STIT": "Pluto TV",
    "PTV": "Pluto TV",
    "AMD-MEDIATOR": "Amagi",
    "CDN-UW2-PROD": "Amagi",
    "AEGIS-CLOUDF": "Tubi",
    "XM": "Xumo",
    "MJE": "MJE",
    "ST": "Stirr",
    "LN": "Local Now",
    "HLS": "",
    "MASTER": "",
    "CLIENTS": "",
    "INDEX": "",
}

# Prefer the actual host over the cryptic harvester tag when we recognise it.
HOST_SOURCES = [
    ("pluto.tv", "Pluto TV"),
    ("tubi", "Tubi"),
    ("amagi.tv", "Amagi"),
    ("uplynk", "Uplynk"),
    ("jmp2.uk", "JMP2"),
    ("mjh.nz", "MJH"),
    ("bloomberg.com", "Bloomberg"),
    ("dai.google.com", "Google DAI"),
    ("xumo", "Xumo"),
    ("roku", "Roku"),
    ("samsung", "Samsung TV Plus"),
    ("plex.tv", "Plex"),
    ("akamaized", "Akamai"),
    ("cloudfront", "CloudFront"),
]

TRACKING_PARAMS = {
    "checkedby",
    "fbclid",
    "gclid",
    "dclid",
    "msclkid",
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
}


def ensure_repo(repo_dir: Path, update: bool) -> None:
    """Clone the upstream addon, or refresh an existing checkout."""
    if (repo_dir / ".git").is_dir():
        if update:
            print(f"[1/4] Updating {repo_dir} ...")
            result = subprocess.run(
                ["git", "-C", str(repo_dir), "pull", "--ff-only"],
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                print("      pull failed; using the existing checkout")
        return

    if repo_dir.exists():
        shutil.rmtree(repo_dir)
    print(f"[1/4] Cloning {UPSTREAM_REPO} ...")
    subprocess.run(
        ["git", "clone", "--depth", "1", UPSTREAM_REPO, str(repo_dir)],
        check=True,
    )


def load_streams(repo_dir: Path, meta: dict) -> list[dict]:
    """Return catalog streams, with the stream endpoint taking precedence."""
    by_url: dict[str, dict] = {}
    for stream in meta.get("streams") or []:
        url = (stream.get("url") or "").strip() if isinstance(stream, dict) else ""
        if url:
            by_url[url] = stream

    stream_file = repo_dir / "stream" / "tv" / f"{meta.get('id', '')}.json"
    if stream_file.is_file():
        try:
            payload = json.loads(stream_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            payload = {}
        for stream in payload.get("streams") or []:
            url = (stream.get("url") or "").strip() if isinstance(stream, dict) else ""
            if url:
                by_url[url] = stream

    return list(by_url.values())


def quality_of(stream: dict) -> str:
    """Return 4K/UHD/FHD/HD/SD/Audio from the upstream stream name."""
    raw = (stream.get("name") or "").upper()
    if "AUDIO" in raw:
        return "Audio"
    match = re.search(r"\b(4K|UHD|FHD|HD|SD)\b", raw)
    return match.group(1) if match else "SD"


def is_dead(stream: dict) -> bool:
    text = f"{stream.get('name', '')} {stream.get('description', '')}"
    return bool(DEAD_STREAM_RE.search(text))


def source_of(stream: dict) -> str:
    """Return a short, human-readable source label for a feed."""
    url = stream.get("url") or ""
    host = (urlsplit(url).hostname or "").lower()
    for needle, label in HOST_SOURCES:
        if needle in host:
            return label

    description = (stream.get("description") or "").strip()
    tag = description[3:].strip() if description.upper().startswith("HV:") else description
    tag = tag.upper()
    if tag in TAG_SOURCES:
        return TAG_SOURCES[tag]
    if re.fullmatch(r"[0-9A-F]{8,}", tag) or tag.isdigit():
        return ""
    if tag and len(tag) <= 12:
        return tag
    return ""


def normalize_url(url: str) -> str:
    """Normalize a URL for duplicate detection without dropping required params."""
    parts = urlsplit(url)
    query = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key.lower() not in TRACKING_PARAMS
    ]
    return urlunsplit(
        (
            parts.scheme.lower(),
            parts.netloc.lower(),
            parts.path,
            urlencode(query, doseq=True),
            "",
        )
    )


def m3u_attr(value: str) -> str:
    """Escape a value for an M3U attribute."""
    return html.escape(str(value), quote=True)


def build(repo_dir: Path, output: Path, epg_url: str) -> int:
    catalog_file = repo_dir / "catalog" / "tv" / "all.json"
    if not catalog_file.is_file():
        print(f"ERROR: catalog not found at {catalog_file}")
        return 1

    catalog = json.loads(catalog_file.read_text(encoding="utf-8"))
    metas = catalog.get("metas") or []
    stats: Counter[str] = Counter()
    channels: list[dict] = []

    for meta in metas:
        name = clean_channel_name(meta.get("name") or "Channel")
        genre = (meta.get("genre") or (meta.get("genres") or ["General"])[0] or "General").strip()
        if genre not in GROUP_ORDER:
            genre = genre.title()
        logo = meta.get("logo") or meta.get("poster") or ""

        kept: list[dict] = []
        seen_urls: dict[str, int] = {}
        for stream in load_streams(repo_dir, meta):
            stats["upstream_streams"] += 1
            url = (stream.get("url") or "").strip()
            if not url:
                stats["filtered_missing_url"] += 1
                continue
            if quality_of(stream) == "Audio":
                stats["filtered_audio"] += 1
                continue
            if is_dead(stream):
                stats["filtered_dead"] += 1
                continue
            if JUNK_URL_RE.search(url):
                stats["filtered_junk"] += 1
                continue
            if MACRO_URL_RE.search(url):
                stats["filtered_macro"] += 1
                continue

            dedupe_key = normalize_url(url)
            if dedupe_key in seen_urls:
                stats["filtered_duplicate"] += 1
                # Prefer the version without tracking parameters.
                if url == dedupe_key:
                    kept[seen_urls[dedupe_key]]["url"] = url
                continue
            seen_urls[dedupe_key] = len(kept)

            kept.append(
                {
                    "url": url,
                    "quality": quality_of(stream),
                    "source": source_of(stream),
                }
            )

        if not kept:
            stats["channels_without_streams"] += 1
            continue

        kept.sort(
            key=lambda item: (
                -QUALITY_RANK.get(item["quality"], 0),
                item["source"].casefold(),
                normalize_url(item["url"]),
            )
        )

        base_labels = []
        for item in kept:
            parts = [part for part in (item["source"], item["quality"]) if part]
            base_labels.append(f"{name} ({' - '.join(parts)})" if parts else name)

        totals = Counter(base_labels)
        seen_labels: Counter[str] = Counter()
        for item, base in zip(kept, base_labels):
            seen_labels[base] += 1
            if totals[base] == 1 or seen_labels[base] == 1:
                item["title"] = base
            else:
                item["title"] = f"{base} #{seen_labels[base]}"

        channels.append(
            {"name": name, "genre": genre, "logo": logo, "streams": kept}
        )

    group_rank = {group: index for index, group in enumerate(GROUP_ORDER)}
    channels.sort(
        key=lambda channel: (
            group_rank.get(channel["genre"], len(GROUP_ORDER)),
            channel["name"].casefold(),
        )
    )

    aliases: dict[str, dict] = {}
    if ALIASES_FILE.is_file():
        try:
            raw_aliases = json.loads(ALIASES_FILE.read_text(encoding="utf-8"))
            aliases = {
                clean_channel_name(name): value
                for name, value in raw_aliases.items()
            }
        except json.JSONDecodeError:
            aliases = {}

    lines = [f'#EXTM3U url-tvg="{m3u_attr(epg_url)}" x-tvg-url="{m3u_attr(epg_url)}"']
    stream_count = 0
    mapped_channels = 0
    for channel in channels:
        tvg_id = canonical_id(channel["name"])
        if channel["name"] in aliases:
            mapped_channels += 1
        group = f"USA | {channel['genre']}"
        for item in channel["streams"]:
            lines.append(
                f'#EXTINF:-1 tvg-id="{m3u_attr(tvg_id)}" '
                f'tvg-name="{m3u_attr(channel["name"])}" '
                f'tvg-logo="{m3u_attr(channel["logo"])}" '
                f'group-title="{m3u_attr(group)}",{m3u_attr(item["title"])}'
            )
            lines.append(item["url"])
            stream_count += 1

    output.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"[2/4] Parsed {len(metas)} upstream channels, {stats['upstream_streams']} streams.")
    print(
        "      Filtered: "
        f"audio={stats['filtered_audio']}, "
        f"dead={stats['filtered_dead']}, "
        f"junk={stats['filtered_junk']}, "
        f"macro={stats['filtered_macro']}, "
        f"duplicate={stats['filtered_duplicate']}, "
        f"missing_url={stats['filtered_missing_url']}"
    )
    print(
        f"[3/4] Wrote {output} with {stream_count} streams from "
        f"{len(channels)} channels ({stats['channels_without_streams']} upstream "
        "channels had no usable stream)."
    )
    print(
        f"[4/4] EPG ids use {mapped_channels}/{len(channels)} mapped channels; "
        f"guide: {epg_url}"
    )

    for genre in GROUP_ORDER:
        count = sum(1 for channel in channels if channel["genre"] == genre)
        if count:
            print(f"      {genre:<16} {count:>3} channels")

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-dir",
        type=Path,
        default=DEFAULT_REPO_DIR,
        help="checkout of yowmamasita/usa-tv-next (default: %(default)s)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="output M3U file (default: %(default)s)",
    )
    parser.add_argument(
        "--epg-url",
        default=DEFAULT_EPG_URL,
        help="XMLTV URL embedded in #EXTM3U (default: %(default)s)",
    )
    parser.add_argument(
        "--no-update",
        action="store_true",
        help="use an existing checkout without running git pull",
    )
    args = parser.parse_args()

    print("==================================================")
    print("     USA TV Next Stremio Addon to M3U Converter")
    print("==================================================")

    try:
        ensure_repo(args.repo_dir, update=not args.no_update)
    except subprocess.CalledProcessError as exc:
        print(f"ERROR: could not clone/update the upstream repository: {exc}")
        return 1

    return build(args.repo_dir, args.output, args.epg_url)


if __name__ == "__main__":
    raise SystemExit(main())
