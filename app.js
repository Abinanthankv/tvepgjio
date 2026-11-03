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

// Matching configuration (mirrors epg_matcher.py)
const QUALITY_TOKENS = new Set(['hd', 'sd', 'fhd', 'uhd', '4k', '8k', 'hdr', 'hevc', 'x264', 'x265', '1080p', '720p', '576p', '540p', '504p', '480p', '396p', '360p']);
const FORMAT_TOKENS = new Set(['stb', 'mobile', 'ott']);
const LOOSE_STOPWORDS = new Set(['tv', 'channel', 'network', 'the', 'and']);
const LANGUAGE_TOKENS = new Set(['tamil', 'telugu', 'hindi', 'kannada', 'malayalam', 'marathi', 'bengali', 'bangla', 'punjabi', 'gujarati', 'odia', 'odiya', 'urdu', 'bhojpuri', 'assamese', 'english', 'sanskrit', 'konkani', 'kashmiri', 'nepali', 'india', 'indian', 'asia', 'usa', 'america', 'uk', 'canada', 'australia', 'arabia', 'global', 'world']);
const DISTINCTIVE_TOKENS = new Set(['jr', 'junior', 'kids', 'news', 'movies', 'movie', 'music', 'sports', 'gold', 'plus', 'max', 'prime', 'action', 'classic', 'classics', 'comedy', 'crime', 'history', 'wild', 'life', 'live', 'shopping', 'yoga', 'bhakti', 'devotional', 'regional', 'national', 'international', '24x7']);
const FUZZY_MIN_SCORE = 0.86;
const FUZZY_MIN_MARGIN = 0.05;

let channelAliases = new Map(); // normalised playlist key -> official source name

// Initialize events when DOM loaded
document.addEventListener('DOMContentLoaded', () => {
  setupFileInputs();
  setupFilterEvents();
  loadChannelAliases();
});

// Load curated aliases so the browser matcher agrees with the Python matcher.
async function loadChannelAliases() {
  try {
    const res = await fetch('channel_aliases.json', { cache: 'no-store' });
    if (!res.ok) return;
    const data = await res.json();
    const aliases = data && data.aliases ? data.aliases : data;
    channelAliases = new Map();
    for (const [key, value] of Object.entries(aliases || {})) {
      if (typeof value === 'string' && !key.startsWith('_')) {
        channelAliases.set(normalizeName(key), value);
      }
    }
    console.log(`Loaded ${channelAliases.size} channel aliases.`);
  } catch (err) {
    console.warn('Could not load channel_aliases.json; continuing without aliases.', err);
  }
}


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
    if (channelAliases.size === 0) {
      await loadChannelAliases();
    }
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

// Title is everything after the last comma that is outside double quotes.
// Some playlists embed a user-agent attribute containing commas.
function splitExtinfTitle(line) {
  let inQuotes = false;
  let cut = -1;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (ch === '"') {
      inQuotes = !inQuotes;
    } else if (ch === ',' && !inQuotes) {
      cut = i;
    }
  }
  return cut !== -1 ? line.substring(cut + 1).trim() : "";
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

      const title = splitExtinfTitle(extinf);

      let streamUrl = "";
      if (i + 1 < lines.length && !lines[i + 1].trim().startsWith('#')) {
        streamUrl = lines[i + 1].trim();
        i++;
      }

      channels.push({
        tvg_id: tvgIdMatch ? tvgIdMatch[1] : "",
        tvg_name: tvgNameMatch ? tvgNameMatch[1] : "",
        tvg_logo: tvgLogoMatch ? tvgLogoMatch[1] : "",
        group_title: groupMatch ? groupMatch[1] : "Uncategorized",
        title: title || (tvgNameMatch ? tvgNameMatch[1] : "Untitled Channel"),
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

// ---------------------------------------------------------------------------
// Channel matching (mirrors epg_matcher.py)
// ---------------------------------------------------------------------------
function rawTokens(name) {
  if (!name) return [];
  let text = name.normalize('NFKD').replace(/[\u0300-\u036f]/g, '');
  text = text.toLowerCase().replace(/&/g, ' and ');
  text = text.replace(/[\(\[\{][^\)\]\}]*[\)\]\}]/g, ' ');
  return text.match(/[a-z0-9]+/g) || [];
}

function identityTokens(name) {
  let tokens = rawTokens(name).filter(t => !QUALITY_TOKENS.has(t) && !FORMAT_TOKENS.has(t));
  if (tokens.length && tokens[0] === 'the') tokens = tokens.slice(1);
  return tokens;
}

function normalizeName(name, loose = false) {
  let tokens = identityTokens(name);
  if (loose) tokens = tokens.filter(t => !LOOSE_STOPWORDS.has(t));
  return tokens.join('');
}

function digitsOf(name) {
  return new Set((normalizeName(name).match(/\d+/g) || []));
}

function languageTokens(name) {
  return new Set(identityTokens(name).filter(t => LANGUAGE_TOKENS.has(t)));
}

function tokenSet(name) {
  return new Set(identityTokens(name).filter(t => !LOOSE_STOPWORDS.has(t)));
}

function firstToken(name) {
  for (const token of identityTokens(name)) {
    if (!LOOSE_STOPWORDS.has(token) && !QUALITY_TOKENS.has(token)) return token;
  }
  return '';
}

function variantOf(name) {
  const tokens = new Set(rawTokens(name));
  if (['hd', 'fhd', 'uhd', '4k', 'hdr'].some(t => tokens.has(t))) return 'hd';
  if (tokens.has('sd')) return 'sd';
  return '';
}

function queryVariant(tvgId, title) {
  if (tvgId && tvgId.includes('@')) {
    const suffix = tvgId.split('@').pop().trim().toLowerCase();
    if (['hd', 'fhd', 'uhd', '4k'].includes(suffix)) return 'hd';
    if (suffix === 'sd') return 'sd';
  }
  return variantOf(title);
}

// Longest-common-subsequence ratio, equivalent in spirit to Python difflib.
function sequenceRatio(a, b) {
  if (!a && !b) return 1;
  if (!a || !b) return 0;
  const dp = new Array(b.length + 1).fill(0);
  for (let i = 1; i <= a.length; i++) {
    let previous = 0;
    for (let j = 1; j <= b.length; j++) {
      const temp = dp[j];
      dp[j] = a[i - 1] === b[j - 1] ? previous + 1 : Math.max(dp[j], dp[j - 1]);
      previous = temp;
    }
  }
  return (2 * dp[b.length]) / (a.length + b.length);
}

function sameSet(a, b) {
  if (a.size !== b.size) return false;
  for (const value of a) if (!b.has(value)) return false;
  return true;
}

function intersect(a, b) {
  const result = new Set();
  for (const value of a) if (b.has(value)) result.add(value);
  return result;
}

function tokensCover(left, right, threshold = 0.8) {
  if (!left.size || !right.size) return false;
  for (const token of new Set([...left, ...right])) {
    const other = left.has(token) ? right : left;
    let covered = false;
    for (const candidate of other) {
      if (token === candidate || sequenceRatio(token, candidate) >= threshold) {
        covered = true;
        break;
      }
    }
    if (!covered) return false;
  }
  return true;
}

function chooseByVariant(ids, queryVar, sourceVariants) {
  if (ids.length === 1) return { id: ids[0], candidates: [] };
  const ranked = ids.map(id => {
    const sourceVar = sourceVariants.get(id) || '';
    let rank;
    if (queryVar && sourceVar === queryVar) rank = 0;
    else if (!sourceVar) rank = 1;
    else if (!queryVar) rank = 2;
    else rank = 3;
    return { rank, id };
  }).sort((a, b) => a.rank - b.rank);
  const bestRank = ranked[0].rank;
  const best = ranked.filter(item => item.rank === bestRank).map(item => item.id);
  if (best.length === 1) return { id: best[0], candidates: [] };
  return { id: null, candidates: ids };
}

function fuzzyScore(qTokens, qNorm, qDigits, qLangs, qFirst, candidateName) {
  const cTokens = tokenSet(candidateName);
  const cNorm = normalizeName(candidateName);
  if (!cTokens.size || !cNorm) return 0;

  // Numeric identity must match (Dangal != Dangal 2).
  if (!sameSet(digitsOf(candidateName), qDigits)) return 0;

  // Language/region markers must not conflict.
  const cLangs = languageTokens(candidateName);
  if (qLangs.size && cLangs.size && !sameSet(qLangs, cLangs)) return 0;

  // Sibling-channel words must agree (Nickelodeon != Nickelodeon Jr.).
  if (!sameSet(intersect(qTokens, DISTINCTIVE_TOKENS), intersect(cTokens, DISTINCTIVE_TOKENS))) return 0;

  // First meaningful word must agree (NTV Telugu != TV9 Telugu).
  if (qFirst && firstToken(candidateName) !== qFirst) return 0;

  // Every word must be nearly present on the other side.
  if (!tokensCover(qTokens, cTokens)) return 0;

  const intersectionSize = [...qTokens].filter(t => cTokens.has(t)).length;
  const unionSize = new Set([...qTokens, ...cTokens]).size;
  const jaccard = unionSize ? intersectionSize / unionSize : 0;
  return Math.max(jaccard, sequenceRatio(qNorm, cNorm));
}

function exactFromIndex(index, key, queryVar, sourceVariants) {
  if (!key) return null;
  const ids = index.get(key);
  if (!ids || ids.size === 0) return null;
  const chosen = chooseByVariant([...ids], queryVar, sourceVariants);
  if (chosen.id) {
    return { status: 'exact', epgId: chosen.id, method: 'exact-name', score: 1 };
  }
  return { status: 'ambiguous', epgId: null, method: 'exact-name', score: 1, candidates: chosen.candidates };
}

function resolveAlias(target, strictIndex, looseIndex) {
  if (epgChannels.has(target)) return target;
  for (const index of [strictIndex, looseIndex]) {
    for (const key of [normalizeName(target), normalizeName(target, true)]) {
      const ids = index.get(key);
      if (ids && ids.size === 1) return [...ids][0];
    }
  }
  return null;
}

function fuzzyMatchChannel(query) {
  const qTokens = tokenSet(query);
  const qNorm = normalizeName(query);
  if (!qTokens.size || qNorm.length < 4) {
    return { status: 'unmatched', epgId: null, method: 'fuzzy', score: 0 };
  }

  const qDigits = digitsOf(query);
  const qLangs = languageTokens(query);
  const qFirst = firstToken(query);
  const scored = [];

  for (const [id, names] of epgChannels.entries()) {
    let best = 0;
    for (const name of (names.length ? names : [id])) {
      // Cheap pre-filter: the first meaningful word is a hard guard in
      // fuzzyScore, so skip candidates that cannot pass it.
      if (qFirst && firstToken(name) !== qFirst) continue;
      best = Math.max(best, fuzzyScore(qTokens, qNorm, qDigits, qLangs, qFirst, name));
    }
    if (best > 0) scored.push({ score: best, id });
  }

  if (!scored.length) {
    return { status: 'unmatched', epgId: null, method: 'fuzzy', score: 0 };
  }

  scored.sort((a, b) => b.score - a.score);
  const top = scored[0];
  const runnerUp = scored[1] ? scored[1].score : 0;

  if (top.score < FUZZY_MIN_SCORE) {
    return { status: 'unmatched', epgId: null, method: 'fuzzy', score: top.score };
  }
  if (runnerUp && top.score - runnerUp < FUZZY_MIN_MARGIN) {
    return {
      status: 'ambiguous',
      epgId: null,
      method: 'fuzzy',
      score: top.score,
      candidates: scored.slice(0, 3).map(item => item.id)
    };
  }
  return { status: 'fuzzy', epgId: top.id, method: 'fuzzy', score: top.score };
}

function matchChannel(ch, strictIndex, looseIndex, sourceVariants) {
  const tvgId = ch.tvg_id || '';
  const baseIdFull = tvgId.split('@')[0];
  const baseId = baseIdFull.includes('.') ? baseIdFull.split('.')[0] : baseIdFull;
  const queryVar = queryVariant(tvgId, ch.title || ch.tvg_name);

  // 1. Exact source id.
  if (tvgId && epgChannels.has(tvgId)) {
    return { status: 'exact', epgId: tvgId, method: 'source-id', score: 1 };
  }
  if (baseId && epgChannels.has(baseId)) {
    return { status: 'exact', epgId: baseId, method: 'source-id', score: 1 };
  }

  // 2. Exact normalised name (strict, then loose).
  const strictKeys = [normalizeName(ch.title), normalizeName(ch.tvg_name), normalizeName(baseId)];
  for (const key of strictKeys) {
    const result = exactFromIndex(strictIndex, key, queryVar, sourceVariants);
    if (result) return result;
  }
  const looseKeys = [normalizeName(ch.title, true), normalizeName(ch.tvg_name, true), normalizeName(baseId, true)];
  for (const key of looseKeys) {
    const result = exactFromIndex(looseIndex, key, queryVar, sourceVariants);
    if (result) {
      if (result.status === 'exact') result.method = 'exact-name-loose';
      return result;
    }
  }

  // 3. Curated alias.
  for (const key of strictKeys) {
    const target = channelAliases.get(key);
    if (!target) continue;
    const resolved = resolveAlias(target, strictIndex, looseIndex);
    if (resolved) return { status: 'alias', epgId: resolved, method: 'alias', score: 1 };
  }

  // 4. Guarded fuzzy.
  return fuzzyMatchChannel(ch.title || ch.tvg_name || baseId);
}

// Perform Channel Matching
function performMatching() {
  matchedChannels = [];

  // Build lookup indexes for EPG channels. Values are Sets so collisions
  // stay visible and can be resolved by feed variant or reported ambiguous.
  const strictIndex = new Map();
  const looseIndex = new Map();
  const sourceVariants = new Map();

  const addKey = (index, key, id) => {
    if (!key) return;
    if (!index.has(key)) index.set(key, new Set());
    index.get(key).add(id);
  };

  for (const [id, names] of epgChannels.entries()) {
    const primary = names.length ? names[0] : id;
    sourceVariants.set(id, variantOf(primary));
    addKey(strictIndex, normalizeName(id), id);
    for (const name of names) {
      addKey(strictIndex, normalizeName(name), id);
      addKey(looseIndex, normalizeName(name, true), id);
    }
  }

  const now = new Date();

  for (const ch of m3uChannels) {
    const result = matchChannel(ch, strictIndex, looseIndex, sourceVariants);
    const matchedEpgId = result.epgId;
    const progs = matchedEpgId ? (epgProgrammes.get(matchedEpgId) || []) : [];
    const sourceName = matchedEpgId && epgChannels.has(matchedEpgId)
      ? epgChannels.get(matchedEpgId)[0]
      : '';

    // Find current live program and upcoming
    let currentProg = null;
    const upcomingProgs = [];

    for (const p of progs) {
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
      match_status: result.status,
      match_method: result.method,
      match_score: result.score,
      match_candidates: result.candidates || [],
      source_name: sourceName,
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
      (ch.source_name || '').toLowerCase().includes(searchVal) ||
      ch.tvg_id.toLowerCase().includes(searchVal) ||
      (ch.current_prog && ch.current_prog.title.toLowerCase().includes(searchVal));

    // Category match
    const matchGroup = groupVal === "ALL" || ch.group_title === groupVal;

    // EPG Status match
    let matchStatus = true;
    if (statusVal === "MATCHED") matchStatus = ch.has_epg;
    else if (statusVal === "UNMATCHED") matchStatus = !ch.has_epg;
    else if (statusVal === "FUZZY") matchStatus = ch.match_status === "fuzzy";
    else if (statusVal === "REVIEW") matchStatus = ch.match_status === "ambiguous";

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
    // Prefer the official source name in the guide; keep the playlist name
    // visible underneath so the mapping is always auditable.
    const displayTitle = ch.source_name || ch.title;
    const showPlaylistName = ch.source_name && ch.source_name !== ch.title;

    let statusBadge;
    if (ch.has_epg) {
      statusBadge = `<span class="badge-status matched"><i class="fa-solid fa-check"></i> EPG (${ch.total_progs})</span>`;
    } else if (ch.match_status === 'ambiguous') {
      statusBadge = `<span class="badge-status unmatched" title="Multiple source channels are equally plausible"><i class="fa-solid fa-code-branch"></i> Review</span>`;
    } else {
      statusBadge = `<span class="badge-status unmatched"><i class="fa-solid fa-xmark"></i> No EPG</span>`;
    }

    let methodBadge = '';
    if (ch.match_status === 'fuzzy') {
      methodBadge = `<span class="match-badge fuzzy" title="Guarded fuzzy match, score ${ch.match_score.toFixed(2)}">fuzzy ${ch.match_score.toFixed(2)}</span>`;
    } else if (ch.match_status === 'alias') {
      methodBadge = `<span class="match-badge alias" title="Matched using channel_aliases.json">alias</span>`;
    }

    const logoHtml = ch.tvg_logo 
      ? `<img src="${ch.tvg_logo}" alt="${escapeHtml(displayTitle)}" class="channel-logo" onerror="this.src='https://via.placeholder.com/48/131b2e/06b6d4?text=TV'">`
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
            <div class="channel-title" title="${escapeHtml(displayTitle)}">${escapeHtml(displayTitle)} ${methodBadge}</div>
            ${showPlaylistName ? `<div class="channel-subtitle" title="Playlist name">${escapeHtml(ch.title)}</div>` : ''}
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
  const displayTitle = ch.source_name || ch.title;
  const matchDetail = ch.match_status
    ? `${ch.match_status}${ch.match_method ? ' / ' + ch.match_method : ''}${ch.match_status === 'fuzzy' ? ' (' + ch.match_score.toFixed(2) + ')' : ''}`
    : 'unknown';

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
        <h2 style="font-size:1.4rem;">${escapeHtml(displayTitle)}</h2>
        ${ch.source_name && ch.source_name !== ch.title ? `<p style="color: var(--text-muted); font-size:0.85rem; margin-bottom:0.2rem;">Playlist name: ${escapeHtml(ch.title)}</p>` : ''}
        <p style="color: var(--text-secondary); font-size:0.85rem;">
          tvg-id: <code>${escapeHtml(ch.tvg_id || 'None')}</code> | Category: ${escapeHtml(ch.group_title)}
        </p>
        <p style="color: var(--text-muted); font-size:0.78rem; margin-top:0.2rem;">Match: ${escapeHtml(matchDetail)}</p>
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
