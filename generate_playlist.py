#!/usr/bin/env python3
import os
import re
import urllib.request

M3U_URL = "https://iptv-org.github.io/iptv/countries/in.m3u"
EPG_URL = "https://raw.githubusercontent.com/Abinanthankv/tvepgjio/main/epg.xml.gz"

OUTPUT_M3U = "in_jio.m3u"

print("==================================================")
print("     Generating Integrated Indian Jio M3U Playlist")
print("==================================================")

print("[1/2] Downloading iptv-org in.m3u playlist...")
req = urllib.request.Request(M3U_URL, headers={'User-Agent': 'Mozilla/5.0'})
with urllib.request.urlopen(req) as resp:
    content = resp.read().decode('utf-8', errors='ignore')

lines = content.splitlines()

m3u_lines = [f'#EXTM3U url-tvg="{EPG_URL}"']
channel_count = 0

i = 0
while i < len(lines):
    line = lines[i].strip()
    if line.startswith("#EXTINF:"):
        extinf = line
        
        # Next line is stream URL
        stream_url = ""
        if i + 1 < len(lines) and not lines[i+1].startswith("#"):
            stream_url = lines[i+1].strip()
            i += 1
            
        m3u_lines.append(extinf)
        m3u_lines.append(stream_url)
        channel_count += 1
    i += 1

print(f"[2/2] Writing {OUTPUT_M3U} with embedded url-tvg...")
with open(OUTPUT_M3U, 'w', encoding='utf-8') as out:
    out.write('\n'.join(m3u_lines) + '\n')

print(f"\n🎉 SUCCESS! Created {OUTPUT_M3U} with {channel_count} channels and embedded Jio EPG URL.")
