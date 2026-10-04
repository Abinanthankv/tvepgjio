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

## 📄 License
MIT License
