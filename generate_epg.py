#!/usr/bin/env python3
"""
Build a Jio-based XMLTV guide for an IPTV-Org style M3U playlist.

Pipeline
--------
1. Download (or read) the playlist and the official Jio EPG.
2. Match each playlist channel to a Jio source channel with
   :mod:`epg_matcher` (exact name -> curated alias -> guarded fuzzy).
3. Emit XMLTV whose ``channel@id`` equals the playlist ``tvg-id`` so any
   player can pair the two files, and whose ``<display-name>`` is the
   *official Jio source name*.
4. Write ``epg_match_report.csv`` so the long tail can be reviewed and
   added to ``channel_aliases.json``.

Usage examples
--------------
    python generate_epg.py
    python generate_epg.py --m3u in.m3u --jio-epg source.xml.gz \
        --output /tmp/epg.xml --output-gz /tmp/epg.xml.gz \
        --report /tmp/report.csv
"""

from __future__ import annotations

import argparse
import copy
import csv
import gzip
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from epg_matcher import ChannelMatcher, SourceChannel, load_aliases

DEFAULT_M3U_URL = "https://iptv-org.github.io/iptv/countries/in.m3u"
DEFAULT_JIO_EPG_URL = "https://avkb.short.gy/jioepg.xml.gz"
DEFAULT_OUTPUT_XML = "epg.xml"
DEFAULT_OUTPUT_GZ = "epg.xml.gz"
DEFAULT_REPORT = "epg_match_report.csv"
DEFAULT_ALIASES = "channel_aliases.json"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)


# --------------------------------------------------------------------------- io
def read_source(location: str) -> bytes:
    """Read a local path or an HTTP(S) URL."""
    if re.match(r"^https?://", location, re.I):
        request = urllib.request.Request(location, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(request) as response:
            return response.read()
    return Path(location).read_bytes()


def maybe_gunzip(data: bytes) -> bytes:
    if data[:2] == b"\x1f\x8b":
        return gzip.decompress(data)
    return data


# ------------------------------------------------------------------------ m3u
def split_extinf_title(line: str) -> str:
    """Return the display title after the last comma that is outside quotes.

    iptv-org sometimes embeds a ``http-user-agent`` attribute containing
    commas; a naive ``split(',', 1)`` truncates those titles.
    """
    in_quotes = False
    cut = -1
    for index, char in enumerate(line):
        if char == '"':
            in_quotes = not in_quotes
        elif char == "," and not in_quotes:
            cut = index
    return line[cut + 1:].strip() if cut != -1 else ""


def attr(extinf: str, name: str) -> str:
    match = re.search(rf'{re.escape(name)}="([^"]*)"', extinf)
    return match.group(1) if match else ""


def parse_m3u(content: str) -> List[dict]:
    channels: List[dict] = []
    lines = content.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index].strip()
        if not line.startswith("#EXTINF:"):
            index += 1
            continue

        stream_url = ""
        if index + 1 < len(lines) and not lines[index + 1].strip().startswith("#"):
            stream_url = lines[index + 1].strip()
            index += 1

        channels.append(
            {
                "tvg_id": attr(line, "tvg-id"),
                "tvg_name": attr(line, "tvg-name"),
                "tvg_logo": attr(line, "tvg-logo"),
                "group_title": attr(line, "group-title") or "Uncategorized",
                "title": split_extinf_title(line) or attr(line, "tvg-name"),
                "url": stream_url,
            }
        )
        index += 1
    return channels


# ----------------------------------------------------------------------- xmltv
def parse_jio_epg(xml_bytes: bytes) -> Tuple[List[SourceChannel], Dict[str, List[ET.Element]], Dict[str, ET.Element]]:
    root = ET.fromstring(xml_bytes)
    sources: List[SourceChannel] = []
    source_elements: Dict[str, ET.Element] = {}
    programmes: Dict[str, List[ET.Element]] = defaultdict(list)

    for channel in root.findall("channel"):
        source_id = channel.attrib.get("id", "")
        if not source_id:
            continue
        names = [
            node.text.strip()
            for node in channel.findall("display-name")
            if node.text and node.text.strip()
        ]
        sources.append(SourceChannel(source_id, names))
        source_elements[source_id] = channel

    for programme in root.findall("programme"):
        channel_id = programme.attrib.get("channel", "")
        if channel_id:
            programmes[channel_id].append(programme)

    return sources, programmes, source_elements


def effective_tvg_id(channel: dict) -> str:
    tvg_id = channel["tvg_id"].strip()
    if tvg_id:
        return tvg_id
    return re.sub(r"\s+", "", channel["title"])


# ---------------------------------------------------------------------- output
def build_xmltv(
    channels: List[dict],
    matcher: ChannelMatcher,
    source_names: Dict[str, str],
    source_elements: Dict[str, ET.Element],
    programmes: Dict[str, List[ET.Element]],
) -> Tuple[ET.ElementTree, List[dict]]:
    root = ET.Element(
        "tv",
        {
            "generator-info-name": "JioEPG-Adapter-for-IPTVOrg",
            "generator-info-url": "https://github.com/Abinanthankv/tvepgjio",
        },
    )

    report_rows: List[dict] = []
    emitted_ids: set[str] = set()
    matched = 0

    for channel in channels:
        tvg_id = effective_tvg_id(channel)
        result = matcher.match(
            tvg_id=channel["tvg_id"],
            title=channel["title"],
            tvg_name=channel["tvg_name"],
        )
        source_id = result.source_id
        source_name = source_names.get(source_id, "") if source_id else ""
        programme_count = len(programmes.get(source_id, [])) if source_id else 0

        report_rows.append(
            {
                "tvg_id": tvg_id,
                "playlist_name": channel["title"],
                "tvg_name": channel["tvg_name"],
                "status": result.status,
                "method": result.method,
                "score": f"{result.score:.2f}",
                "source_id": source_id or "",
                "source_name": source_name,
                "programme_count": programme_count,
                "candidates": "|".join(result.candidates),
                "note": result.note,
            }
        )

        if not source_id or programme_count == 0:
            continue
        # A playlist may list the same tvg-id twice; emit the guide once.
        if tvg_id in emitted_ids:
            continue
        emitted_ids.add(tvg_id)
        matched += 1

        channel_element = ET.SubElement(root, "channel", id=tvg_id)
        display_name = ET.SubElement(channel_element, "display-name")
        display_name.text = source_name or source_id  # official source name

        logo = channel["tvg_logo"]
        if not logo:
            source_icon = source_elements[source_id].find("icon")
            if source_icon is not None:
                logo = source_icon.attrib.get("src", "")
        if logo:
            ET.SubElement(channel_element, "icon", src=logo)

        for programme in programmes[source_id]:
            clone = copy.deepcopy(programme)
            clone.set("channel", tvg_id)
            root.append(clone)

    return ET.ElementTree(root), report_rows


def write_report(path: Path, rows: Iterable[dict]) -> None:
    fieldnames = [
        "tvg_id",
        "playlist_name",
        "tvg_name",
        "status",
        "method",
        "score",
        "source_id",
        "source_name",
        "programme_count",
        "candidates",
        "note",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


# ------------------------------------------------------------------------ main
def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--m3u", default=DEFAULT_M3U_URL, help="M3U path or URL")
    parser.add_argument("--jio-epg", default=DEFAULT_JIO_EPG_URL, help="Jio EPG path or URL")
    parser.add_argument("--aliases", default=DEFAULT_ALIASES, help="Alias JSON path")
    parser.add_argument("--output", default=DEFAULT_OUTPUT_XML, help="Output XMLTV path")
    parser.add_argument("--output-gz", default=DEFAULT_OUTPUT_GZ, help="Output gzip path")
    parser.add_argument("--report", default=DEFAULT_REPORT, help="Match report CSV path")
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)

    print("==================================================")
    print("     Jio EPG Adapter for IPTV-Org in.m3u")
    print("==================================================")

    print(f"[1/5] Reading playlist: {args.m3u}")
    m3u_content = read_source(args.m3u).decode("utf-8", errors="ignore")
    m3u_channels = parse_m3u(m3u_content)
    print(f"      Parsed {len(m3u_channels)} playlist channels.")

    print(f"[2/5] Reading Jio EPG: {args.jio_epg}")
    xml_bytes = maybe_gunzip(read_source(args.jio_epg))
    print(f"      {len(xml_bytes) / (1024 * 1024):.2f} MB of XML.")

    print("[3/5] Indexing Jio source channels...")
    sources, programmes, source_elements = parse_jio_epg(xml_bytes)
    source_names = {source.source_id: source.primary_name for source in sources}
    alias_path = Path(args.aliases)
    aliases = load_aliases(alias_path)
    matcher = ChannelMatcher(sources, aliases)
    print(
        f"      {len(sources)} source channels, "
        f"{sum(len(p) for p in programmes.values())} programmes, "
        f"{len(aliases)} curated aliases."
    )

    print("[4/5] Matching and building XMLTV...")
    tree, report_rows = build_xmltv(
        m3u_channels, matcher, source_names, source_elements, programmes
    )

    output_path = Path(args.output)
    tree.write(output_path, encoding="utf-8", xml_declaration=True)
    print(f"      Wrote {output_path} ({output_path.stat().st_size / (1024 * 1024):.2f} MB)")

    output_gz = Path(args.output_gz)
    with output_path.open("rb") as source_handle, gzip.open(output_gz, "wb") as gzip_handle:
        gzip_handle.writelines(source_handle)
    print(f"      Wrote {output_gz} ({output_gz.stat().st_size / (1024 * 1024):.2f} MB)")

    report_path = Path(args.report)
    write_report(report_path, report_rows)
    print(f"      Wrote {report_path}")

    print("[5/5] Summary")
    status_counts: Dict[str, int] = defaultdict(int)
    for row in report_rows:
        status_counts[row["status"]] += 1
    total = len(report_rows)
    matched = status_counts.get("exact", 0) + status_counts.get("alias", 0) + status_counts.get("fuzzy", 0)
    for status in ("exact", "alias", "fuzzy", "ambiguous", "unmatched"):
        print(f"      {status:10} {status_counts.get(status, 0):4}")
    if total:
        print(f"      coverage   {matched}/{total} ({matched / total * 100:.1f}%)")
    print("\n🎉 Success! EPG adapted and compressed successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
