#!/usr/bin/env python3
"""Build a compact USA XMLTV guide for ``usa_tv_next.m3u``.

The playlist draws on three community guides.  This script downloads them,
keeps only the channels referenced by the playlist (curated aliases plus the
native Pluto ids embedded in Pluto stream URLs), rewrites curated ids to the
same canonical ids used by the playlist, and writes one small guide:

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
import datetime
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
    "pluto": "https://github.com/matthuisman/i.mjh.nz/raw/master/PlutoTV/us.xml.gz",
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
PLUTO_ID_RE = re.compile(r"^[a-f0-9]{24}$")


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
        if destination.is_file() and destination.stat().st_size > 0:
            print(
                f"      WARNING: download failed ({exc}); "
                f"using cached {destination.name}"
            )
            return destination
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

    native_pluto_ids = {tvg_id for tvg_id in playlist_ids if PLUTO_ID_RE.fullmatch(tvg_id)}

    needed: dict[str, set[str]] = defaultdict(set)
    for mapping in aliases.values():
        source = mapping.get("source")
        source_id = mapping.get("id")
        if source in SOURCES and source_id:
            needed[source].add(source_id)
    if native_pluto_ids:
        needed["pluto"].update(native_pluto_ids)

    print(
        f"[1/4] {len(aliases)} aliases, {len(native_pluto_ids)} native Pluto ids, "
        f"{len(needed)} guide sources."
    )
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
    id_map: dict[tuple[str, str], list[str]] = defaultdict(list)
    channel_programme_counts: Counter[str] = Counter()
    missing: list[tuple[str, str, str]] = []
    missing_native: set[str] = set()
    fallback_native: set[str] = set()

    for name, mapping in sorted(aliases.items(), key=lambda item: item[0].casefold()):
        source = mapping.get("source")
        source_id = mapping.get("id")
        if source not in SOURCES or not source_id:
            continue
        canonical = canonical_id(name)
        if playlist_ids and canonical not in playlist_ids:
            continue
        if source in failed_sources:
            missing.append((name, source, source_id))
            continue

        channel = source_channels.get(source, {}).get(source_id)
        if channel is None:
            missing.append((name, source, source_id))
            continue

        copied = copy.deepcopy(channel)
        copied.set("id", canonical)
        set_display_name(copied, name)
        output_channels.append(copied)
        id_map[(source, source_id)].append(canonical)
        channel_programme_counts[canonical] = source_counts[source][source_id]

    for native_id in sorted(native_pluto_ids):
        name = playlist_channels.get(native_id, native_id)
        channel = source_channels.get("pluto", {}).get(native_id)
        if channel is not None:
            copied = copy.deepcopy(channel)
            copied.set("id", native_id)
            set_display_name(copied, name)
            output_channels.append(copied)
            id_map[("pluto", native_id)].append(native_id)
            channel_programme_counts[native_id] = source_counts["pluto"][native_id]
            continue

        # The Pluto guide does not carry this native id.  Only fall back to the
        # curated national mapping when the channel has no other guide-bearing
        # stream, so extra Pluto feeds are not silently given a wrong schedule.
        mapping = aliases.get(name)
        canonical = canonical_id(name)
        if not mapping or (playlist_ids and canonical in playlist_ids):
            missing_native.add(native_id)
            continue
        source = mapping.get("source")
        source_id = mapping.get("id")
        fallback_channel = source_channels.get(source, {}).get(source_id)
        if not source or not source_id or fallback_channel is None:
            missing_native.add(native_id)
            continue

        copied = copy.deepcopy(fallback_channel)
        copied.set("id", native_id)
        set_display_name(copied, name)
        output_channels.append(copied)
        id_map[(source, source_id)].append(native_id)
        channel_programme_counts[native_id] = source_counts[source][source_id]
        fallback_native.add(native_id)

    for source, programmes in source_programmes.items():
        for programme in programmes:
            old_id = programme.get("channel")
            for target_id in id_map.get((source, old_id), []):
                copied = copy.deepcopy(programme)
                copied.set("channel", target_id)
                output_programmes.append(copied)

    output_programmes.sort(key=lambda programme: programme.get("start", ""))
    output_channels.sort(key=lambda channel: channel.get("id", ""))

    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d%H%M%S")
    future_programme_counts: Counter[str] = Counter()
    for programme in output_programmes:
        if programme.get("start", "")[:14] > now:
            future_programme_counts[programme.get("channel", "")] += 1

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
    missing_canonical = {canonical_id(name) for name, _source, _source_id in missing}
    for tvg_id, name in sorted(playlist_channels.items(), key=lambda item: item[1].casefold()):
        if tvg_id in native_pluto_ids and tvg_id not in fallback_native:
            mapping: dict | None = {"source": "pluto", "id": tvg_id}
        else:
            mapping = aliases.get(name)

        count = channel_programme_counts.get(tvg_id, 0)
        future = future_programme_counts.get(tvg_id, 0)
        if not mapping:
            source = ""
            source_id = ""
            status = "unmapped"
        else:
            source = str(mapping.get("source", ""))
            source_id = str(mapping.get("id", ""))
            if tvg_id in missing_native or canonical_id(name) in missing_canonical:
                status = "missing"
            elif tvg_id in fallback_native:
                status = "fallback"
            elif count == 0:
                status = "no_programmes"
            elif future == 0:
                status = "stale"
            else:
                status = "ok"

        report_rows.append(
            {
                "channel": name,
                "tvg_id": tvg_id,
                "source": source,
                "source_id": source_id,
                "programmes": count,
                "future_programmes": future,
                "status": status,
            }
        )

    with report_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "channel",
                "tvg_id",
                "source",
                "source_id",
                "programmes",
                "future_programmes",
                "status",
            ],
        )
        writer.writeheader()
        writer.writerows(report_rows)

    status_counts = Counter(str(row["status"]) for row in report_rows)
    print(
        f"[4/4] Report: {status_counts.get('ok', 0)}/{len(report_rows)} playlist ids "
        f"have current/future programmes; fallback={status_counts.get('fallback', 0)}, "
        f"stale={status_counts.get('stale', 0)}, "
        f"no_programmes={status_counts.get('no_programmes', 0)}, "
        f"unmapped={status_counts.get('unmapped', 0)}, "
        f"missing={status_counts.get('missing', 0)}."
    )
    if failed_sources:
        print(f"      Failed sources: {', '.join(sorted(failed_sources))}")
        if not output_channels:
            return 1

    for source in sorted(needed):
        kept = len(source_channels.get(source, {}))
        print(f"      {source:<10} {kept:>3}/{len(needed[source]):<3} guide channels")
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
