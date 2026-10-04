/* ==========================================================================
   TVEPG Jio - App JavaScript Logic
   ========================================================================== */

let m3uChannels = [];
let epgChannels = new Map(); // id -> names array
let epgProgrammes = new Map(); // id -> programme objects array
let matchedChannels = [];
let filteredChannels = [];

let currentTab = 'url';
let currentViewMode = 'grid';

// Initialize events when DOM loaded
document.addEventListener('DOMContentLoaded', () => {
  setupFileInputs();
  setupFilterEvents();
});

// Tab Switcher
function switchTab(tab) {
  currentTab = tab;
  document.getElementById('tabUrlBtn').classList.toggle('active', tab === 'url');
  document.getElementById('tabFileBtn').classList.toggle('active', tab === 'file');
  document.getElementById('urlInputsSection').style.display = tab === 'url' ? 'block' : 'none';
  document.getElementById('fileInputsSection').style.display = tab === 'file' ? 'block' : 'none';
}

function setupFileInputs() {
  const m3uInput = document.getElementById('m3uFileInput');
  const epgInput = document.getElementById('epgFileInput');

  m3uInput.addEventListener('change', (e) => {
    if (e.target.files.length > 0) {
      document.getElementById('m3uFileName').innerText = e.target.files[0].name;
    }
  });

  epgInput.addEventListener('change', (e) => {
    if (e.target.files.length > 0) {
      document.getElementById('epgFileName').innerText = e.target.files[0].name;
    }
  });
}

function resetDefaults() {
  document.getElementById('m3uUrlInput').value = "https://iptv-org.github.io/iptv/countries/in.m3u";
  document.getElementById('epgUrlInput').value = "https://raw.githubusercontent.com/Abinanthankv/tvepgjio/main/epg.xml.gz";
  document.getElementById('m3uFileInput').value = "";
  document.getElementById('epgFileInput').value = "";
  document.getElementById('m3uFileName').innerText = "Choose or Drag & Drop M3U Playlist";
  document.getElementById('epgFileName').innerText = "Choose or Drag & Drop EPG File";
  document.getElementById('searchInput').value = "";
  document.getElementById('groupFilter').value = "ALL";
  document.getElementById('statusFilter').value = "ALL";
}

// Main Loader Function
async function loadData() {
  const mainContainer = document.getElementById('mainContainer');
  mainContainer.innerHTML = `
    <div class="loading-overlay">
      <div class="spinner"></div>
      <h2>Fetching and Processing Data...</h2>
      <p style="color: var(--text-secondary)">Downloading M3U playlist & Jio EPG XML (decompressing GZip)...</p>
    </div>
  `;

  try {
    let m3uText = "";
    let epgXmlText = "";

    if (currentTab === 'url') {
      const m3uUrl = document.getElementById('m3uUrlInput').value.trim();
      const epgUrl = document.getElementById('epgUrlInput').value.trim();

      if (!m3uUrl || !epgUrl) {
        alert("Please enter both M3U Playlist URL and EPG URL.");
        return;
      }

      console.log("Fetching M3U from URL:", m3uUrl);
      const m3uRes = await fetch(m3uUrl);
      if (!m3uRes.ok) throw new Error(`Failed to fetch M3U playlist: ${m3uRes.statusText}`);
      m3uText = await m3uRes.text();

      console.log("Fetching EPG from URL:", epgUrl);
      const epgRes = await fetch(epgUrl);
      if (!epgRes.ok) throw new Error(`Failed to fetch EPG file: ${epgRes.statusText}`);

      const epgBuffer = await epgRes.arrayBuffer();
      epgXmlText = decompressIfNeeded(epgBuffer);
    } else {
      // File upload mode
      const m3uFile = document.getElementById('m3uFileInput').files[0];
      const epgFile = document.getElementById('epgFileInput').files[0];

      if (!m3uFile || !epgFile) {
        alert("Please select both a local M3U file and an EPG XML / XML.GZ file.");
        return;
      }

      m3uText = await m3uFile.text();
      const epgBuffer = await epgFile.arrayBuffer();
      epgXmlText = decompressIfNeeded(epgBuffer);
    }

    // Step 1: Parse M3U
    m3uChannels = parseM3U(m3uText);
    console.log(`Parsed ${m3uChannels.length} M3U channels.`);

    // Step 2: Parse EPG XML
    parseEPG(epgXmlText);
    console.log(`Parsed ${epgChannels.size} EPG channels and ${epgProgrammes.size} schedule queues.`);

    // Step 3: Perform Matching
    performMatching();

    // Step 4: Render UI
    renderStats();
    populateCategoryDropdown();
    applyFilters();

  } catch (err) {
    console.error("Error loading TV guide:", err);
    mainContainer.innerHTML = `
      <div class="empty-state">
        <i class="fa-solid fa-triangle-exclamation" style="color: var(--danger-color)"></i>
        <h2>Failed to Load TV Guide</h2>
        <p style="color: var(--text-primary); margin-top: 0.5rem;">${err.message}</p>
        <p style="font-size: 0.85rem; color: var(--text-muted); margin-top: 0.5rem;">
          If using URL mode, please ensure the URL supports CORS or try downloading the file and uploading it using the <strong>Local Files</strong> tab.
        </p>
      </div>
    `;
  }
}

// Decompress GZip array buffer if needed
function decompressIfNeeded(arrayBuffer) {
  const bytes = new Uint8Array(arrayBuffer);
  // Check GZip magic bytes (0x1f, 0x8b)
  if (bytes[0] === 0x1f && bytes[1] === 0x8b) {
    console.log("Decompressing GZip data using fflate...");
    try {
      const decompressed = fflate.decompressSync(bytes);
      return new TextDecoder("utf-8").decode(decompressed);
    } catch (e) {
      console.warn("fflate error, trying standard decoder:", e);
    }
  }
  return new TextDecoder("utf-8").decode(bytes);
}

// M3U Playlist Parser
function parseM3U(content) {
  const channels = [];
  const lines = content.split('\n');
  let i = 0;

  while (i < lines.length) {
    let line = lines[i].trim();
    if (line.startsWith('#EXTINF:')) {
      const extinf = line;
      
      const tvgIdMatch = extinf.match(/tvg-id="([^"]*)"/);
      const tvgNameMatch = extinf.match(/tvg-name="([^"]*)"/);
      const tvgLogoMatch = extinf.match(/tvg-logo="([^"]*)"/);
      const groupMatch = extinf.match(/group-title="([^"]*)"/);

      const commaIdx = extinf.lastIndexOf(',');
      const title = commaIdx !== -1 ? extinf.substring(commaIdx + 1).trim() : "";

      let streamUrl = "";
      if (i + 1 < lines.length && !lines[i + 1].trim().startsWith('#')) {
        streamUrl = lines[i + 1].trim();
        i++;
      }

      channels.append = undefined; // safety
      channels.push({
        tvg_id: tvgIdMatch ? tvgIdMatch[1] : "",
        tvg_name: tvgNameMatch ? tvgNameMatch[1] : "",
        tvg_logo: tvgLogoMatch ? tvgLogoMatch[1] : "",
        group_title: groupMatch ? groupMatch[1] : "Uncategorized",
        title: title || "Untitled Channel",
        url: streamUrl
      });
    }
    i++;
  }
  return channels;
}

// EPG XMLTV Parser
function parseEPG(xmlText) {
  epgChannels.clear();
  epgProgrammes.clear();

  const parser = new DOMParser();
  const xmlDoc = parser.parseFromString(xmlText, "text/xml");

  const channelNodes = xmlDoc.getElementsByTagName("channel");
  for (let ch of channelNodes) {
    const id = ch.getAttribute("id") || "";
    const nameNodes = ch.getElementsByTagName("display-name");
    const names = [];
    for (let n of nameNodes) {
      if (n.textContent) names.push(n.textContent.trim());
    }
    if (id) epgChannels.set(id, names);
  }

  const progNodes = xmlDoc.getElementsByTagName("programme");
  const now = new Date();

  for (let prog of progNodes) {
    const chId = prog.getAttribute("channel") || "";
    const startStr = prog.getAttribute("start") || "";
    const stopStr = prog.getAttribute("stop") || "";

    const titleNode = prog.getElementsByTagName("title")[0];
    const descNode = prog.getElementsByTagName("desc")[0];
    const categoryNode = prog.getElementsByTagName("category")[0];

    const title = titleNode ? titleNode.textContent.trim() : "No Title";
    const desc = descNode ? descNode.textContent.trim() : "";
    const category = categoryNode ? categoryNode.textContent.trim() : "";

    const startDate = parseXMLTVDate(startStr);
    const stopDate = parseXMLTVDate(stopStr);

    if (chId) {
      if (!epgProgrammes.has(chId)) {
        epgProgrammes.set(chId, []);
      }
      epgProgrammes.get(chId).push({
        start: startDate,
        stop: stopDate,
        startStr,
        stopStr,
        title,
        desc,
        category
      });
    }
  }

  // Sort programmes chronologically for each channel
  for (let [chId, progs] of epgProgrammes.entries()) {
    progs.sort((a, b) => a.start - b.start);
  }
}

// Parse XMLTV Date String Format: YYYYMMDDHHMMSS +0000 or YYYYMMDDHHMMSS
function parseXMLTVDate(dStr) {
  if (!dStr || dStr.length < 14) return new Date();
  const year = parseInt(dStr.substr(0, 4));
  const month = parseInt(dStr.substr(4, 2)) - 1;
  const day = parseInt(dStr.substr(6, 2));
  const hour = parseInt(dStr.substr(8, 2));
  const minute = parseInt(dStr.substr(10, 2));
  const second = parseInt(dStr.substr(12, 2));

  return new Date(Date.UTC(year, month, day, hour, minute, second));
}

// Normalize strings for matching
function cleanStr(s) {
  if (!s) return "";
  s = s.replace(/\([^)]*\)/g, '');
  s = s.replace(/\[[^\]]*\]/g, '');
  s = s.replace(/\b(hd|sd|fhd|4k|1080p|720p|576p|480p|360p)\b/gi, '');
  return s.replace(/[^a-zA-Z0-9]/g, '').toLowerCase();
}

// Perform Channel Matching
function performMatching() {
  matchedChannels = [];

  // Build lookup index for EPG channels
  const epgLookup = new Map();
  for (let [id, names] of epgChannels.entries()) {
    const cleanId = cleanStr(id.split('.')[0]);
    if (cleanId) epgLookup.set(cleanId, id);
    for (let name of names) {
      const cleanName = cleanStr(name);
      if (cleanName && !epgLookup.has(cleanName)) {
        epgLookup.set(cleanName, id);
      }
    }
  }

  const now = new Date();

  for (let ch of m3uChannels) {
    const tvgId = ch.tvg_id;
    const baseId = tvgId ? tvgId.split('@')[0] : "";
    const cleanBaseId = cleanStr(baseId.split('.')[0]);
    const cleanTitle = cleanStr(ch.title);
    const cleanName = cleanStr(ch.tvg_name);

    let matchedEpgId = null;

    if (tvgId && epgChannels.has(tvgId)) {
      matchedEpgId = tvgId;
    } else if (baseId && epgChannels.has(baseId)) {
      matchedEpgId = baseId;
    } else if (cleanBaseId && epgLookup.has(cleanBaseId)) {
      matchedEpgId = epgLookup.get(cleanBaseId);
    } else if (cleanTitle && epgLookup.has(cleanTitle)) {
      matchedEpgId = epgLookup.get(cleanTitle);
    } else if (cleanName && epgLookup.has(cleanName)) {
      matchedEpgId = epgLookup.get(cleanName);
    }

    const progs = matchedEpgId ? (epgProgrammes.get(matchedEpgId) || []) : [];
    
    // Find current live program and upcoming
    let currentProg = null;
    let upcomingProgs = [];

    for (let p of progs) {
      if (now >= p.start && now <= p.stop) {
        currentProg = p;
      } else if (p.start > now) {
        upcomingProgs.push(p);
      }
    }

    matchedChannels.push({
      ...ch,
      epg_id: matchedEpgId,
      has_epg: matchedEpgId !== null && progs.length > 0,
      current_prog: currentProg,
      upcoming_progs: upcomingProgs.slice(0, 3),
      total_progs: progs.length
    });
  }
}

// Render Summary Statistics
function renderStats() {
  const total = matchedChannels.length;
  const matched = matchedChannels.filter(c => c.has_epg).length;
  
  let totalListings = 0;
  for (let [id, progs] of epgProgrammes.entries()) {
    totalListings += progs.length;
  }

  const coverage = total > 0 ? ((matched / total) * 100).toFixed(1) : 0;

  document.getElementById('statTotalChannels').innerText = total.toLocaleString();
  document.getElementById('statMatchedChannels').innerText = matched.toLocaleString();
  document.getElementById('statTotalProgrammes').innerText = totalListings.toLocaleString();
  document.getElementById('statCoverageRate').innerText = `${coverage}%`;
}

// Populate Category Filter Dropdown
function populateCategoryDropdown() {
  const groupSelect = document.getElementById('groupFilter');
  groupSelect.innerHTML = `<option value="ALL">All Categories</option>`;

  const groups = new Set();
  for (let ch of matchedChannels) {
    if (ch.group_title) groups.add(ch.group_title);
  }

  Array.from(groups).sort().forEach(g => {
    const opt = document.createElement('option');
    opt.value = g;
    opt.textContent = g;
    groupSelect.appendChild(opt);
  });
}

// Setup Event Listeners for Searching & Filtering
function setupFilterEvents() {
  document.getElementById('searchInput').addEventListener('input', applyFilters);
  document.getElementById('groupFilter').addEventListener('change', applyFilters);
  document.getElementById('statusFilter').addEventListener('change', applyFilters);
}

// Filter Channels Logic
function applyFilters() {
  const searchVal = document.getElementById('searchInput').value.toLowerCase().trim();
  const groupVal = document.getElementById('groupFilter').value;
  const statusVal = document.getElementById('statusFilter').value;

  filteredChannels = matchedChannels.filter(ch => {
    // Search match
    const matchSearch = !searchVal || 
      ch.title.toLowerCase().includes(searchVal) || 
      ch.tvg_id.toLowerCase().includes(searchVal) ||
      (ch.current_prog && ch.current_prog.title.toLowerCase().includes(searchVal));

    // Category match
    const matchGroup = groupVal === "ALL" || ch.group_title === groupVal;

    // EPG Status match
    const matchStatus = statusVal === "ALL" || 
      (statusVal === "MATCHED" && ch.has_epg) || 
      (statusVal === "UNMATCHED" && !ch.has_epg);

    return matchSearch && matchGroup && matchStatus;
  });

  renderChannels();
}

// Set View Mode (Grid vs List)
function setViewMode(mode) {
  currentViewMode = mode;
  document.getElementById('viewGridBtn').classList.toggle('active', mode === 'grid');
  document.getElementById('viewListBtn').classList.toggle('active', mode === 'list');
  renderChannels();
}

// Render Channel Cards
function renderChannels() {
  const mainContainer = document.getElementById('mainContainer');

  if (filteredChannels.length === 0) {
    mainContainer.innerHTML = `
      <div class="empty-state">
        <i class="fa-solid fa-tv"></i>
        <h2>No Channels Found</h2>
        <p>Try adjusting your search criteria or category filter.</p>
      </div>
    `;
    return;
  }

  const gridClass = currentViewMode === 'list' ? 'channel-grid compact' : 'channel-grid';
  
  let html = `<div class="${gridClass}">`;

  for (let ch of filteredChannels) {
    const statusBadge = ch.has_epg 
      ? `<span class="badge-status matched"><i class="fa-solid fa-check"></i> EPG (${ch.total_progs})</span>`
      : `<span class="badge-status unmatched"><i class="fa-solid fa-xmark"></i> No EPG</span>`;

    const logoHtml = ch.tvg_logo 
      ? `<img src="${ch.tvg_logo}" alt="${ch.title}" class="channel-logo" onerror="this.src='https://via.placeholder.com/48/131b2e/06b6d4?text=TV'">`
      : `<i class="fa-solid fa-tv" style="color: var(--accent-cyan); font-size: 1.2rem;"></i>`;

    // Now Playing section
    let epgSection = '';
    if (ch.current_prog) {
      const p = ch.current_prog;
      const progress = calculateProgress(p.start, p.stop);
      const startFmt = formatTime(p.start);
      const stopFmt = formatTime(p.stop);

      epgSection = `
        <div class="epg-now-playing">
          <div class="now-header">
            <span><i class="fa-solid fa-circle" style="font-size:0.5rem; color:var(--danger-color)"></i> LIVE NOW</span>
            <span>${startFmt} - ${stopFmt}</span>
          </div>
          <div class="now-title">${escapeHtml(p.title)}</div>
          <div class="progress-bar-container">
            <div class="progress-bar-fill" style="width: ${progress}%"></div>
          </div>
        </div>
      `;
    } else if (ch.has_epg && ch.upcoming_progs.length > 0) {
      const nextP = ch.upcoming_progs[0];
      epgSection = `
        <div class="epg-now-playing">
          <div class="now-header" style="color: var(--text-secondary)">
            <span>UPCOMING</span>
            <span>${formatTime(nextP.start)}</span>
          </div>
          <div class="now-title">${escapeHtml(nextP.title)}</div>
        </div>
      `;
    } else {
      epgSection = `
        <div class="epg-now-playing" style="opacity: 0.6">
          <div class="now-title" style="font-size: 0.85rem; color: var(--text-muted)">No live schedule data</div>
        </div>
      `;
    }

    html += `
      <div class="channel-card" onclick="openChannelModal('${escapeHtml(ch.tvg_id || ch.title)}')">
        <div class="channel-header">
          <div class="channel-logo-container">${logoHtml}</div>
          <div class="channel-info">
            <div class="channel-title" title="${escapeHtml(ch.title)}">${escapeHtml(ch.title)}</div>
            <div class="channel-meta">
              <span class="tvg-id-badge">${escapeHtml(ch.tvg_id || 'N/A')}</span>
              <span>•</span>
              <span>${escapeHtml(ch.group_title)}</span>
            </div>
          </div>
          <div>${statusBadge}</div>
        </div>
        ${epgSection}
      </div>
    `;
  }

  html += `</div>`;
  mainContainer.innerHTML = html;
}

// Calculate Progress Bar %
function calculateProgress(start, stop) {
  const now = new Date().getTime();
  const startMs = start.getTime();
  const stopMs = stop.getTime();
  if (stopMs <= startMs) return 0;
  const pct = ((now - startMs) / (stopMs - startMs)) * 100;
  return Math.min(Math.max(pct, 0), 100);
}

// Format Time HH:MM AM/PM
function formatTime(dateObj) {
  if (!dateObj || isNaN(dateObj.getTime())) return "--:--";
  return dateObj.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

// Modal View
function openChannelModal(idOrTitle) {
  const ch = matchedChannels.find(c => (c.tvg_id === idOrTitle || c.title === idOrTitle));
  if (!ch) return;

  const modalBody = document.getElementById('modalBody');
  const progs = ch.epg_id ? (epgProgrammes.get(ch.epg_id) || []) : [];

  let scheduleListHtml = '';
  if (progs.length > 0) {
    scheduleListHtml = progs.map(p => `
      <div class="schedule-item" style="padding: 0.75rem; margin-bottom: 0.5rem; background: rgba(15, 23, 42, 0.6); border-radius: var(--radius-md);">
        <div style="display:flex; justify-content:space-between; margin-bottom:0.25rem;">
          <strong style="color: var(--accent-cyan); font-size:0.9rem;">${formatTime(p.start)} - ${formatTime(p.stop)}</strong>
          ${p.category ? `<span style="font-size:0.75rem; background:rgba(255,255,255,0.08); padding:0.1rem 0.4rem; border-radius:4px">${escapeHtml(p.category)}</span>` : ''}
        </div>
        <div style="font-weight:600; color: var(--text-primary); font-size:1rem;">${escapeHtml(p.title)}</div>
        ${p.desc ? `<div style="font-size:0.85rem; color: var(--text-secondary); margin-top:0.3rem;">${escapeHtml(p.desc)}</div>` : ''}
      </div>
    `).join('');
  } else {
    scheduleListHtml = `<p style="color: var(--text-muted);">No EPG programme schedule available for this channel.</p>`;
  }

  modalBody.innerHTML = `
    <div style="display:flex; align-items:center; gap:1rem; margin-bottom:1.5rem;">
      <div class="channel-logo-container" style="width:60px; height:60px;">
        ${ch.tvg_logo ? `<img src="${ch.tvg_logo}" class="channel-logo">` : `<i class="fa-solid fa-tv" style="font-size:1.5rem; color:var(--accent-cyan)"></i>`}
      </div>
      <div>
        <h2 style="font-size:1.4rem;">${escapeHtml(ch.title)}</h2>
        <p style="color: var(--text-secondary); font-size:0.85rem;">
          tvg-id: <code>${escapeHtml(ch.tvg_id || 'None')}</code> | Category: ${escapeHtml(ch.group_title)}
        </p>
      </div>
    </div>
    <h3 style="font-size:1.1rem; margin-bottom:1rem; color:var(--text-primary);">
      <i class="fa-solid fa-calendar-week" style="color:var(--accent-cyan)"></i> EPG Programme Guide (${progs.length} listings)
    </h3>
    <div style="max-height: 400px; overflow-y: auto; padding-right:0.5rem;">
      ${scheduleListHtml}
    </div>
  `;

  document.getElementById('programModal').classList.add('active');
}

function closeModalDirect() {
  document.getElementById('programModal').classList.remove('active');
}

function closeModal(event) {
  if (event.target.id === 'programModal') {
    closeModalDirect();
  }
}

function escapeHtml(str) {
  if (!str) return '';
  return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
}
