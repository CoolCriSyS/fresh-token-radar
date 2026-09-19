"use client";

import { useEffect, useMemo, useState } from "react";

// Data lives on the `data` branch (keeps scan refreshes off main so Vercel
// doesn't rebuild); fall back to the bundled copy if the remote fetch fails.
const DATA_URLS = [
  "https://raw.githubusercontent.com/CoolCriSyS/fresh-token-radar/data/web/public/data/latest.json",
  "/data/latest.json",
];
const loadData = () => {
  const attempt = (i) =>
    i >= DATA_URLS.length
      ? Promise.reject(new Error("data unavailable"))
      : fetch(DATA_URLS[i])
          .then((r) => { if (!r.ok) throw new Error("bad response"); return r.json(); })
          .catch(() => attempt(i + 1));
  return attempt(0);
};

// Compact money: 1.2M, 300K. Handles null/undefined.
const compact$ = (n) => {
  if (n == null || Number.isNaN(n)) return "—";
  const a = Math.abs(n);
  if (a >= 1e9) return "$" + (n / 1e9).toFixed(1) + "B";
  if (a >= 1e6) return "$" + (n / 1e6).toFixed(1) + "M";
  if (a >= 1e3) return "$" + (n / 1e3).toFixed(0) + "K";
  return "$" + n.toFixed(0);
};
const signed$ = (n) => (n == null ? "—" : (n < 0 ? "−" : "+") + compact$(n).slice(0));
const shortAddr = (a) => (a ? a.slice(0, 6) + "…" + a.slice(-4) : "—");
// Defense in depth: redact slur-bearing labels before render.
const cleanLabel = (s) => {
  if (!s) return "";
  const low = s.toLowerCase();
  if (low.includes("nigger") || low.includes("nigga")) return "[redacted label]";
  return s;
};
const fmtAge = (d) => (d == null ? "—" : d < 1 ? `${Math.max(1, Math.round(d * 24))}h` : `${Math.round(d)}d`);
const fmtTouch = (h) => {
  if (h == null) return "—";
  if (h < 1) return `${Math.max(1, Math.round(h * 60))}m ago`;
  if (h < 24) return `${h.toFixed(0)}h ago`;
  return `${(h / 24).toFixed(1)}d ago`;
};
const fmtPct = (p) => (p == null ? "—" : `${p >= 0 ? "+" : ""}${p.toFixed(1)}%`);

function BuyersList({ items }) {
  const rows = (items || []).slice(0, 5);
  if (rows.length === 0) return null;
  return (
    <details className="buyers">
      <summary>Top buyers ({rows.length})</summary>
      <ul>
        {rows.map((b, i) => (
          <li key={i}>
            <span className="who">
              {shortAddr(b.address)}
              {cleanLabel(b.label) && <span className="lbl">{cleanLabel(b.label)}</span>}
            </span>
            <span className="amt">{compact$(b.value_usd)}</span>
          </li>
        ))}
      </ul>
    </details>
  );
}

function HeatCard({ t, maxScore, rank }) {
  const width = maxScore > 0 ? (100 * t.heat_score / maxScore).toFixed(1) : 0;
  const ageCls = t.token_age_days < 2 ? "hot" : t.token_age_days <= 4 ? "warm" : "cool";
  return (
    <div className="card">
      <div className="top">
        <div className="sym">
          <span className="rank">#{rank}</span> {t.symbol}
          <span className="chain">{t.chain}</span>
          <span className={`accel ${ageCls}`}>{fmtAge(t.token_age_days)} old</span>
        </div>
        <div className="score-num">{t.heat_score.toFixed(1)}</div>
      </div>
      <div className="score-line">
        <div className="bar"><div className="fill g" style={{ width: `${width}%` }} /></div>
      </div>
      <div className="kvgrid">
        <div className="kv"><div className="k">Smart buyers</div><div className="v">{t.buyers}</div><div className="sub">{t.distinct_labels} cohorts</div></div>
        <div className="kv"><div className="k">First touch</div><div className="v">{fmtTouch(t.first_touch_hours_ago)}</div></div>
        <div className="kv"><div className="k">Buy volume (24h)</div><div className="v pos">{compact$(t.buy_volume_usd)}</div></div>
        <div className="kv"><div className="k">Netflow</div><div className={`v ${t.netflow_usd < 0 ? "neg" : "pos"}`}>{signed$(t.netflow_usd)}</div></div>
        <div className="kv"><div className="k">Mcap</div><div className="v">{compact$(t.market_cap)}</div><div className={`sub ${t.price_change_pct < 0 ? "neg" : "pos"}`}>{fmtPct(t.price_change_pct)} 24h</div></div>
        <div className="kv"><div className="k">Liquidity</div><div className="v">{compact$(t.liquidity_usd)}</div></div>
      </div>
      <BuyersList items={t.top_buyers} />
    </div>
  );
}

function TouchTimeline({ tokens }) {
  const rows = (tokens || [])
    .filter((t) => t.first_touch_hours_ago != null)
    .sort((a, b) => a.first_touch_hours_ago - b.first_touch_hours_ago)
    .slice(0, 12);
  if (rows.length === 0) return <div className="empty">No first-touch data in this scan.</div>;
  const maxH = Math.max(1, ...rows.map((r) => r.first_touch_hours_ago));
  return (
    <div className="timeline">
      {rows.map((t, i) => (
        <div className="tl-row" key={i}>
          <div className="tl-sym">{t.symbol}<span className="chain">{t.chain}</span></div>
          <div className="tl-track">
            <div className="tl-dot" style={{ left: `${(100 * t.first_touch_hours_ago / maxH).toFixed(1)}%` }} />
          </div>
          <div className="tl-when">{fmtTouch(t.first_touch_hours_ago)}</div>
        </div>
      ))}
    </div>
  );
}

export default function Page() {
  const [data, setData] = useState(null);
  const [loadError, setLoadError] = useState(false);
  const [chainFilter, setChainFilter] = useState("all");

  useEffect(() => {
    loadData()
      .then(setData)
      .catch(() => setLoadError(true));
  }, []);

  const tokens = useMemo(
    () => (data ? [...(data.tokens || [])].sort((a, b) => b.heat_score - a.heat_score) : []),
    [data]
  );
  const chains = useMemo(() => [...new Set(tokens.map((t) => t.chain))].sort(), [tokens]);
  const filtered = useMemo(
    () => (chainFilter === "all" ? tokens : tokens.filter((t) => t.chain === chainFilter)),
    [tokens, chainFilter]
  );
  const maxScore = useMemo(() => Math.max(1, ...filtered.map((t) => t.heat_score || 0)), [filtered]);

  if (loadError) return <div className="wrap"><div className="empty">Could not load scan data. Check back after the next scheduled scan.</div></div>;
  if (!data) return <div className="wrap"><div className="empty">Loading scan data…</div></div>;

  const scannedAt = data.scanned_at ? new Date(data.scanned_at).toLocaleString() : "—";

  return (
    <div className="wrap">
      <div className="hero">
        <span className="kicker">Nansen Meridian Buildathon</span>
        <h1>Fresh Token <span className="accent">Radar</span></h1>
        <p>
          Tokens in their <strong>first smart-money hour</strong> — coins no more than
          7 days old where Nansen-labeled smart wallets are placing early bets. Meme
          season moves in hours, not quarters: this board ranks fresh launches by how
          hard and how recently smart money piled in. Two or more independent buyers
          required — one wallet aping in is noise, a crowd is a signal.
        </p>
      </div>

      <div className="stats">
        <div className="stat"><div className="label">Fresh signals</div><div className="value green">{tokens.length}</div></div>
        <div className="stat"><div className="label">Nansen API calls</div><div className="value">{data.api_calls ?? "—"}</div></div>
        <div className="stat"><div className="label">Last scan</div><div className="value" style={{ fontSize: 15 }}>{scannedAt}</div></div>
      </div>

      <div className="chips">
        {["all", ...chains].map((c) => (
          <button
            key={c}
            className={`chip ${chainFilter === c ? "on" : ""}`}
            onClick={() => setChainFilter(c)}
          >
            {c === "all" ? "All chains" : c}
          </button>
        ))}
      </div>

      <div className="section-head">
        <h2><span className="accent-g">Fresh Heat</span></h2>
        <p>
          Ranked by heat score = buyer breadth × buy volume × netflow positivity ×
          first-touch recency × token youth. Younger tokens and fresher first touches
          run hotter.
        </p>
      </div>
      <div className="cards">
        {filtered.map((t, i) => <HeatCard key={i} t={t} maxScore={maxScore} rank={i + 1} />)}
      </div>
      {filtered.length === 0 && <div className="empty">No fresh signals in this scan{chainFilter !== "all" ? ` for ${chainFilter}` : ""}.</div>}

      <div className="section-head">
        <h2><span className="accent-b">First Touch Timeline</span></h2>
        <p>
          When smart money first touched each token, most recent first. Dots near
          the left edge are the freshest bets on the board.
        </p>
      </div>
      <TouchTimeline tokens={tokens} />

      <div className="method">
        <h2>How the signals are computed</h2>
        <ol>
          <li><code>token_discovery_screener</code> (traderType=smart money, age ≤ 7 days, 24h window, sorted by smart buy volume) — seeds the candidate list from the two most-bought pages.</li>
          <li><code>smart_traders_and_funds_dex_trades</code> — per-token smart buys: buyer count, distinct Nansen label cohorts, and the first smart-money touch time.</li>
          <li>Heat score = log(buyers) × log(buy volume) × netflow positivity × first-touch recency × token youth. Tokens with fewer than 2 distinct buyers are dropped.</li>
        </ol>
      </div>

      <div className="footer">
        Data via <a href="https://docs.nansen.ai" target="_blank" rel="noreferrer">Nansen API</a> ·
        Built for the Nansen Meridian Buildathon ·
        Analytical signals, not financial advice
      </div>
    </div>
  );
}
