#!/usr/bin/env python3
import json
import urllib.request
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

CATALOG_URL = "https://raw.githubusercontent.com/yowmamasita/usa-tv-next/main/catalog/tv/all.json"
BASE_STREAM_URL = "https://raw.githubusercontent.com/yowmamasita/usa-tv-next/main/stream/tv/"

OUTPUT_M3U = "usa_tv_next.m3u"

print("1. Downloading USA TV Next Catalog...")
req = urllib.request.Request(CATALOG_URL, headers={'User-Agent': 'Mozilla/5.0'})
with urllib.request.urlopen(req) as resp:
    catalog = json.loads(resp.read().decode('utf-8'))

metas = catalog.get('metas', [])
print(f"   Found {len(metas)} channels in catalog.")

def fetch_stream(item):
    ch_id = item.get('id', '')
    ch_name = item.get('name', 'Untitled')
    poster = item.get('poster', '')
    logo = item.get('logo', '') or poster
    genres = item.get('genres', [])
    group = genres[0] if genres else "General"
    
    if not ch_id:
        return []
        
    stream_url = f"{BASE_STREAM_URL}{ch_id}.json"
    entries = []
    try:
        s_req = urllib.request.Request(stream_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(s_req) as s_resp:
            s_data = json.loads(s_resp.read().decode('utf-8'))
            streams = s_data.get('streams', [])
            
            for s in streams:
                url = s.get('url', '')
                if not url:
                    continue
                    
                quality_name = s.get('name', 'HD')
                stream_title = f"{ch_name} ({quality_name})" if len(streams) > 1 else ch_name
                clean_tvgid = ch_name.replace(" ", "") + ".us"
                
                extinf = f'#EXTINF:-1 tvg-id="{clean_tvgid}" tvg-name="{ch_name}" tvg-logo="{logo}" group-title="{group}",{stream_title}'
                entries.append(f"{extinf}\n{url}")
    except Exception as e:
        pass
    return entries

print("2. Concurrently fetching stream data for all channels...")
all_entries = []
with ThreadPoolExecutor(max_workers=20) as executor:
    futures = [executor.submit(fetch_stream, item) for item in metas]
    for future in as_completed(futures):
        res = future.result()
        if res:
            all_entries.extend(res)

print(f"3. Generating M3U Playlist ({len(all_entries)} total streams generated)...")
m3u_content = "#EXTM3U\n" + "\n".join(all_entries) + "\n"

with open(OUTPUT_M3U, "w", encoding="utf-8") as f:
    f.write(m3u_content)

print(f"   Saved to {OUTPUT_M3U} ({os.path.getsize(OUTPUT_M3U)/1024:.2f} KB)")
