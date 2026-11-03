#!/usr/bin/env python3
"""
Create an integrated Indian IPTV playlist with the Jio EPG URL embedded.

The source playlist is copied channel-for-channel so names, logos, groups and
per-channel options (``#EXTVLCOPT``, ``#KODIPROP``, ...) stay exactly as the
upstream source provides them.
"""

import re
import urllib.request
from pathlib import Path

M3U_URL = "https://iptv-org.github.io/iptv/countries/in.m3u"
EPG_URL = "https://raw.githubusercontent.com/Abinanthankv/tvepgjio/main/epg.xml.gz"

OUTPUT_M3U = "in_jio.m3u"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)


def main() -> int:
    print("==================================================")
    print("     Generating Integrated Indian Jio M3U Playlist")
    print("==================================================")

    print("[1/2] Downloading iptv-org in.m3u playlist...")
    request = urllib.request.Request(M3U_URL, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request) as response:
        content = response.read().decode("utf-8", errors="ignore")

    lines = content.splitlines()

    # url-tvg is the modern key; x-tvg-url is still read by some players.
    output_lines = [f'#EXTM3U url-tvg="{EPG_URL}" x-tvg-url="{EPG_URL}"']
    channel_count = 0

    index = 0
    while index < len(lines):
        line = lines[index].strip()
        if not line.startswith("#EXTINF:"):
            index += 1
            continue

        # Copy the whole channel block: the #EXTINF line, any option lines
        # (#EXTVLCOPT / #KODIPROP), and the stream URL.  The previous version
        # dropped option lines and their stream URL entirely.
        block = [line]
        cursor = index + 1
        while cursor < len(lines):
            candidate = lines[cursor].strip()
            if not candidate:
                cursor += 1
                continue
            if candidate.startswith("#EXTINF:"):
                break
            block.append(candidate)
            cursor += 1
            if not candidate.startswith("#"):
                break

        output_lines.extend(block)
        channel_count += 1
        index = cursor

    print(f"[2/2] Writing {OUTPUT_M3U} with embedded url-tvg...")
    Path(OUTPUT_M3U).write_text("\n".join(output_lines) + "\n", encoding="utf-8")

    print(
        f"\n🎉 SUCCESS! Created {OUTPUT_M3U} with {channel_count} channels "
        "and embedded Jio EPG URL."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
