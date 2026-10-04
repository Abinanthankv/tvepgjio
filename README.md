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

### 1. Indian Jio EPG URL
```text
https://raw.githubusercontent.com/Abinanthankv/tvepgjio/main/epg.xml.gz
```

### 2. USA TV Next Converted M3U Playlist
```text
https://raw.githubusercontent.com/Abinanthankv/tvepgjio/main/usa_tv_next.m3u
```

---

## ⚡ Features & Workflows

* **USA TV Next M3U Workflow** (`update-usa-m3u.yml`):
  - Converts 169+ US live streams (ABC, CBS, NBC, FOX, ESPN, HBO, etc.) from the Stremio `usa-tv-next` addon into `#EXTM3U`.
  - Runs **once daily** automatically (`cron: '0 0 * * *'`) or **manually on demand** via GitHub Actions.
* **Jio EPG Workflow** (`generate-epg.yml`):
  - Maps 580+ Indian channels from `in.m3u` including stream variants (`@SD`, `@HD`, `@1080p`, etc.) to Jio schedules.
  - Runs **every 6 hours** automatically (`cron: '0 */6 * * *'`) or **manually on demand**.

---

## 🚀 How to Manually Trigger Workflows on GitHub

1. Go to your repository on GitHub: `https://github.com/Abinanthankv/tvepgjio`.
2. Click the **Actions** tab.
3. Select either:
   - **Update USA TV Next M3U Playlist** ➔ Click **Run workflow**.
   - **Generate and Update EPG** ➔ Click **Run workflow**.

---

## ⚖️ Legal & DMCA Disclaimer

- **Publicly Available Information**: All playlist links (`.m3u`), Electronic Program Guides (`.xml` / `.xml.gz`), channel logos, and metadata indexed by this project are parsed from freely and publicly accessible resources available on the internet.
- **No Content Hosting**: This repository does **NOT** host, store, retransmit, or broadcast any video, audio, media files, or copyrighted streams. All stream links point directly to external, unassociated third-party servers over which we have no control.
- **Fair Use & Non-Infringement**: This repository acts strictly as an automated metadata parser and indexer for educational and personal use under Fair Use guidelines.
- **DMCA Exemption Notice**: Because this repository functions exclusively as a data aggregator and does not store or distribute copyrighted media files, it is **not subject to DMCA takedown claims** regarding content hosting. If you believe an external stream link infringes your copyright, please contact the respective third-party host server or domain administrator directly.

---

## 📄 License
MIT License
