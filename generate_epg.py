#!/usr/bin/env python3
import gzip
import io
import os
import re
import urllib.request
import xml.etree.ElementTree as ET
from collections import defaultdict
from difflib import SequenceMatcher

M3U_URL = "https://iptv-org.github.io/iptv/countries/in.m3u"
JIO_EPG_URL = "https://avkb.short.gy/jioepg.xml.gz"

OUTPUT_XML = "epg.xml"
OUTPUT_GZ = "epg.xml.gz"

print("==================================================")
print("     Jio EPG Adapter for IPTV-Org in.m3u")
print("==================================================")

# 1. Download M3U
print("[1/5] Downloading M3U playlist...")
req_m3u = urllib.request.Request(M3U_URL, headers={'User-Agent': 'Mozilla/5.0'})
with urllib.request.urlopen(req_m3u) as response:
    m3u_content = response.read().decode('utf-8', errors='ignore')

def parse_m3u(content):
    channels = []
    lines = content.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith("#EXTINF:"):
            extinf = line
            tvg_id = re.search(r'tvg-id="([^"]*)"', extinf)
            tvg_name = re.search(r'tvg-name="([^"]*)"', extinf)
            tvg_logo = re.search(r'tvg-logo="([^"]*)"', extinf)
            group_title = re.search(r'group-title="([^"]*)"', extinf)
            
            parts = extinf.split(',', 1)
            title = parts[1].strip() if len(parts) > 1 else ""
            
            url = ""
            if i + 1 < len(lines) and not lines[i+1].startswith("#"):
                url = lines[i+1].strip()
                i += 1
                
            channels.append({
                'tvg_id': tvg_id.group(1) if tvg_id else "",
                'tvg_name': tvg_name.group(1) if tvg_name else "",
                'tvg_logo': tvg_logo.group(1) if tvg_logo else "",
                'group_title': group_title.group(1) if group_title else "",
                'title': title,
                'url': url
            })
        i += 1
    return channels

m3u_channels = parse_m3u(m3u_content)
print(f"      Parsed {len(m3u_channels)} channels from M3U playlist.")

# 2. Download Jio EPG
print("[2/5] Downloading Jio EPG XML.gz...")
req_epg = urllib.request.Request(JIO_EPG_URL, headers={
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
})
with urllib.request.urlopen(req_epg) as response:
    compressed_epg = response.read()

try:
    xml_bytes = gzip.decompress(compressed_epg)
except Exception:
    xml_bytes = compressed_epg

print(f"      Downloaded {len(xml_bytes)/(1024*1024):.2f} MB XML data.")

# 3. Parse Jio EPG
print("[3/5] Parsing Jio EPG XML tree...")
jio_root = ET.fromstring(xml_bytes)

jio_channels = {} # jio_id -> {'names': [...], 'element': Element}
for ch in jio_root.findall('channel'):
    ch_id = ch.attrib.get('id', '')
    disp_names = [d.text.strip() for d in ch.findall('display-name') if d.text]
    jio_channels[ch_id] = {
        'names': disp_names,
        'element': ch
    }

jio_programmes = defaultdict(list)
total_progs = 0
for prog in jio_root.findall('programme'):
    ch_id = prog.attrib.get('channel', '')
    if ch_id:
        jio_programmes[ch_id].append(prog)
        total_progs += 1

print(f"      Parsed {len(jio_channels)} Jio EPG channels with {total_progs} programmes.")

# 4. Build Matching Index
print("[4/5] Matching M3U channels to Jio EPG schedules...")

def clean_str(s):
    if not s:
        return ""
    s = re.sub(r'\([^)]*\)', '', s)
    s = re.sub(r'\[[^\]]*\]', '', s)
    s = re.sub(r'\b(hd|sd|fhd|4k|1080p|720p|576p|480p|360p)\b', '', s, flags=re.IGNORECASE)
    s = re.sub(r'[^a-zA-Z0-9]', '', s).lower()
    return s

# Index Jio EPG by cleaned name/id
jio_lookup = {}
for jio_id, data in jio_channels.items():
    # clean Jio ID without numbers if helpful
    clean_j_id = clean_str(jio_id)
    if clean_j_id:
        jio_lookup[clean_j_id] = jio_id
    for name in data['names']:
        cleaned_name = clean_str(name)
        if cleaned_name and cleaned_name not in jio_lookup:
            jio_lookup[cleaned_name] = jio_id

# Custom alias dictionary for tricky Indian channel names
MANUAL_ALIASES = {
    'andtv': 'andtv',
    'andxplorhd': 'andxplor',
    'abnandhrajoti': 'abnandhrajyothy',
    'bhakthitv': 'bhaktitv',
    'vijaysuper': 'vijaysuper',
    'zeecinemalu': 'zeecinemalu',
    'starmaa': 'starmaa',
    'starmovies': 'starmovies',
    'starworld': 'starworld',
    'starplus': 'starplus',
    'starsports1': 'starsports1',
    'starsports2': 'starsports2',
    'star Bharat': 'starbharat',
    'colorskannada': 'colorskannada',
    'colorsmarathi': 'colorsmarathi',
    'colorstamil': 'colorstamil',
    'colorsbangla': 'colorsbangla',
}

# Output XML Construction
new_root = ET.Element('tv', generator_info_name="JioEPG-Adapter-for-IPTVOrg", generator_info_url="https://github.com")

matched_m3u_count = 0
unmatched_m3u_count = 0
added_channel_ids = set()

for ch in m3u_channels:
    tvg_id = ch['tvg_id']
    tvg_name = ch['tvg_name']
    title = ch['title']
    
    # Must have a tvg-id to map in M3U
    if not tvg_id:
        tvg_id = title.replace(" ", "")
        
    base_tvg_id = tvg_id.split('@')[0] if '@' in tvg_id else tvg_id
    
    clean_base_id = clean_str(base_tvg_id.split('.')[0])
    clean_title = clean_str(title)
    clean_name = clean_str(tvg_name)
    
    matched_jio_id = None
    
    # Check Manual Aliases
    if clean_title in MANUAL_ALIASES and MANUAL_ALIASES[clean_title] in jio_lookup:
        matched_jio_id = jio_lookup[MANUAL_ALIASES[clean_title]]
    elif clean_base_id in MANUAL_ALIASES and MANUAL_ALIASES[clean_base_id] in jio_lookup:
        matched_jio_id = jio_lookup[MANUAL_ALIASES[clean_base_id]]
    # Match Cleaned ID / Title
    elif clean_base_id in jio_lookup:
        matched_jio_id = jio_lookup[clean_base_id]
    elif clean_title in jio_lookup:
        matched_jio_id = jio_lookup[clean_title]
    elif clean_name in jio_lookup:
        matched_jio_id = jio_lookup[clean_name]
    else:
        # Fuzzy Match fallback
        best_score = 0
        best_j_id = None
        if len(clean_title) > 3:
            for k, j_id in jio_lookup.items():
                if len(k) > 3:
                    ratio = SequenceMatcher(None, clean_title, k).ratio()
                    if ratio > 0.88 and ratio > best_score:
                        best_score = ratio
                        best_j_id = j_id
        if best_j_id:
            matched_jio_id = best_j_id

    if matched_jio_id:
        matched_m3u_count += 1
        
        # Add channel node if not already added for this tvg_id
        if tvg_id not in added_channel_ids:
            ch_elem = ET.SubElement(new_root, 'channel', id=tvg_id)
            disp_elem = ET.SubElement(ch_elem, 'display-name')
            disp_elem.text = title
            if ch['tvg_logo']:
                ET.SubElement(ch_elem, 'icon', src=ch['tvg_logo'])
            added_channel_ids.add(tvg_id)
            
        # Copy programmes mapped to this tvg_id
        for prog in jio_programmes[matched_jio_id]:
            # Create a copy of programme element with channel attribute set to tvg_id
            prog_copy = ET.SubElement(new_root, 'programme', 
                                      start=prog.attrib.get('start', ''),
                                      stop=prog.attrib.get('stop', ''),
                                      channel=tvg_id)
            for child in prog:
                prog_copy.append(child)
    else:
        unmatched_m3u_count += 1

print(f"      Matched M3U Channels: {matched_m3u_count} / {len(m3u_channels)} ({matched_m3u_count/len(m3u_channels)*100:.1f}%)")
print(f"      Unmatched Channels:   {unmatched_m3u_count}")

# 5. Write Output XML & GZ
print("[5/5] Writing output files...")
tree = ET.ElementTree(new_root)

# Write uncompressed XML
tree.write(OUTPUT_XML, encoding='utf-8', xml_declaration=True)
xml_file_size = os.path.getsize(OUTPUT_XML) / (1024 * 1024)
print(f"      Generated {OUTPUT_XML} ({xml_file_size:.2f} MB)")

# Compress to .xml.gz
with open(OUTPUT_XML, 'rb') as f_in:
    with gzip.open(OUTPUT_GZ, 'wb') as f_out:
        f_out.writelines(f_in)

gz_file_size = os.path.getsize(OUTPUT_GZ) / (1024 * 1024)
print(f"      Compressed {OUTPUT_GZ} ({gz_file_size:.2f} MB)")

print("\n🎉 Success! EPG adapted and compressed successfully.")
