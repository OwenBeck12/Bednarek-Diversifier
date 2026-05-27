"use strict";

const MOON = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>`;
const SUN  = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>`;

// ─────────────────────────────────────────────────────────────────────────────
//  State
// ─────────────────────────────────────────────────────────────────────────────
let D = null;            // parsed stocks.json
let selectedIdx = -1;   // index of the currently selected stock
let sortedCorrs  = [];  // [{index, corr}, …] sorted low→high for selected stock

// ─────────────────────────────────────────────────────────────────────────────
//  DOM refs
// ─────────────────────────────────────────────────────────────────────────────
const $ = id => document.getElementById(id);

const loadingOverlay = $("loadingOverlay");
const stockList      = $("stockList");
const stockSearch    = $("stockSearch");
const stockMeta      = $("stockMeta");
const welcomeState   = $("welcomeState");
const corrView       = $("corrView");
const corrList       = $("corrList");
const corrSearch     = $("corrSearch");
const corrMeta       = $("corrMeta");
const themeBtn       = $("themeBtn");

// ─────────────────────────────────────────────────────────────────────────────
//  Boot
// ─────────────────────────────────────────────────────────────────────────────
(async function init() {
  applySystemTheme();
  setThemeIcon();

  try {
    const resp = await fetch("data/stocks.json");
    if (!resp.ok) throw new Error(`HTTP ${resp.status} — ${resp.statusText}`);
    D = await resp.json();
  } catch (err) {
    showError(err.message);
    return;
  }

  buildStockList();
  stockMeta.textContent = `${D.n.toLocaleString()} stocks`;

  const updated = document.getElementById("lastUpdated");
  if (updated && D.generated_at) {
    const d = new Date(D.generated_at);
    updated.textContent = `Last updated: ${d.toLocaleDateString("en-US", { month:"short", day:"numeric", year:"numeric" })}, ${d.toLocaleTimeString("en-US", { hour:"numeric", minute:"2-digit" })}`;
  }

  hideLoading();

  stockSearch.addEventListener("input", filterStockList);
  corrSearch.addEventListener("input",  filterCorrList);
  themeBtn.addEventListener("click",    toggleTheme);
})();

// ─────────────────────────────────────────────────────────────────────────────
//  Stock list
// ─────────────────────────────────────────────────────────────────────────────
function buildStockList() {
  const frag = document.createDocumentFragment();
  D.stocks.forEach((s, i) => {
    const li = document.createElement("li");
    li.className = "stock-item";
    li.setAttribute("role", "option");
    li.setAttribute("aria-selected", "false");
    li.dataset.index = i;
    // store lowercase for fast search
    li._searchKey = `${s.ticker} ${s.name}`.toLowerCase();

    li.innerHTML =
      `<div class="stock-item-ticker">${s.ticker}</div>` +
      `<div class="stock-item-name">${esc(s.name)}</div>`;

    li.addEventListener("click", () => selectStock(i));
    frag.appendChild(li);
  });
  stockList.appendChild(frag);
}

function filterStockList() {
  const q = stockSearch.value.trim().toLowerCase();
  let visible = 0;
  const items = stockList.children;
  for (let i = 0; i < items.length; i++) {
    const show = !q || items[i]._searchKey.includes(q);
    items[i].classList.toggle("hidden", !show);
    if (show) visible++;
  }
  stockMeta.textContent = q
    ? `${visible.toLocaleString()} of ${D.n.toLocaleString()} stocks`
    : `${D.n.toLocaleString()} stocks`;
}

// ─────────────────────────────────────────────────────────────────────────────
//  Select a stock
// ─────────────────────────────────────────────────────────────────────────────
function selectStock(idx) {
  // Deselect previous
  if (selectedIdx >= 0) {
    const prev = stockList.children[selectedIdx];
    if (prev) { prev.classList.remove("active"); prev.setAttribute("aria-selected", "false"); }
  }

  selectedIdx = idx;
  const item = stockList.children[idx];
  if (item) {
    item.classList.add("active");
    item.setAttribute("aria-selected", "true");
    item.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }

  // Ensure the left sidebar's search result shows the active item
  if (item && item.classList.contains("hidden")) {
    stockSearch.value = "";
    filterStockList();
  }

  renderCorrHeader(idx);
  renderCorrList(idx);
  corrSearch.value = "";

  welcomeState.style.display = "none";
  corrView.classList.remove("hidden");
}

// ─────────────────────────────────────────────────────────────────────────────
//  Correlation header (selected stock info)
// ─────────────────────────────────────────────────────────────────────────────
function renderCorrHeader(idx) {
  const s = D.stocks[idx];

  $("cTicker").textContent = s.ticker;
  $("cName").textContent   = s.name;
  $("cSector").textContent = s.sector;

  const ret   = s.annual_return * 100;
  const retEl = $("cReturn");
  retEl.textContent = (ret >= 0 ? "+" : "") + ret.toFixed(1) + "%";
  retEl.className   = "stat-value " + (ret >= 0 ? "positive" : "negative");

  $("cVol").textContent = (s.volatility * 100).toFixed(1) + "%";
  $("cN").textContent   = (D.n - 1).toLocaleString();
}

// ─────────────────────────────────────────────────────────────────────────────
//  Correlation list
// ─────────────────────────────────────────────────────────────────────────────
function renderCorrList(stockIdx) {
  const n    = D.n;
  const base = stockIdx * n;

  // Build sorted array
  sortedCorrs = [];
  for (let j = 0; j < n; j++) {
    if (j !== stockIdx) {
      sortedCorrs.push({ index: j, corr: D.correlations[base + j] });
    }
  }
  sortedCorrs.sort((a, b) => a.corr - b.corr);

  // Render via DocumentFragment (batch DOM update)
  const frag = document.createDocumentFragment();
  sortedCorrs.forEach(({ index, corr }, rank) => {
    const s     = D.stocks[index];
    const style = corrStyle(corr);

    const li = document.createElement("li");
    li.className = "corr-item";
    li.setAttribute("role", "option");
    li.dataset.rank = rank;
    li._searchKey   = `${s.ticker} ${s.name}`.toLowerCase();

    li.innerHTML =
      `<span class="corr-rank">#${(rank + 1).toLocaleString()}</span>` +
      `<div class="corr-body">` +
        `<div class="corr-row1">` +
          `<span class="corr-item-ticker">${s.ticker}</span>` +
          `<span class="corr-item-name">${esc(s.name)}</span>` +
        `</div>` +
        `<div class="corr-item-sector">${esc(s.sector)}</div>` +
      `</div>` +
      `<span class="corr-badge" style="background:${style.bg};color:${style.fg};${style.border ? `border:2px solid ${style.border};` : ''}">` +
        `ρ = ${corr >= 0 ? "+" : ""}${corr.toFixed(3)}` +
      `</span>`;

    li.addEventListener("click", () => selectStock(index));
    frag.appendChild(li);
  });

  corrList.replaceChildren(frag);
  corrMeta.textContent = `${sortedCorrs.length.toLocaleString()} stocks`;
  corrList.parentElement.scrollTop = 0;
}

function filterCorrList() {
  const q = corrSearch.value.trim().toLowerCase();
  let visible = 0;
  const items = corrList.children;
  for (let i = 0; i < items.length; i++) {
    const show = !q || items[i]._searchKey.includes(q);
    items[i].classList.toggle("hidden", !show);
    if (show) visible++;
  }
  corrMeta.textContent = q
    ? `${visible.toLocaleString()} of ${sortedCorrs.length.toLocaleString()} stocks`
    : `${sortedCorrs.length.toLocaleString()} stocks`;
}

// ─────────────────────────────────────────────────────────────────────────────
//  Correlation badge color
// ─────────────────────────────────────────────────────────────────────────────
function corrStyle(rho) {
  if (rho <= -0.20) return { bg: "#166534", fg: "#dcfce7", border: "#14532d" };
  if (rho <= 0)     return { bg: "#86efac", fg: "#14532d" };
  if (rho <= 0.30)  return { bg: "#bbf7d0", fg: "#166534" };
  if (rho <= 0.70)  return { bg: "#f97316", fg: "#ffffff" };
                    return { bg: "#991b1b", fg: "#fee2e2", border: "#7f1d1d" };
}

// ─────────────────────────────────────────────────────────────────────────────
//  Theme
// ─────────────────────────────────────────────────────────────────────────────
function isDark() { return document.documentElement.getAttribute("data-theme") === "dark"; }

function applySystemTheme() {
  if (window.matchMedia("(prefers-color-scheme: dark)").matches) {
    document.documentElement.setAttribute("data-theme", "dark");
  }
}

function toggleTheme() {
  document.documentElement.setAttribute("data-theme", isDark() ? "light" : "dark");
  setThemeIcon();
}

function setThemeIcon() {
  themeBtn.innerHTML = isDark() ? SUN : MOON;
  themeBtn.title = isDark() ? "Switch to light mode" : "Switch to dark mode";
}

// ─────────────────────────────────────────────────────────────────────────────
//  Loading / error states
// ─────────────────────────────────────────────────────────────────────────────
function hideLoading() {
  loadingOverlay.classList.add("fade-out");
  setTimeout(() => { loadingOverlay.style.display = "none"; }, 420);
}

function showError(msg) {
  loadingOverlay.innerHTML = `
    <div class="error-card">
      <div class="error-emoji">⚠️</div>
      <h2 class="error-title">Could not load data</h2>
      <div class="error-body">
        <p>${esc(msg)}</p>
        <br>
        <p>Make sure you've run <code>fetch_data.py</code> first, then serve the
        folder over HTTP (browsers block <code>fetch()</code> on
        <code>file://</code> URLs):</p>
        <br>
        <p><code>python -m http.server 8080</code></p>
        <br>
        <p>Then open <code>http://localhost:8080</code></p>
      </div>
    </div>`;
}

// ─────────────────────────────────────────────────────────────────────────────
//  Helpers
// ─────────────────────────────────────────────────────────────────────────────
function esc(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
