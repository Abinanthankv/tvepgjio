# 📺 TVEPG Jio - Interactive TV Guide & EPG Browser (`tvepgjio`)

Automated Electronic Program Guide (EPG) generator that fetches full TV schedules from **Jio TV** and maps them directly to channel `tvg-id`s used in `https://iptv-org.github.io/iptv/countries/in.m3u`.

Includes an interactive **GitHub Pages Web App** for searching channels, checking match rates, and inspecting live TV schedules.

---

## 🌐 Web App (GitHub Pages)

Access the live web app in your browser:
```text
https://Abinanthankv.github.io/tvepgjio/
```

### Web App Features:
- 🔍 **Search & Filter**: Search channels by name, `tvg-id`, or program title.
- 📺 **Live TV Guide**: Displays real-time now-playing programs with live progress bars and upcoming schedules.
- 📊 **Match Analytics**: Shows total channels, EPG match rate %, and category breakdowns.
- 📁 **File Upload Support**: Drag & drop custom `.m3u` playlists and `.xml` / `.xml.gz` EPG files to inspect offline.

---

## 🔗 Direct EPG URL for IPTV Players

In **TiviMate**, **OTT Navigator**, **Kodi**, **IPTV Smarters Pro**, or **Tivimax**:

```text
https://raw.githubusercontent.com/Abinanthankv/tvepgjio/main/epg.xml.gz
```

*(You can also use `epg.xml` if your player requires uncompressed XML).*

---

## ⚡ Features

* **High Match Rate (~70%)**: Directly maps over 580+ Indian channels from `in.m3u` including stream variants (`@SD`, `@HD`, `@1080p`, etc.).
* **Automated Updates**: Powered by **GitHub Actions** — runs every 6 hours (`cron: '0 */6 * * *'`) and updates the repository automatically.
* **Compressed File**: `epg.xml.gz` is optimized to ~1 MB for quick downloading on mobile/TV devices.

---

## 🚀 How to Enable GitHub Pages

1. Push your changes to GitHub:
   ```bash
   git push origin main
   ```
2. On GitHub, go to **Settings** -> **Pages**.
3. Under **Build and deployment** -> **Source**, choose **Deploy from a branch**.
4. Set **Branch** to `main` and folder to `/ (root)`.
5. Click **Save**.

Your web page will be live at `https://Abinanthankv.github.io/tvepgjio/` within 1–2 minutes!

---

## 📄 License
MIT License
