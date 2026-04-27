"use strict";

// ═══════════════════════════════════════════════════
// CONSTANTS
// ═══════════════════════════════════════════════════
const STRAT_COLORS = { FLIP:"#5dade2", MERCH:"#f39c12", TREND:"#2ecc71", NEWS:"#e74c3c" };
const SCORE_HIGH = "#2ecc71", SCORE_MID = "#f39c12", SCORE_LOW = "#e74c3c";

// ═══════════════════════════════════════════════════
// UTILITIES
// ═══════════════════════════════════════════════════
function fmtGP(v) {
  if (v == null || isNaN(v)) return "—";
  const n = Math.round(v);
  if (Math.abs(n) >= 1e9) return (n/1e9).toFixed(2)+"B";
  if (Math.abs(n) >= 1e6) return (n/1e6).toFixed(1)+"M";
  if (Math.abs(n) >= 1e3) return Math.round(n/1e3)+"k";
  return n.toLocaleString();
}

function fmtPct(v, decimals=1) {
  if (v == null || isNaN(v)) return "—";
  return (v > 0 ? "+" : "") + v.toFixed(decimals) + "%";
}

function scoreColor(s) {
  if (s >= 70) return SCORE_HIGH;
  if (s >= 50) return SCORE_MID;
  return SCORE_LOW;
}

function parsePrice(s) {
  s = (s||"").trim().toUpperCase();
  if (s.endsWith("B")) return parseFloat(s)*1e9;
  if (s.endsWith("M")) return parseFloat(s)*1e6;
  if (s.endsWith("K")) return parseFloat(s)*1e3;
  const n = parseFloat(s);
  return isNaN(n) ? 2e9 : n*1e6;
}

function parseGP(s) {
  s = (s||"").trim().replace(/,/g,"").toUpperCase();
  if (!s) return null;
  if (s.endsWith("B")) return Math.round(parseFloat(s)*1e9);
  if (s.endsWith("M")) return Math.round(parseFloat(s)*1e6);
  if (s.endsWith("K")) return Math.round(parseFloat(s)*1e3);
  const n = parseFloat(s);
  return isNaN(n) ? null : Math.round(n);
}

function movingAvg(arr, window) {
  return arr.map((_, i) => {
    const slice = arr.slice(Math.max(0, i-window+1), i+1).filter(v => v!=null && !isNaN(v));
    return slice.length ? slice.reduce((a,b)=>a+b,0)/slice.length : null;
  });
}

function calcRSI(prices, period=14) {
  const result = new Array(prices.length).fill(null);
  if (prices.length < period+1) return result;
  let avgGain=0, avgLoss=0;
  for (let i=0; i<period; i++) {
    const d = prices[i+1]-prices[i];
    if (d>0) avgGain+=d; else avgLoss-=d;
  }
  avgGain/=period; avgLoss/=period;
  result[period] = avgLoss===0 ? 100 : 100-(100/(1+avgGain/avgLoss));
  for (let i=period+1; i<prices.length; i++) {
    const d = prices[i]-prices[i-1];
    avgGain = (avgGain*(period-1)+(d>0?d:0))/period;
    avgLoss = (avgLoss*(period-1)+(d<0?-d:0))/period;
    result[i] = avgLoss===0 ? 100 : 100-(100/(1+avgGain/avgLoss));
  }
  return result;
}

async function api(path, opts={}) {
  const r = await fetch(path, opts);
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return r.json();
}

// ═══════════════════════════════════════════════════
// STATUS BAR
// ═══════════════════════════════════════════════════
const statusDot  = document.getElementById("status-dot");
const statusText = document.getElementById("status-text");
let _statusInterval = null;
let _lastScoredCount = 0;

let _lastRefreshedAt = 0;

function _ageStr(ts) {
  if (!ts) return "";
  const secs = Math.floor(Date.now() / 1000) - ts;
  if (secs < 10)  return "just now";
  if (secs < 60)  return `${secs}s ago`;
  if (secs < 3600) return `${Math.floor(secs/60)}m ago`;
  return `${Math.floor(secs/3600)}h ago`;
}

function pollStatus() {
  clearInterval(_statusInterval);
  _statusInterval = setInterval(async () => {
    try {
      const s = await api("/api/status");
      const age = s.refreshed_at ? ` · prices ${_ageStr(s.refreshed_at)}` : "";
      statusText.textContent = s.message + age;
      statusDot.className = "dot " + (s.running ? "running" : "idle");
      // Auto-reload dashboard whenever the scored-item count increases
      if ((s.count || 0) > _lastScoredCount) {
        _lastScoredCount = s.count;
        Dashboard.load();
      }
      // Auto-reload dashboard when prices refresh (~60s cycle)
      if (s.refreshed_at && s.refreshed_at !== _lastRefreshedAt) {
        _lastRefreshedAt = s.refreshed_at;
        if (!s.running && document.getElementById("tab-dashboard").classList.contains("active")) {
          Dashboard.load();
        }
      }
    } catch {}
  }, 1500);
}

// ═══════════════════════════════════════════════════
// TAB NAVIGATION
// ═══════════════════════════════════════════════════
document.querySelectorAll(".tab-btn").forEach(btn => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
    document.querySelectorAll(".tab-content").forEach(c => c.classList.add("hidden"));
    btn.classList.add("active");
    document.getElementById("tab-"+btn.dataset.tab).classList.remove("hidden");
    // Lazy-load on first visit
    if (btn.dataset.tab === "recommendations" && !Recs._loaded) Recs.load();
    if (btn.dataset.tab === "watchlist") Watchlist.load();
  });
});

// ═══════════════════════════════════════════════════
// GLOBAL ACTIONS (header buttons)
// ═══════════════════════════════════════════════════
const App = {
  async triggerScore() {
    await api("/api/score", {method:"POST"});
    // Wait for scoring to finish then reload dashboard
    setTimeout(() => Dashboard.load(), 4000);
  },
  async triggerRefresh() {
    await api("/api/refresh", {method:"POST"});
  },
  async triggerNews() {
    await api("/api/news", {method:"POST"});
  },
};

// ═══════════════════════════════════════════════════
// DASHBOARD
// ═══════════════════════════════════════════════════
const Dashboard = {
  _items: [],
  _sortCol: "score",
  _sortAsc: false,

  async load() {
    try {
      this._items = await api("/api/items");
      this.applyFilters();
      this._renderTopPicks();
    } catch(e) {
      console.error("Dashboard load failed:", e);
    }
  },

  applyFilters() {
    const minScore = +document.getElementById("f-score").value;
    const search   = document.getElementById("f-search").value.trim().toLowerCase();
    const strategy = document.getElementById("f-strat").value;
    const minPrice = parsePrice(document.getElementById("f-min-price").value);
    const maxPrice = parsePrice(document.getElementById("f-price").value);
    document.getElementById("score-val").textContent = minScore;

    let rows = this._items.filter(i =>
      (i.score||0) >= minScore &&
      (!search || (i.name||"").toLowerCase().includes(search)) &&
      (i.current_low||0) >= minPrice &&
      (i.current_low||0) <= maxPrice &&
      (!strategy || i.strategy === strategy)
    );
    this._renderTable(rows);
  },

  _sortRows(rows) {
    const col = this._sortCol, asc = this._sortAsc;
    return [...rows].sort((a,b) => {
      let av = a[col]??0, bv = b[col]??0;
      if (typeof av === "string") av = av.toLowerCase();
      if (typeof bv === "string") bv = bv.toLowerCase();
      return asc ? (av>bv?1:av<bv?-1:0) : (av<bv?1:av>bv?-1:0);
    });
  },

  _renderTable(rows) {
    rows = this._sortRows(rows);
    const tbody = document.getElementById("items-tbody");
    if (!rows.length) {
      tbody.innerHTML = `<tr><td colspan="12" class="placeholder">No items match the current filters.</td></tr>`;
      return;
    }
    tbody.innerHTML = rows.map((r, i) => {
      const sc = r.score||0;
      const news = r.news_signals?.length ? '<span class="news-star">★</span>' : "";
      const stratColor = STRAT_COLORS[r.strategy]||"#aaa";
      const icon = r.icon_url ? `<img src="${r.icon_url}" width="20" height="20" style="vertical-align:middle;margin-right:5px;image-rendering:pixelated" onerror="this.style.display='none'">` : "";
      return `<tr class="${r.news_signals?.length?'has-news':''}"
               data-id="${r.item_id}" data-name="${escHtml(r.name||'')}">
        <td>${i+1}</td>
        <td class="td-name">${icon}${escHtml(r.name||"")}${news}</td>
        <td style="color:${stratColor};font-weight:700">${r.strategy||"—"}</td>
        <td style="color:${scoreColor(sc)};font-weight:700">${sc.toFixed(0)}</td>
        <td>${fmtGP(r.current_low)}</td>
        <td>${r.net_margin_pct!=null?fmtPct(r.net_margin_pct):"—"}</td>
        <td>${fmtGP(r.daily_flip_profit)}</td>
        <td style="color:${changeColor(r.change_1d)}">${r.change_1d!=null?fmtPct(r.change_1d):"—"}</td>
        <td style="color:${changeColor(r.change_30d)}">${r.change_30d!=null?fmtPct(r.change_30d):"—"}</td>
        <td style="color:${rsiColor(r.rsi)}">${r.rsi!=null?r.rsi.toFixed(0):"—"}</td>
        <td>${r.avg_daily_vol!=null?Math.round(r.avg_daily_vol).toLocaleString():"—"}</td>
        <td style="text-align:center"><button class="btn-reason"
          data-name="${escHtml(r.name||'')}"
          data-score="${sc.toFixed(0)}"
          data-reason="${escHtml(r.reason||'')}">Info</button></td>
      </tr>`;
    }).join("");

    // Sort headers
    document.querySelectorAll("#items-table th[data-col]").forEach(th => {
      th.className = th.dataset.col===this._sortCol
        ? (this._sortAsc?"sort-asc":"sort-desc") : "";
      th.onclick = () => {
        if (this._sortCol===th.dataset.col) this._sortAsc=!this._sortAsc;
        else { this._sortCol=th.dataset.col; this._sortAsc=false; }
        this.applyFilters();
      };
    });
  },

  _renderTopPicks() {
    const top = this._items.filter(i=>(i.score||0)>=50).slice(0,5);
    const el = document.getElementById("top-picks-cards");
    if (!top.length) { el.innerHTML=`<span class="dim-text">No items scored above 50 yet.</span>`; return; }
    el.innerHTML = top.map(r => {
      const sc = r.score||0;
      const stratColor = STRAT_COLORS[r.strategy]||"#aaa";
      const news = r.news_signals?.length ? `<span class="news-star">★ NEWS</span>` : "";
      const pickIcon = r.icon_url ? `<img src="${r.icon_url}" width="24" height="24" style="vertical-align:middle;margin-right:6px;image-rendering:pixelated" onerror="this.style.display='none'">` : "";
      return `<div class="pick-card${r.news_signals?.length?' has-news':''}"
               data-id="${r.item_id}" data-name="${escHtml(r.name||'')}">
        <div class="strat" style="color:${stratColor}">[${r.strategy||"?"}] ${news}</div>
        <div class="item-name">${pickIcon}${escHtml(r.name||"")}</div>
        <div class="score-line" style="color:${scoreColor(sc)}">Score: ${sc.toFixed(0)}</div>
        <div class="detail-line">${fmtGP(r.current_low)} · ${fmtGP(r.daily_flip_profit)}/day</div>
        <div class="detail-line" style="font-size:10px;color:#666">${escHtml((r.reason||"").slice(0,50))}</div>
      </div>`;
    }).join("");
    el.querySelectorAll(".pick-card").forEach(c => {
      c.addEventListener("click", () => {
        Charts.loadItem(+c.dataset.id, c.dataset.name);
        switchTab("charts");
      });
    });
  },
};

// One-time delegated click handler for dashboard table body.
// Must be outside _renderTable — registering inside would accumulate one
// extra handler per render, causing clicks to fire multiple times.
document.getElementById("items-tbody").addEventListener("click", (e) => {
  const btn = e.target.closest(".btn-reason");
  if (btn) {
    openReason(btn.dataset.name, btn.dataset.score, btn.dataset.reason);
    return;
  }
  const row = e.target.closest("tr[data-id]");
  if (row) {
    Charts.loadItem(+row.dataset.id, row.dataset.name);
    switchTab("charts");
  }
});

// Filter inputs → live re-filter
document.getElementById("f-score").addEventListener("input",    () => Dashboard.applyFilters());
document.getElementById("f-search").addEventListener("input",   () => Dashboard.applyFilters());
document.getElementById("f-strat").addEventListener("change",   () => Dashboard.applyFilters());
document.getElementById("f-min-price").addEventListener("input", () => Dashboard.applyFilters());

// ═══════════════════════════════════════════════════
// CHARTS
// ═══════════════════════════════════════════════════
const Charts = {
  _currentDays:     90,
  _currentId:       null,
  _currentData:     null,
  _currentIntraday: null,

  async loadItem(itemId, itemName) {
    this._currentId = itemId;
    document.getElementById("chart-item-name").textContent = itemName;
    document.getElementById("chart-search").value = itemName;
    try {
      const data = await api(`/api/items/${itemId}/timeseries`);
      this._currentData = data;
      if (this._currentDays === 1) {
        this._loadAndDrawIntraday(itemId);
      } else {
        this._draw(data, this._currentDays);
      }
    } catch(e) {
      document.getElementById("chart-container").innerHTML =
        `<div class="placeholder" style="padding:80px 0;text-align:center;color:#e74c3c">Failed to load chart: ${e.message}</div>`;
    }
  },

  _draw(data, days) {
    if (!data || !data.length) {
      document.getElementById("chart-container").innerHTML =
        `<div class="placeholder" style="padding:80px 0;text-align:center;color:#555">No price history available.</div>`;
      document.getElementById("chart-stats").classList.add("hidden");
      return;
    }

    // Use all valid rows for warmup, then slice to the visible window
    const allRows = data.filter(d => d.avgHighPrice && d.avgLowPrice);
    let rows = days > 0 ? allRows.slice(-days) : allRows;
    if (!rows.length) return;

    const dates = rows.map(d => new Date(d.timestamp*1000));
    const highs  = rows.map(d => d.avgHighPrice);
    const lows   = rows.map(d => d.avgLowPrice);
    const mids   = rows.map(d => (d.avgHighPrice+d.avgLowPrice)/2);
    const vols     = rows.map(d => (d.highPriceVolume||0)+(d.lowPriceVolume||0));
    const avgVol30 = movingAvg(vols, 30);
    const spkX = [], spkY = [], spkC = [];
    vols.forEach((v, i) => {
      const avg = avgVol30[i] || 1;
      if (avg <= 0 || v <= 0) return;
      const ratio = v / avg;
      if (ratio < 1.5) return;
      spkX.push(dates[i]);
      spkY.push(v);
      spkC.push(ratio >= 3.0 ? "rgba(231,76,60,0.9)" :
                ratio >= 2.0 ? "rgba(243,156,18,0.9)" :
                               "rgba(155,89,182,0.8)");
    });
    const ma30 = movingAvg(mids, 30);
    const ma90 = movingAvg(mids, 90);
    // Compute RSI over full dataset so the warmup period is offscreen,
    // then slice to match the visible window — eliminates the leading null gap.
    const allMids   = allRows.map(d => (d.avgHighPrice + d.avgLowPrice) / 2);
    const rsiOffset = allRows.length - rows.length;
    const rsi       = calcRSI(allMids, 14).slice(rsiOffset);

    const traces = [
      { x:dates, y:highs, name:"High", line:{color:"rgba(93,173,226,0.4)",width:0},
        showlegend:false, hovertemplate:"High: %{y:,.0f}<extra></extra>" },
      { x:dates, y:lows,  name:"Range", fill:"tonexty",
        fillcolor:"rgba(93,173,226,0.15)", line:{color:"rgba(93,173,226,0.4)",width:0},
        hovertemplate:"Low: %{y:,.0f}<extra></extra>" },
      { x:dates, y:mids, name:"Mid",  line:{color:"#5dade2",width:1.5},
        hovertemplate:"Mid: %{y:,.0f}<extra></extra>" },
      { x:dates, y:ma30, name:"MA30", line:{color:"#f39c12",width:1.5,dash:"dash"},
        hovertemplate:"MA30: %{y:,.0f}<extra></extra>" },
      { x:dates, y:ma90, name:"MA90", line:{color:"#e74c3c",width:1.5,dash:"dash"},
        hovertemplate:"MA90: %{y:,.0f}<extra></extra>" },
      { x:dates, y:vols, name:"Volume", type:"scatter", mode:"lines",
        fill:"tozeroy", fillcolor:"rgba(93,173,226,0.25)",
        line:{color:"rgba(93,173,226,0.4)", width:0.5},
        yaxis:"y2", hovertemplate:"Vol: %{y:,.0f}<extra></extra>" },
      { x:spkX, y:spkY, name:"Vol Spike", type:"scatter", mode:"markers",
        marker:{color:spkC, size:7, symbol:"circle"},
        yaxis:"y2", hovertemplate:"Spike: %{y:,.0f}<extra></extra>" },
      { x:dates, y:rsi, name:"RSI", line:{color:"#e67e22",width:1.5}, yaxis:"y3",
        hovertemplate:"RSI: %{y:.1f}<extra></extra>" },
      { x:[dates[0],dates.at(-1)], y:[70,70], line:{color:"#e74c3c",dash:"dot",width:0.8},
        yaxis:"y3", showlegend:false, hoverinfo:"skip", mode:"lines" },
      { x:[dates[0],dates.at(-1)], y:[30,30], line:{color:"#2ecc71",dash:"dot",width:0.8},
        yaxis:"y3", showlegend:false, hoverinfo:"skip", mode:"lines" },
    ];

    const layout = {
      paper_bgcolor:"#1a1a2e", plot_bgcolor:"#0f3460",
      font:{ color:"white", size:11, family:"Segoe UI,sans-serif" },
      hovermode:"x unified",
      hoverlabel:{ bgcolor:"#0a1428", bordercolor:"#5dade2", font:{color:"white",size:11} },
      legend:{ bgcolor:"#0d1b2a", bordercolor:"#333", borderwidth:1, x:0.01, y:0.99 },
      xaxis:  { gridcolor:"#333", linecolor:"#444", showgrid:true, domain:[0,1] },
      yaxis:  { gridcolor:"#333", linecolor:"#444", title:"Price (gp)", domain:[0.35,1.0],
                tickformat:",.0f", automargin:true },
      yaxis2: { gridcolor:"#2a2a2a", linecolor:"#444", title:"Volume",  domain:[0.18,0.33],
                automargin:true },
      yaxis3: { gridcolor:"#2a2a2a", linecolor:"#444", title:"RSI",     domain:[0,0.16],
                range:[0,100], automargin:true },
      margin: { l:70, r:20, t:40, b:40 },
    };

    Plotly.react("chart-container", traces, layout, {responsive:true, displayModeBar:false});
    requestAnimationFrame(() => Plotly.Plots.resize("chart-container"));
    this._updateStats(rows, false);
  },

  async _loadAndDrawIntraday(itemId) {
    try {
      const data = await api(`/api/items/${itemId}/intraday`);
      this._currentIntraday = data;
      this._drawIntraday(data);
    } catch(e) {
      document.getElementById("chart-container").innerHTML =
        `<div class="placeholder" style="padding:80px 0;text-align:center;color:#e74c3c">Failed to load intraday: ${e.message}</div>`;
      document.getElementById("chart-stats").classList.add("hidden");
    }
  },

  _drawIntraday(data) {
    const ts = (data.timeseries || []).filter(d => d.avgHighPrice && d.avgLowPrice);
    if (!ts.length) {
      document.getElementById("chart-container").innerHTML =
        `<div class="placeholder" style="padding:80px 0;text-align:center;color:#555">No intraday data available.</div>`;
      document.getElementById("chart-stats").classList.add("hidden");
      return;
    }

    const dates = ts.map(d => new Date(d.timestamp*1000));
    const highs  = ts.map(d => d.avgHighPrice);
    const lows   = ts.map(d => d.avgLowPrice);
    const vols     = ts.map(d => (d.highPriceVolume||0)+(d.lowPriceVolume||0));
    const avgVolId = movingAvg(vols, 30);
    const ispkX = [], ispkY = [], ispkC = [];
    vols.forEach((v, i) => {
      const avg = avgVolId[i] || 1;
      if (avg <= 0 || v <= 0) return;
      const ratio = v / avg;
      if (ratio < 1.5) return;
      ispkX.push(dates[i]);
      ispkY.push(v);
      ispkC.push(ratio >= 3.0 ? "rgba(231,76,60,0.9)" :
                 ratio >= 2.0 ? "rgba(243,156,18,0.9)" :
                                "rgba(155,89,182,0.8)");
    });

    const traces = [
      { x:dates, y:highs, name:"Sell (high)", line:{color:"rgba(93,173,226,0.7)",width:1.5},
        hovertemplate:"Sell: %{y:,.0f}<extra></extra>" },
      { x:dates, y:lows, name:"Buy (low)", fill:"tonexty",
        fillcolor:"rgba(93,173,226,0.12)", line:{color:"rgba(46,204,113,0.6)",width:1.5},
        hovertemplate:"Buy: %{y:,.0f}<extra></extra>" },
      { x:dates, y:vols, name:"Volume", type:"scatter", mode:"lines",
        fill:"tozeroy", fillcolor:"rgba(93,173,226,0.25)",
        line:{color:"rgba(93,173,226,0.4)", width:0.5},
        yaxis:"y2", hovertemplate:"Vol: %{y:,.0f}<extra></extra>" },
      { x:ispkX, y:ispkY, name:"Vol Spike", type:"scatter", mode:"markers",
        marker:{color:ispkC, size:7, symbol:"circle"},
        yaxis:"y2", hovertemplate:"Spike: %{y:,.0f}<extra></extra>" },
    ];

    const layout = {
      paper_bgcolor:"#1a1a2e", plot_bgcolor:"#0f3460",
      font:{ color:"white", size:11, family:"Segoe UI,sans-serif" },
      hovermode:"x unified",
      hoverlabel:{ bgcolor:"#0a1428", bordercolor:"#5dade2", font:{color:"white",size:11} },
      legend:{ bgcolor:"#0d1b2a", bordercolor:"#333", borderwidth:1, x:0.01, y:0.99 },
      xaxis:  { gridcolor:"#333", linecolor:"#444", showgrid:true, domain:[0,1] },
      yaxis:  { gridcolor:"#333", linecolor:"#444", title:"Price (gp)", domain:[0.3,1.0],
                tickformat:",.0f", automargin:true },
      yaxis2: { gridcolor:"#2a2a2a", linecolor:"#444", title:"Volume", domain:[0,0.27],
                automargin:true },
      margin: { l:70, r:20, t:40, b:40 },
    };

    Plotly.react("chart-container", traces, layout, {responsive:true, displayModeBar:false});
    requestAnimationFrame(() => Plotly.Plots.resize("chart-container"));
    this._updateStats(ts, true);
  },

  _updateStats(rows, intraday) {
    const el = document.getElementById("chart-stats");
    if (!el || !rows || !rows.length) { if (el) el.classList.add("hidden"); return; }
    el.classList.remove("hidden");

    const last    = rows[rows.length - 1];
    const nowSec  = Date.now() / 1000;
    const ageMin  = Math.round((nowSec - (last.timestamp || nowSec)) / 60);
    const ageStr  = ageMin < 2    ? "just now"
                  : ageMin < 60   ? `${ageMin}m ago`
                  : `${Math.floor(ageMin/60)}h ago`;
    const buyPx   = last.avgLowPrice  || null;
    const sellPx  = last.avgHighPrice || null;

    let parts = [
      `<div class="cs-item"><span class="cs-label">Low (buy)</span><span class="cs-value">${fmtGP(buyPx)}</span></div>`,
      `<div class="cs-item"><span class="cs-label">High (sell)</span><span class="cs-value">${fmtGP(sellPx)}</span></div>`,
    ];

    if (buyPx && sellPx && buyPx > 0) {
      const sp = (sellPx - buyPx) / buyPx * 100;
      parts.push(`<div class="cs-item"><span class="cs-label">Spread</span><span class="cs-value">${fmtPct(sp)}</span></div>`);
    }

    parts.push(`<div class="cs-item"><span class="cs-label">Data age</span><span class="cs-value cs-dim">${ageStr}</span></div>`);

    if (intraday) {
      const totalVol = rows.reduce((s,r) => s + (r.highPriceVolume||0) + (r.lowPriceVolume||0), 0);
      parts.push(`<div class="cs-item"><span class="cs-label">Vol (24h)</span><span class="cs-value">${totalVol.toLocaleString()}</span></div>`);
    } else {
      const mids = rows.map(r => (r.avgHighPrice + r.avgLowPrice) / 2);
      if (mids.length >= 7) {
        const linSlope = arr => {
          if (arr.length < 2) return 0;
          const n = arr.length, xBar = (n-1)/2;
          const yBar = arr.reduce((a,b)=>a+b,0)/n;
          let num=0, den=0;
          arr.forEach((y,x) => { num+=(x-xBar)*(y-yBar); den+=(x-xBar)**2; });
          return den ? (num/den)/yBar*100 : 0;
        };
        const sl7  = linSlope(mids.slice(-7));
        const sl30 = linSlope(mids.slice(-30));
        const sl90 = linSlope(mids.slice(-90));
        const rsiArr = calcRSI(mids, 14);
        const rsiVal = rsiArr[rsiArr.length-1];
        const chg1d = mids.length >= 2 ? (mids[mids.length-1]-mids[mids.length-2])/mids[mids.length-2]*100 : null;
        if (chg1d != null) parts.push(`<div class="cs-item"><span class="cs-label">1d Change</span><span class="cs-value" style="color:${changeColor(chg1d)}">${fmtPct(chg1d)}</span></div>`);
        parts.push(`<div class="cs-item"><span class="cs-label">7d Slope</span><span class="cs-value" style="color:${slopeColor(sl7)}">${fmtPct(sl7)}</span></div>`);
        parts.push(`<div class="cs-item"><span class="cs-label">30d Slope</span><span class="cs-value" style="color:${slopeColor(sl30)}">${fmtPct(sl30)}</span></div>`);
        parts.push(`<div class="cs-item"><span class="cs-label">90d Slope</span><span class="cs-value" style="color:${slopeColor(sl90)}">${fmtPct(sl90)}</span></div>`);
        if (rsiVal != null)
          parts.push(`<div class="cs-item"><span class="cs-label">RSI (14)</span><span class="cs-value" style="color:${rsiColor(rsiVal)}">${rsiVal.toFixed(0)}</span></div>`);
      }
      const avgVol = Math.round(rows.reduce((s,r) => s+(r.highPriceVolume||0)+(r.lowPriceVolume||0),0) / rows.length);
      const lastVol = (rows[rows.length-1].highPriceVolume||0)+(rows[rows.length-1].lowPriceVolume||0);
      if (avgVol > 0 && lastVol > 0) {
        const spikeRatio = lastVol / avgVol;
        if (spikeRatio >= 1.5) {
          const spColor = spikeRatio >= 3.0 ? "#e74c3c" : spikeRatio >= 2.0 ? "#f39c12" : "#9b59b6";
          parts.push(`<div class="cs-item"><span class="cs-label">Vol Spike</span><span class="cs-value" style="color:${spColor}">${spikeRatio.toFixed(1)}× avg</span></div>`);
        }
      }
      parts.push(`<div class="cs-item"><span class="cs-label">Avg Vol/day</span><span class="cs-value">${avgVol.toLocaleString()}</span></div>`);
    }

    el.innerHTML = parts.join("");
  },
};

// Range buttons
document.querySelectorAll(".btn-range").forEach(btn => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".btn-range").forEach(b=>b.classList.remove("active"));
    btn.classList.add("active");
    Charts._currentDays = +btn.dataset.days;
    if (Charts._currentDays === 1) {
      if (Charts._currentId) Charts._loadAndDrawIntraday(Charts._currentId);
    } else {
      if (Charts._currentData) Charts._draw(Charts._currentData, Charts._currentDays);
    }
  });
});

// Chart search autocomplete
setupAutocomplete(
  document.getElementById("chart-search"),
  document.getElementById("chart-dropdown"),
  async (q) => api(`/api/items/search?q=${encodeURIComponent(q)}`),
  (item) => Charts.loadItem(item.id, item.name)
);

// ═══════════════════════════════════════════════════
// WATCHLIST
// ═══════════════════════════════════════════════════
const Watchlist = {
  _selectedId: null,
  _data: [],

  async load() {
    try {
      this._data = await api("/api/watchlist");
      this._render();
    } catch(e) { console.error("Watchlist load:", e); }
  },

  _renderSummary() {
    const el = document.getElementById("wl-summary");
    if (!el) return;
    const pos = this._data.filter(r => r.buy_price != null && r.quantity != null && r.buy_price > 0 && r.quantity > 0);
    if (!pos.length) { el.classList.add("hidden"); return; }
    const invested = pos.reduce((s,r) => s + r.buy_price * r.quantity, 0);
    const pnlGp    = pos.reduce((s,r) => s + (r.pnl_gp || 0), 0);
    const curVal   = invested + pnlGp;
    const pnlPct   = invested > 0 ? pnlGp / invested * 100 : 0;
    const pnlColor = pnlGp >= 0 ? "var(--green)" : "var(--red)";
    el.classList.remove("hidden");
    el.innerHTML = `
      <div><div class="wl-sum-label">Positions</div><div class="wl-sum-val">${pos.length}</div></div>
      <div><div class="wl-sum-label">Total Invested</div><div class="wl-sum-val">${fmtGP(invested)}</div></div>
      <div><div class="wl-sum-label">Current Value</div><div class="wl-sum-val">${fmtGP(curVal)}</div></div>
      <div><div class="wl-sum-label">Total P&amp;L</div><div class="wl-sum-val" style="color:${pnlColor}">${pnlGp>=0?"+":""}${fmtGP(pnlGp)}</div></div>
      <div><div class="wl-sum-label">P&amp;L %</div><div class="wl-sum-val" style="color:${pnlColor}">${fmtPct(pnlPct)}</div></div>`;
  },

  _render() {
    const tbody = document.getElementById("wl-tbody");
    if (!this._data.length) {
      tbody.innerHTML = `<tr><td colspan="15" class="placeholder">Add items to start tracking.</td></tr>`;
      this._renderSummary();
      return;
    }
    tbody.innerHTML = this._data.map(r => {
      const sc   = r.score||0;
      const sc_  = sc ? `<span style="color:${scoreColor(sc)};font-weight:700">${sc.toFixed(0)}</span>` : "—";
      const stc  = STRAT_COLORS[r.strategy]||"#aaa";
      const hasBP = r.buy_price != null;
      const pnlGp  = r.pnl_gp;
      const pnlPct = r.pnl_pct;
      const pnlGpStr  = pnlGp  != null ? `<span class="${pnlGp>=0?'text-green':'text-red'}">${(pnlGp<0?"-":"")+fmtGP(Math.abs(pnlGp))}</span>` : "—";
      const pnlPctStr = pnlPct != null ? `<span class="${pnlPct>=0?'text-green':'text-red'}">${fmtPct(pnlPct)}</span>` : "—";
      const wlIcon = r.icon_url ? `<img src="${r.icon_url}" width="20" height="20" style="vertical-align:middle;margin-right:5px;image-rendering:pixelated" onerror="this.style.display='none'">` : "";
      return `<tr class="${hasBP?'wl-position':''} ${r.item_id===this._selectedId?'selected':''}"
               data-id="${r.item_id}">
        <td class="td-name">${wlIcon}${escHtml(r.name||"")}</td>
        <td style="color:${stc};font-weight:700">${r.strategy||"—"}</td>
        <td>${sc_}</td>
        <td>${fmtGP(r.current_low)}</td>
        <td>${r.net_margin_pct!=null?fmtPct(r.net_margin_pct):"—"}</td>
        <td>${fmtGP(r.daily_flip_profit)}</td>
        <td style="color:${changeColor(r.change_1d)}">${r.change_1d!=null?fmtPct(r.change_1d):"—"}</td>
        <td style="color:${changeColor(r.change_30d)}">${r.change_30d!=null?fmtPct(r.change_30d):"—"}</td>
        <td style="color:${rsiColor(r.rsi)}">${r.rsi!=null?r.rsi.toFixed(0):"—"}</td>
        <td>${r.avg_daily_vol!=null?Math.round(r.avg_daily_vol).toLocaleString():"—"}</td>
        <td>${r.buy_price!=null?r.buy_price.toLocaleString():"—"}</td>
        <td>${r.quantity!=null?r.quantity.toLocaleString():"—"}</td>
        <td>${pnlGpStr}</td>
        <td>${pnlPctStr}</td>
        <td><button class="btn-sm btn-danger" onclick="Watchlist._quickRemove(${r.item_id})">✕</button></td>
      </tr>`;
    }).join("");

    tbody.querySelectorAll("tr[data-id]").forEach(tr => {
      tr.addEventListener("click", (e) => {
        if (e.target.tagName === "BUTTON") return;
        this._selectRow(+tr.dataset.id);
      });
      tr.addEventListener("dblclick", () => {
        const r = this._data.find(x => x.item_id === +tr.dataset.id);
        if (r) { Charts.loadItem(r.item_id, r.name); switchTab("charts"); }
      });
    });

    // Sort headers
    document.querySelectorAll("#wl-table th[data-col]").forEach(th => {
      th.onclick = () => {
        const col = th.dataset.col;
        this._data.sort((a,b) => (b[col]??0)-(a[col]??0));
        this._render();
      };
    });

    this._renderSummary();
  },

  _selectRow(id) {
    this._selectedId = id;
    const r = this._data.find(x => x.item_id===id);
    if (!r) return;
    document.getElementById("wl-sel-name").textContent = `Selected: ${r.name}`;
    document.getElementById("wl-edit-buy").value = r.buy_price ?? "";
    document.getElementById("wl-edit-qty").value = r.quantity  ?? "";
    document.getElementById("wl-action-bar").classList.remove("hidden");
    this._render();
  },

  async addWatch() {
    const id = _resolveWLSearch();
    if (!id) return;
    await api("/api/watchlist", {method:"POST",
      headers:{"Content-Type":"application/json"},
      body: JSON.stringify({item_id:id})});
    document.getElementById("wl-status").textContent = "Added.";
    const inp = document.getElementById("wl-search");
    inp.value = ""; delete inp.dataset.id;
    this.load();
  },

  async addPosition() {
    const id = _resolveWLSearch();
    if (!id) return;
    const bp  = parseGP(document.getElementById("wl-buy").value);
    const qty = parseGP(document.getElementById("wl-qty").value);
    await api("/api/watchlist", {method:"POST",
      headers:{"Content-Type":"application/json"},
      body: JSON.stringify({item_id:id, buy_price:bp, quantity:qty})});
    document.getElementById("wl-status").textContent = "Position logged.";
    const inp = document.getElementById("wl-search");
    inp.value = ""; delete inp.dataset.id;
    document.getElementById("wl-buy").value = "";
    document.getElementById("wl-qty").value = "";
    this.load();
  },

  async updateSelected() {
    if (!this._selectedId) return;
    const bp  = parseGP(document.getElementById("wl-edit-buy").value);
    const qty = parseGP(document.getElementById("wl-edit-qty").value);
    await api(`/api/watchlist/${this._selectedId}`, {method:"PUT",
      headers:{"Content-Type":"application/json"},
      body: JSON.stringify({item_id:this._selectedId, buy_price:bp, quantity:qty})});
    this.load();
  },

  async removeSelected() {
    if (!this._selectedId) return;
    await api(`/api/watchlist/${this._selectedId}`, {method:"DELETE"});
    this._selectedId = null;
    document.getElementById("wl-action-bar").classList.add("hidden");
    this.load();
  },

  async _quickRemove(id) {
    await api(`/api/watchlist/${id}`, {method:"DELETE"});
    if (this._selectedId===id) {
      this._selectedId=null;
      document.getElementById("wl-action-bar").classList.add("hidden");
    }
    this.load();
  },

  chartSelected() {
    if (!this._selectedId) return;
    const r = this._data.find(x=>x.item_id===this._selectedId);
    if (r) { Charts.loadItem(r.item_id, r.name); switchTab("charts"); }
  },
};

// Watchlist autocomplete
const _wlMatches = [];
setupAutocomplete(
  document.getElementById("wl-search"),
  document.getElementById("wl-dropdown"),
  async (q) => api(`/api/items/search?q=${encodeURIComponent(q)}`),
  (item) => {
    _wlMatches.length = 0;
    _wlMatches.push(item);
    document.getElementById("wl-search").value = item.name;
    document.getElementById("wl-search").dataset.id = item.id;
  }
);

function _resolveWLSearch() {
  const input = document.getElementById("wl-search");
  const id = +input.dataset.id;
  if (!id) {
    document.getElementById("wl-status").textContent = "Select an item from the dropdown.";
    return null;
  }
  return id;
}

// ═══════════════════════════════════════════════════
// RECOMMENDATIONS
// ═══════════════════════════════════════════════════
const Recs = {
  _view: "FLIP",
  _loaded: false,

  async load() {
    this._loaded = true;
    this._fetchAndRender();
  },

  switchView(view) {
    this._view = view;
    document.querySelectorAll(".rec-tab").forEach(b =>
      b.classList.toggle("active", b.dataset.view === view));
    this._fetchAndRender();
  },

  async _fetchAndRender() {
    const apiView = this._view === "price" ? "price" : "strategy";
    try {
      const data = await api(`/api/recommendations?view=${apiView}`);
      if (this._view === "price") {
        this._renderSections(data.sections);
      } else {
        const section = data.sections.find(s => s.key === this._view);
        this._renderStrategy(section);
      }
    } catch(e) { console.error("Recs load:", e); }
  },

  _renderStrategy(section) {
    const items = section?.items || [];
    document.getElementById("rec-count").textContent = items.length ? `${items.length} items` : "";
    const el = document.getElementById("rec-sections");
    if (!items.length) {
      el.innerHTML = `<div class="placeholder">No opportunities in this category. Press "Score All Items" first.</div>`;
      return;
    }
    el.innerHTML = `<div class="rec-cards">${items.map(i => this._cardHtml(i)).join("")}</div>`;
    this._wireCards(el);
  },

  _renderSections(sections) {
    const total = sections.reduce((s, sec) => s + sec.items.length, 0);
    document.getElementById("rec-count").textContent = total ? `${total} items` : "";
    const el = document.getElementById("rec-sections");
    if (!sections.length) {
      el.innerHTML = `<div class="placeholder">Press "Score All Items" first.</div>`;
      return;
    }
    el.innerHTML = sections.map(sec => {
      const cardsHtml = sec.items.length
        ? sec.items.map(i => this._cardHtml(i)).join("")
        : `<span class="dim-text">No items in this category.</span>`;
      return `<div class="rec-section">
        <div class="rec-section-header">
          <span class="rec-section-title" style="color:${sec.color}">${escHtml(sec.title)}</span>
          ${sec.subtitle ? `<span class="rec-section-sub">— ${escHtml(sec.subtitle)}</span>` : ""}
        </div>
        <div class="rec-cards">${cardsHtml}</div>
      </div>`;
    }).join("");
    this._wireCards(el);
  },

  _wireCards(el) {
    el.querySelectorAll(".rec-card[data-id]").forEach(card => {
      card.addEventListener("click", (e) => {
        if (e.target.classList.contains("rc-toggle")) return;
        Charts.loadItem(+card.dataset.id, card.dataset.name);
        switchTab("charts");
      });
    });
    el.querySelectorAll(".rc-toggle").forEach(btn => {
      btn.addEventListener("click", () => {
        const detail = btn.previousElementSibling;
        const open = detail.style.display === "block";
        detail.style.display = open ? "none" : "block";
        btn.textContent = open ? "▼ Details" : "▲ Hide";
      });
    });
  },

  _cardHtml(item) {
    const sc = item.score || 0;
    const strat = item.strategy || "";
    const stratColor = STRAT_COLORS[strat] || "#aaa";
    const news = item.news_signals?.length ? `<span class="news-star">★</span>` : "";
    const rcIcon = item.icon_url ? `<img src="${item.icon_url}" width="24" height="24" style="vertical-align:middle;margin-right:6px;image-rendering:pixelated" onerror="this.style.display='none'">` : "";
    return `<div class="rec-card${item.news_signals?.length ? ' has-news' : ''}"
             data-id="${item.item_id}" data-name="${escHtml(item.name || '')}">
      <div class="rc-top">
        <span class="rc-name">${rcIcon}${escHtml(item.name || "")}</span>
        <span class="rc-badge" style="background:${stratColor}22;color:${stratColor}">${strat}</span>
        ${news}
      </div>
      <div class="rc-score" style="color:${scoreColor(sc)}">Score: ${sc.toFixed(0)}</div>
      <div class="rc-price">${fmtGP(item.current_low)}</div>
      <div class="rc-summary">${escHtml(item.summary || "")}</div>
      <div class="rc-detail">${escHtml(item.detail || "")}</div>
      <button class="rc-toggle">▼ Details</button>
    </div>`;
  },
};

// Rec tab click handlers (set up once, no inline onclick needed)
document.querySelectorAll(".rec-tab").forEach(btn => {
  btn.addEventListener("click", () => Recs.switchView(btn.dataset.view));
});

// ═══════════════════════════════════════════════════
// AUTOCOMPLETE (shared)
// ═══════════════════════════════════════════════════
function setupAutocomplete(input, dropdown, fetchFn, onSelect) {
  let _timer = null;

  input.addEventListener("input", () => {
    clearTimeout(_timer);
    const q = input.value.trim();
    if (q.length < 2) { dropdown.classList.add("hidden"); return; }
    _timer = setTimeout(async () => {
      try {
        const items = await fetchFn(q);
        renderDropdown(items);
      } catch {}
    }, 200);
  });

  function renderDropdown(items) {
    if (!items.length) { dropdown.classList.add("hidden"); return; }
    dropdown.innerHTML = items.map((item,i) =>
      `<div class="ac-option" data-idx="${i}">${escHtml(item.name)}</div>`
    ).join("");
    dropdown.classList.remove("hidden");
    dropdown.querySelectorAll(".ac-option").forEach((opt, i) => {
      opt.addEventListener("mousedown", (e) => {
        e.preventDefault();
        onSelect(items[i]);
        dropdown.classList.add("hidden");
      });
    });
  }

  input.addEventListener("blur", () => {
    setTimeout(() => dropdown.classList.add("hidden"), 150);
  });

  input.addEventListener("keydown", (e) => {
    if (e.key === "Escape") dropdown.classList.add("hidden");
    if (e.key === "Enter") {
      const focused = dropdown.querySelector(".ac-option.focused");
      if (focused) focused.dispatchEvent(new MouseEvent("mousedown"));
    }
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      const opts = [...dropdown.querySelectorAll(".ac-option")];
      const cur = opts.findIndex(o=>o.classList.contains("focused"));
      opts.forEach(o=>o.classList.remove("focused"));
      const next = e.key==="ArrowDown" ? Math.min(cur+1, opts.length-1)
                                        : Math.max(cur-1, 0);
      if (opts[next]) { opts[next].classList.add("focused"); opts[next].scrollIntoView({block:"nearest"}); }
      e.preventDefault();
    }
  });
}

// ═══════════════════════════════════════════════════
// SCORE REASON MODAL
// ═══════════════════════════════════════════════════
function openReason(name, score, reason) {
  document.getElementById("modal-item-name").textContent = name;
  document.getElementById("modal-score-line").textContent =
    `Final score: ${score}/100  ·  Each factor below is added to a base of 50`;

  const factors = (reason || "").split(" · ").filter(Boolean);
  let html = `<div class="modal-base">Starting score: 50</div>`;
  factors.forEach(f => {
    let cls;
    if (f.startsWith("★"))                               cls = "factor-news";
    else if (f.includes("(+"))                            cls = "factor-pos";
    else if (f.includes("(−") || f.includes("(-"))  cls = "factor-neg";
    else                                                  cls = "";
    html += `<div class="modal-factor"><span class="${cls}">${escHtml(f)}</span></div>`;
  });
  document.getElementById("modal-factors").innerHTML = html;
  document.getElementById("reason-modal").classList.remove("hidden");
}

function closeReason() {
  document.getElementById("reason-modal").classList.add("hidden");
}

function closeReasonModal(e) {
  if (e.target === e.currentTarget) closeReason();
}

// ═══════════════════════════════════════════════════
// HELPERS
// ═══════════════════════════════════════════════════
function escHtml(s) {
  return String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;")
                  .replace(/>/g,"&gt;").replace(/"/g,"&quot;");
}

function slopeColor(v) {
  if (v == null) return "#888";
  if (v > 0.05)  return "#2ecc71";
  if (v < -0.05) return "#e74c3c";
  return "#aaa";
}

function changeColor(v) {
  if (v == null) return "#888";
  if (v > 0.1)  return "#2ecc71";
  if (v < -0.1) return "#e74c3c";
  return "#aaa";
}

function rsiColor(v) {
  if (v == null) return "#888";
  if (v < 35) return "#2ecc71";
  if (v > 65) return "#e74c3c";
  return "#aaa";
}

function switchTab(name) {
  document.querySelectorAll(".tab-btn").forEach(b =>
    b.classList.toggle("active", b.dataset.tab===name));
  document.querySelectorAll(".tab-content").forEach(c =>
    c.classList.toggle("hidden", !c.id.endsWith(name)));
  if (name==="recommendations" && !Recs._loaded) Recs.load();
  if (name==="watchlist") Watchlist.load();
}

// ═══════════════════════════════════════════════════
// COLUMN HEADER TOOLTIPS
// ═══════════════════════════════════════════════════
const _tipEl = document.createElement("div");
_tipEl.id = "col-tooltip";
document.body.appendChild(_tipEl);

document.querySelectorAll("th[data-tip]").forEach(th => {
  th.addEventListener("mouseenter", (e) => {
    _tipEl.textContent = th.dataset.tip;
    _tipEl.style.display = "block";
    _positionTip(e);
  });
  th.addEventListener("mousemove", _positionTip);
  th.addEventListener("mouseleave", () => { _tipEl.style.display = "none"; });
});

function _positionTip(e) {
  const gap = 12;
  let x = e.clientX + gap, y = e.clientY + gap;
  // Keep within viewport
  if (x + _tipEl.offsetWidth  > window.innerWidth  - 8) x = e.clientX - _tipEl.offsetWidth  - gap;
  if (y + _tipEl.offsetHeight > window.innerHeight - 8) y = e.clientY - _tipEl.offsetHeight - gap;
  _tipEl.style.left = x + "px";
  _tipEl.style.top  = y + "px";
}

// ═══════════════════════════════════════════════════
// INIT
// ═══════════════════════════════════════════════════
(async function init() {
  pollStatus();
  // Load dashboard once scoring might have initial results
  setTimeout(() => Dashboard.load(), 2000);
  // Reload after auto-score fires (~5s after startup finishes)
  setTimeout(() => Dashboard.load(), 6000);
})();
