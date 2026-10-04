#!/usr/bin/env python3
import os
import json
import subprocess

TMP_DIR = '/tmp/usa-tv-next'
OUTPUT_FILE = 'usa_tv_next.m3u'

print("==================================================")
print("     USA TV Next Stremio Addon to M3U Converter")
print("==================================================")

if not os.path.exists(TMP_DIR):
    print("[1/3] Cloning yowmamasita/usa-tv-next repository...")
    subprocess.run(['git', 'clone', '--depth', '1', 'https://github.com/yowmamasita/usa-tv-next', TMP_DIR], check=True)
else:
    print("[1/3] Updating local yowmamasita/usa-tv-next repository...")
    subprocess.run(['git', '-C', TMP_DIR, 'pull'], check=False)

catalog_path = os.path.join(TMP_DIR, 'catalog/tv/all.json')
with open(catalog_path, 'r', encoding='utf-8') as f:
    catalog = json.load(f)

metas = catalog.get('metas', [])
print(f"[2/3] Parsed {len(metas)} catalog items.")

m3u_lines = ['#EXTM3U']
stream_count = 0

for m in metas:
    ch_id = m.get('id')
    name = m.get('name', 'Channel')
    poster = m.get('poster', '')
    logo = m.get('logo', '') or poster
    genres = m.get('genres', [])
    group = genres[0] if genres else 'General'
    
    stream_file = os.path.join(TMP_DIR, f'stream/tv/{ch_id}.json')
    if os.path.exists(stream_file):
        with open(stream_file, 'r', encoding='utf-8') as sf:
            s_data = json.load(sf)
            streams = s_data.get('streams', [])
            for s in streams:
                url = s.get('url')
                if url:
                    q_name = s.get('name', 'HD')
                    title = f"{name} ({q_name})" if len(streams) > 1 else name
                    tvg_id = name.replace(' ', '') + '.us'
                    m3u_lines.append(f'#EXTINF:-1 tvg-id="{tvg_id}" tvg-name="{name}" tvg-logo="{logo}" group-title="{group}",{title}')
                    m3u_lines.append(url)
                    stream_count += 1

print(f"[3/3] Writing {OUTPUT_FILE}...")
with open(OUTPUT_FILE, 'w', encoding='utf-8') as out:
    out.write('\n'.join(m3u_lines) + '\n')

print(f"\n🎉 SUCCESS! Generated {OUTPUT_FILE} containing {stream_count} streams across {len(metas)} channels.")
