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

### 3. USA TV Next Converted M3U Playlist
```text
https://raw.githubusercontent.com/Abinanthankv/tvepgjio/main/usa_tv_next.m3u
```

---

## ⚡ Features & Workflows

* **All-in-One Integrated Playlist (`in_jio.m3u`)**: Contains 835+ Indian live streams with embedded `url-tvg` pointing to your Jio EPG guide.
* **Jio EPG Workflow** (`generate-epg.yml`): Maps 580+ Indian channels from `in.m3u` to Jio schedules. Runs **every 6 hours** automatically (`cron: '0 */6 * * *'`).
* **USA TV Next M3U Workflow** (`update-usa-m3u.yml`): Converts 169+ US live streams from `usa-tv-next` into `#EXTM3U`. Runs **once daily** (`cron: '0 0 * * *'`).

---

## 🚀 How to Manually Trigger Workflows on GitHub

1. Go to your repository on GitHub: `https://github.com/Abinanthankv/tvepgjio`.
2. Click the **Actions** tab.
3. Select **Generate and Update EPG & Playlist** ➔ Click **Run workflow**.

---

## ⚖️ Legal & DMCA Disclaimer

- **Publicly Available Information**: All playlist links (`.m3u`), Electronic Program Guides (`.xml` / `.xml.gz`), channel logos, and metadata indexed by this project are parsed from freely and publicly accessible resources available on the internet.
- **No Content Hosting**: This repository does **NOT** host, store, retransmit, or broadcast any video, audio, media files, or copyrighted streams. All stream links point directly to external, unassociated third-party servers over which we have no control.
- **Fair Use & Non-Infringement**: This repository acts strictly as an automated metadata parser and indexer for educational and personal use under Fair Use guidelines.
- **DMCA Exemption Notice**: Because this repository functions exclusively as a data aggregator and does not store or distribute copyrighted media files, it is **not subject to DMCA takedown claims** regarding content hosting. If you believe an external stream link infringes your copyright, please contact the respective third-party host server or domain administrator directly.

---

## 📄 License
MIT License
