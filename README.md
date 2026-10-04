# 📺 Adapted Jio EPG for IPTV-Org Indian Channels (`in.m3u`)

Automated Electronic Program Guide (EPG) generator that fetches full TV schedules from **Jio TV** and maps them directly to channel `tvg-id`s used in `https://iptv-org.github.io/iptv/countries/in.m3u`.

---

## 🔗 Direct EPG URL for IPTV Players

Once you host this repository on GitHub, your direct EPG URL will be:

```text
https://raw.githubusercontent.com/<YOUR_GITHUB_USERNAME>/<YOUR_REPO_NAME>/main/epg.xml.gz
```

*(You can also use `epg.xml` if your player requires uncompressed XML).*

---

## ⚡ Features

* **High Match Rate (~70%)**: Directly maps over 580+ Indian channels from `in.m3u` including stream variants (`@SD`, `@HD`, `@1080p`, etc.).
* **Automated Updates**: Powered by **GitHub Actions** — runs every 6 hours (`cron: '0 */6 * * *'`) and updates the repository automatically.
* **Compressed File**: `epg.xml.gz` is optimized to ~1 MB for quick downloading on mobile/TV devices.
* **Compatible With**:
  - **TiviMate**
  - **OTT Navigator**
  - **IPTV Smarters Pro**
  - **Kodi Simple IPTV Client**
  - **Tivimax / Perfect Player**

---

## 🚀 How to Setup on GitHub

### 1. Initialize Git and Push to GitHub

Run the following commands in your local directory:

```bash
git init
git add .
git commit -m "Initial commit: EPG adapter and workflow"
git branch -M main
git remote add origin https://github.com/<YOUR_GITHUB_USERNAME>/<YOUR_REPO_NAME>.git
git push -u origin main
```

### 2. Enable GitHub Actions Permissions

1. Go to your repository on GitHub.
2. Click **Settings** -> **Actions** -> **General**.
3. Scroll down to **Workflow permissions**.
4. Select **Read and write permissions**.
5. Click **Save**.

That's it! GitHub Actions will now automatically update your EPG every 6 hours. You can also manually trigger an update under the **Actions** tab by selecting **Generate and Update EPG** -> **Run workflow**.

---

## 🛠️ Local Usage

If you want to run the adapter script locally:

```bash
python3 generate_epg.py
```

This will download the latest playlist and guide data, generate `epg.xml`, and compress it to `epg.xml.gz`.

---

## 📄 License
MIT License
