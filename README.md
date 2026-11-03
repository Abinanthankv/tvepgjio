# 📺 TVEPG Jio - Interactive TV Guide & Playlist Tools (`tvepgjio`)

Automated Electronic Program Guide (EPG) generator and IPTV playlist converter for **Jio TV** and **USA TV Next**.

Includes an interactive **GitHub Pages Web App** for searching channels, checking match rates, and inspecting live TV schedules.

---

## 🌐 Web App (GitHub Pages)

Access the live web app in your browser:
```text
https://Abinanthankv.github.io/tvepgjio/
```

---

## 🔗 Direct URLs for IPTV Players (TiviMate / OTT Navigator / Kodi / IPTV Smarters)

### 1. All-in-One Indian Jio M3U Playlist (With Embedded Jio EPG) ⭐ *[RECOMMENDED]*
```text
https://raw.githubusercontent.com/Abinanthankv/tvepgjio/main/in_jio.m3u
```
*(This single link embeds `#EXTM3U url-tvg="..."` so your IPTV player automatically loads streams AND the TV guide without manual setup).*

### 2. Standalone Indian Jio EPG URL
```text
https://raw.githubusercontent.com/Abinanthankv/tvepgjio/main/epg.xml.gz
```

### 3. USA TV Next Playlist (With Embedded USA EPG) ⭐
```text
https://raw.githubusercontent.com/Abinanthankv/tvepgjio/main/usa_tv_next.m3u
```
*The playlist embeds `url-tvg` / `x-tvg-url` pointing at the matching USA guide, so
channels and schedules load together.*

### 4. Standalone USA EPG URL
```text
https://raw.githubusercontent.com/Abinanthankv/tvepgjio/main/usa_epg.xml.gz
```

---

## ⚡ Features & Workflows

* **All-in-One Integrated Playlist (`in_jio.m3u`)**: Contains 840+ Indian live streams with embedded `url-tvg` pointing to your Jio EPG guide. Channel names, logos, groups and per-channel options are copied exactly from the upstream playlist.
* **Jio EPG Workflow** (`generate-epg.yml`): Maps Indian channels from `in.m3u` to Jio schedules. Runs **every 6 hours** automatically (`cron: '0 */6 * * *'`).
* **USA TV Next Workflow** (`update-usa-m3u.yml`): Converts the `usa-tv-next`
  catalog into a cleaned M3U, then builds a compact USA XMLTV guide. Runs
  **once daily** (`cron: '0 0 * * *'`) and commits
  `usa_tv_next.m3u`, `usa_epg.xml`, `usa_epg.xml.gz` and
  `usa_epg_report.csv`.
* **Cleaned USA output**: audio-only streams, dead feeds, duplicate URLs,
  UUID titles and known non-US/junk feeds (for example the Australian
  `abc-*` feeds and the `*_in_90_seconds` clips) are removed. Every remaining
  feed gets a unique `Channel (Source - Quality)` title, stable `tvg-id`, a
  `USA | <Genre>` group and a deterministic sort order. The upstream catalog
  lists 169 channels; 103 currently have usable video streams.

---

## 🎯 EPG Matching & Channel Names

The guide uses the **official Jio source channel name** for every matched
`<display-name>` (for example `Colors Cineplex Superhit`, not
`Colors Cineplex Superhits (576p)`). The playlist name is preserved as the
secondary, human-readable label in the web app so every mapping stays
auditable.

Matching is staged and deliberately conservative:

1. **Exact source ID** — direct `tvg-id` match.
2. **Exact normalised name** — case, punctuation, brackets, `HD`/`SD` and
   quality tags are ignored; `@HD`/`@SD` tvg-id tags disambiguate duplicate
   SD/HD source feeds.
3. **Curated alias** — see [`channel_aliases.json`](channel_aliases.json).
4. **Guarded fuzzy match** — only when the first word, numbers, language
   markers and distinctive words agree. Weak candidates are reported as
   `ambiguous` instead of being guessed.

`generate_epg.py` writes **`epg_match_report.csv`** with one row per playlist
channel (`status`, `method`, `score`, `source_id`, `source_name`,
`programme_count`, `candidates`). To fix a missing channel:

1. Open `epg_match_report.csv` and find the `unmatched` row.
2. Add an entry to `channel_aliases.json`:
   ```json
   {
     "aliases": {
       "Playlist Channel Name": "Official Jio Source Name"
     }
   }
   ```
3. Re-run `python generate_epg.py`. The alias is applied before fuzzy
   matching, so it is deterministic.

You can test locally without overwriting the published files:

```bash
python generate_epg.py \
  --output /tmp/epg.xml \
  --output-gz /tmp/epg.xml.gz \
  --report /tmp/epg_match_report.csv
```

### USA TV Next guide

The USA guide is built from two public XMLTV sources
(`epg.kanya.io` and `epgshare01`). `usa_epg_aliases.json` records the exact
source channel id for every playlist channel; `generate_usa_epg.py` keeps only
those channels, rewrites their ids to match the playlist, and writes:

* `usa_epg.xml` / `usa_epg.xml.gz` — compact guide used by the playlist.
* `usa_epg_report.csv` — per-channel audit (`status`, `source`, `source_id`,
  `programmes`). Channels without a confident mapping are marked `unmapped`
  rather than being guessed.

To fix or add a USA channel:

1. Find the source channel id in the guide (for example `ABC.us@East`).
2. Add it to `usa_epg_aliases.json`:
   ```json
   {
     "ABC": { "source": "kanya", "id": "ABC.us@East" }
   }
   ```
3. Re-run:
   ```bash
   python convert_stremio_to_m3u.py
   python generate_usa_epg.py
   ```

Local regeneration without touching the published guide:

```bash
python generate_usa_epg.py \
  --output /tmp/usa_epg.xml \
  --output-gz /tmp/usa_epg.xml.gz \
  --report /tmp/usa_epg_report.csv
```

---

## 🚀 How to Manually Trigger Workflows on GitHub

1. Go to your repository on GitHub: `https://github.com/Abinanthankv/tvepgjio`.
2. Click the **Actions** tab.
3. Select **Generate and Update EPG & Playlist** (Jio) or **Update USA TV Next
   M3U Playlist** (USA) ➔ Click **Run workflow**.

---

## ⚖️ Legal & DMCA Disclaimer

- **Publicly Available Information**: All playlist links (`.m3u`), Electronic Program Guides (`.xml` / `.xml.gz`), channel logos, and metadata indexed by this project are parsed from freely and publicly accessible resources available on the internet.
- **No Content Hosting**: This repository does **NOT** host, store, retransmit, or broadcast any video, audio, media files, or copyrighted streams. All stream links point directly to external, unassociated third-party servers over which we have no control.
- **Fair Use & Non-Infringement**: This repository acts strictly as an automated metadata parser and indexer for educational and personal use under Fair Use guidelines.
- **DMCA Exemption Notice**: Because this repository functions exclusively as a data aggregator and does not store or distribute copyrighted media files, it is **not subject to DMCA takedown claims** regarding content hosting. If you believe an external stream link infringes your copyright, please contact the respective third-party host server or domain administrator directly.

---

## 📄 License
MIT License
