#!/usr/bin/env python3
import os
import json
import re
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

def get_stream_label(channel_name, stream_item):
    url = stream_item.get('url', '')
    desc = stream_item.get('description', '')
    q_name = stream_item.get('name', '')
    
    label_parts = []
    
    # Extract regional affiliate or station callsign from URL if present
    match = re.search(r'live/([a-z0-9\-]+)', url, re.IGNORECASE)
    if match:
        station = match.group(1).upper()
        if 'WABC' in station: label_parts.append('WABC New York')
        elif 'KABC' in station: label_parts.append('KABC Los Angeles')
        elif 'WCBS' in station: label_parts.append('WCBS New York')
        elif 'KCBS' in station or 'CBS-KCBS' in station: label_parts.append('KCBS Los Angeles')
        elif 'WNBC' in station: label_parts.append('WNBC New York')
        elif 'KNBC' in station or 'NBC-KNBC' in station: label_parts.append('KNBC Los Angeles')
        elif 'WNYW' in station: label_parts.append('WNYW New York')
        elif 'KTTV' in station or 'FOX-KTTV' in station: label_parts.append('KTTV Los Angeles')
        elif 'WPIX' in station: label_parts.append('WPIX New York')
        else: label_parts.append(station)
    elif 'uplynk' in url:
        label_parts.append('Primary Feed')
    elif 'pluto' in url:
        label_parts.append('Pluto Feed')
    elif desc and not desc.startswith('HV:'):
        label_parts.append(desc)
        
    if q_name and q_name != 'Audio':
        label_parts.append(q_name)
        
    if label_parts:
        return f"{channel_name} ({' - '.join(label_parts)})"
    return channel_name

m3u_lines = ['#EXTM3U']
stream_count = 0
seen_urls = set()

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
                q_name = s.get('name', '')
                
                # Filter out audio-only streams and duplicates
                if not url or url in seen_urls or q_name == 'Audio':
                    continue
                    
                seen_urls.add(url)
                
                title = get_stream_label(name, s)
                tvg_id = name.replace(' ', '') + '.us'
                
                m3u_lines.append(f'#EXTINF:-1 tvg-id="{tvg_id}" tvg-name="{name}" tvg-logo="{logo}" group-title="{group}",{title}')
                m3u_lines.append(url)
                stream_count += 1

print(f"[3/3] Writing cleaned {OUTPUT_FILE}...")
with open(OUTPUT_FILE, 'w', encoding='utf-8') as out:
    out.write('\n'.join(m3u_lines) + '\n')

print(f"\n🎉 SUCCESS! Generated {OUTPUT_FILE} containing {stream_count} active video streams across {len(metas)} channels.")
