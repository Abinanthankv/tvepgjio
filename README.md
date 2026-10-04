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

## ⚡ Features

* **USA TV Next to M3U Converter**: Converted 169+ US live streams (ABC, CBS, NBC, FOX, ESPN, HBO, etc.) from the Stremio `usa-tv-next` addon into a standard `#EXTM3U` playlist (`usa_tv_next.m3u`).
* **Jio EPG Adapter**: Directly maps over 580+ Indian channels from `in.m3u` including stream variants (`@SD`, `@HD`, `@1080p`, etc.).
* **Automated Updates**: Powered by **GitHub Actions** — runs every 6 hours (`cron: '0 */6 * * *'`) and updates the repository automatically.

---

## 🚀 How to Sync & Push Changes

```bash
git push origin main
```

---

## ⚖️ Legal & DMCA Disclaimer

- **Publicly Available Information**: All playlist links (`.m3u`), Electronic Program Guides (`.xml` / `.xml.gz`), channel logos, and metadata indexed by this project are parsed from freely and publicly accessible resources available on the internet.
- **No Content Hosting**: This repository does **NOT** host, store, retransmit, or broadcast any video, audio, media files, or copyrighted streams. All stream links point directly to external, unassociated third-party servers over which we have no control.
- **Fair Use & Non-Infringement**: This repository acts strictly as an automated metadata parser and indexer for educational and personal use under Fair Use guidelines.
- **DMCA Exemption Notice**: Because this repository functions exclusively as a data aggregator and does not store or distribute copyrighted media files, it is **not subject to DMCA takedown claims** regarding content hosting. If you believe an external stream link infringes your copyright, please contact the respective third-party host server or domain administrator directly.

---

## 📄 License
MIT License
