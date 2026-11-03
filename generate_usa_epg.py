#!/usr/bin/env python3
"""Build a compact USA XMLTV guide for ``usa_tv_next.m3u``.

The playlist draws on two community guides.  This script downloads both,
keeps only the channels that appear in ``usa_epg_aliases.json``, rewrites their
ids to the same canonical ids used by the playlist, and writes one small guide:

    usa_epg.xml
    usa_epg.xml.gz
    usa_epg_report.csv

Usage:
    python generate_usa_epg.py
    python generate_usa_epg.py --refresh
"""

from __future__ import annotations

import argparse
import copy
import csv
import gzip
import html
import json
import re
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from pathlib import Path

from usa_epg_common import canonical_id, clean_channel_name

SOURCES = {
    "kanya": "https://epg.kanya.io/us/guide.xml.gz",
    "epgshare": "https://epgshare01.online/epgshare01/epg_ripper_US2.xml.gz",
}
DEFAULT_ALIASES = Path("usa_epg_aliases.json")
DEFAULT_M3U = Path("usa_tv_next.m3u")
DEFAULT_OUTPUT = Path("usa_epg.xml")
DEFAULT_OUTPUT_GZ = Path("usa_epg.xml.gz")
DEFAULT_REPORT = Path("usa_epg_report.csv")
DEFAULT_CACHE = Path("/tmp/usa-epg")
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)
EXTINF_ID_RE = re.compile(r'tvg-id="([^"]*)"')
EXTINF_NAME_RE = re.compile(r'tvg-name="([^"]*)"')


def download(url: str, destination: Path, refresh: bool) -> Path:
    """Download a guide to the cache, reusing an existing copy when possible."""
    if destination.is_file() and destination.stat().st_size > 0 and not refresh:
        print(f"      using cached {destination.name} ({destination.stat().st_size:,} bytes)")
        return destination

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".part")
    print(f"      downloading {url} ...")
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            with temporary.open("wb") as output:
                while True:
                    chunk = response.read(1024 * 256)
                    if not chunk:
                        break
                    output.write(chunk)
    except (OSError, urllib.error.URLError) as exc:
        temporary.unlink(missing_ok=True)
        raise RuntimeError(f"could not download {url}: {exc}") from exc

    temporary.replace(destination)
    print(f"      saved {destination.name} ({destination.stat().st_size:,} bytes)")
    return destination


def parse_guide(path: Path, needed_ids: set[str]) -> tuple[dict[str, ET.Element], list[ET.Element], Counter[str]]:
    """Extract only the channels/programmes referenced by ``needed_ids``."""
    channels: dict[str, ET.Element] = {}
    programmes: list[ET.Element] = []
    programme_counts: Counter[str] = Counter()

    with gzip.open(path, "rb") as handle:
        for _event, element in ET.iterparse(handle, events=("end",)):
            if element.tag == "channel":
                channel_id = element.get("id")
                if channel_id in needed_ids:
                    channels[channel_id] = copy.deepcopy(element)
                element.clear()
            elif element.tag == "programme":
                channel_id = element.get("channel")
                if channel_id in needed_ids:
                    programmes.append(copy.deepcopy(element))
                    programme_counts[channel_id] += 1
                element.clear()

    return channels, programmes, programme_counts


def load_aliases(path: Path) -> dict[str, dict]:
    if not path.is_file():
        raise SystemExit(f"ERROR: alias file not found: {path}")
    raw = json.loads(path.read_text(encoding="utf-8"))
    aliases: dict[str, dict] = {}
    for name, value in raw.items():
        if not isinstance(value, dict):
            continue
        aliases[clean_channel_name(name)] = value
    return aliases


def parse_m3u_channels(path: Path) -> dict[str, str]:
    """Return {tvg-id: tvg-name} from the generated playlist."""
    if not path.is_file():
        return {}
    channels: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("#EXTINF"):
            continue
        id_match = EXTINF_ID_RE.search(line)
        name_match = EXTINF_NAME_RE.search(line)
        if id_match and name_match:
            channels[id_match.group(1)] = html.unescape(name_match.group(1))
    return channels


def set_display_name(channel: ET.Element, name: str) -> None:
    for existing in channel.findall("display-name"):
        channel.remove(existing)
    display = ET.Element("display-name")
    display.text = name
    channel.insert(0, display)


def build(
    aliases_path: Path,
    m3u_path: Path,
    output_path: Path,
    output_gz_path: Path,
    report_path: Path,
    cache_dir: Path,
    refresh: bool,
) -> int:
    aliases = load_aliases(aliases_path)
    playlist_channels = parse_m3u_channels(m3u_path)
    playlist_ids = set(playlist_channels)

    needed: dict[str, set[str]] = defaultdict(set)
    for mapping in aliases.values():
        source = mapping.get("source")
        source_id = mapping.get("id")
        if source in SOURCES and source_id:
            needed[source].add(source_id)

    print(f"[1/4] {len(aliases)} aliases across {len(needed)} guide sources.")
    source_channels: dict[str, dict[str, ET.Element]] = {}
    source_programmes: dict[str, list[ET.Element]] = {}
    source_counts: dict[str, Counter[str]] = {}
    failed_sources: set[str] = set()

    for source, ids in needed.items():
        print(f"[2/4] Fetching {source} ({len(ids)} channels) ...")
        try:
            archive = download(
                SOURCES[source], cache_dir / f"{source}.xml.gz", refresh=refresh
            )
            channels, programmes, counts = parse_guide(archive, ids)
        except RuntimeError as exc:
            print(f"      WARNING: {exc}")
            failed_sources.add(source)
            continue
        source_channels[source] = channels
        source_programmes[source] = programmes
        source_counts[source] = counts
        print(f"      kept {len(channels)} channels, {len(programmes):,} programmes")

    output_channels: list[ET.Element] = []
    output_programmes: list[ET.Element] = []
    id_map: dict[tuple[str, str], str] = {}
    channel_programme_counts: Counter[str] = Counter()
    missing: list[tuple[str, str, str]] = []

    for name, mapping in sorted(aliases.items(), key=lambda item: item[0].casefold()):
        source = mapping.get("source")
        source_id = mapping.get("id")
        if source not in SOURCES or not source_id:
            continue
        if source in failed_sources:
            missing.append((name, source, source_id))
            continue

        channel = source_channels.get(source, {}).get(source_id)
        if channel is None:
            missing.append((name, source, source_id))
            continue

        canonical = canonical_id(name)
        if playlist_ids and canonical not in playlist_ids:
            continue
        copied = copy.deepcopy(channel)
        copied.set("id", canonical)
        set_display_name(copied, name)
        output_channels.append(copied)
        id_map[(source, source_id)] = canonical
        channel_programme_counts[canonical] = source_counts[source][source_id]

    for source, programmes in source_programmes.items():
        for programme in programmes:
            old_id = programme.get("channel")
            canonical = id_map.get((source, old_id))
            if not canonical:
                continue
            copied = copy.deepcopy(programme)
            copied.set("channel", canonical)
            output_programmes.append(copied)

    output_programmes.sort(key=lambda programme: programme.get("start", ""))
    output_channels.sort(key=lambda channel: channel.get("id", ""))

    tv = ET.Element(
        "tv",
        {
            "generator-info-name": "tvepgjio USA EPG",
            "generator-info-url": "https://github.com/Abinanthankv/tvepgjio",
        },
    )
    tv.extend(output_channels)
    tv.extend(output_programmes)

    try:
        ET.indent(tv, space="  ")
    except AttributeError:
        pass

    xml_bytes = ET.tostring(tv, encoding="utf-8", xml_declaration=True)
    output_path.write_bytes(xml_bytes)
    with output_gz_path.open("wb") as raw:
        with gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as compressed:
            compressed.write(xml_bytes)

    print(
        f"[3/4] Wrote {output_path} and {output_gz_path.name}: "
        f"{len(output_channels)} channels, {len(output_programmes):,} programmes."
    )

    report_rows: list[dict[str, object]] = []
    report_ids = set(playlist_channels)
    for tvg_id, name in sorted(playlist_channels.items(), key=lambda item: item[1].casefold()):
        mapping = aliases.get(name)
        if not mapping:
            report_rows.append(
                {
                    "channel": name,
                    "tvg_id": tvg_id,
                    "source": "",
                    "source_id": "",
                    "programmes": 0,
                    "status": "unmapped",
                }
            )
            continue
        count = channel_programme_counts.get(tvg_id, 0)
        report_rows.append(
            {
                "channel": name,
                "tvg_id": tvg_id,
                "source": mapping.get("source", ""),
                "source_id": mapping.get("id", ""),
                "programmes": count,
                "status": "ok" if count else "no_programmes",
            }
        )

    for name, source, source_id in missing:
        tvg_id = canonical_id(name)
        if tvg_id in report_ids:
            continue
        report_rows.append(
            {
                "channel": name,
                "tvg_id": tvg_id,
                "source": source,
                "source_id": source_id,
                "programmes": 0,
                "status": "missing",
            }
        )

    with report_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["channel", "tvg_id", "source", "source_id", "programmes", "status"],
        )
        writer.writeheader()
        writer.writerows(report_rows)

    ok = sum(1 for row in report_rows if row["status"] == "ok")
    print(
        f"[4/4] Report: {ok}/{len(report_rows)} playlist channels have programmes; "
        f"{len(missing)} aliases missing from their guide."
    )
    if failed_sources:
        print(f"      Failed sources: {', '.join(sorted(failed_sources))}")
        if not output_channels:
            return 1

    for source in sorted(needed):
        count = sum(1 for mapping in aliases.values() if mapping.get("source") == source)
        print(f"      {source:<10} {count:>3} mapped channels")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--aliases", type=Path, default=DEFAULT_ALIASES)
    parser.add_argument("--m3u", type=Path, default=DEFAULT_M3U)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--output-gz", type=Path, default=DEFAULT_OUTPUT_GZ)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE)
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="download fresh guides instead of using the cache",
    )
    args = parser.parse_args()

    print("==================================================")
    print("        USA TV Next XMLTV Guide Generator")
    print("==================================================")

    return build(
        args.aliases,
        args.m3u,
        args.output,
        args.output_gz,
        args.report,
        args.cache_dir,
        args.refresh,
    )


if __name__ == "__main__":
    raise SystemExit(main())
