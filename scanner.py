#!/usr/bin/env python3
"""Fresh Token Radar v0.1 — Nansen Meridian Buildathon entry #3.

Catches tokens in their first smart-money hour: young tokens (<=7 days old)
where Nansen-labeled smart traders & funds are placing early bets.

Pipeline (Nansen MCP tools):
  token_discovery_screener (traderType="sm", tokenAgeDays<=7, 24h window,
                            orderBy=buyVolume desc, pages 1-2)
    -> smart_traders_and_funds_dex_trades (per-token buys: buyer count,
       first smart-money touch time, label diversity)

Heat score = log1p(buyers) x log1p(buy volume) x netflow positivity
           x first-touch recency x token youth. Requires >=2 distinct
buyers so a single wallet aping in doesn't light up the board.

Usage:
  scanner.py [--tokens N] [--out report.json]

~17 API calls per scan (2 screener pages + up to 15 per-token buy lookups).
"""
import argparse
import datetime
import json
import math
import os
import re
import sys
import urllib.request
from collections import defaultdict

sys.path.insert(0, "/opt/hatch/skills/skill-creator/bin")
try:
    from dynamic_credentials import (  # noqa: E402
        add_surrogate_to_request,
        read_response_body,
    )
    HAS_SURROGATE = True
except ImportError:
    HAS_SURROGATE = False

ENDPOINT = "https://mcp.nansen.ai/ra/mcp"
CREDENTIAL = "custom.nansen"
ALLOWED_HOSTS = ("mcp.nansen.ai",)

CALL_COUNT = 0

WRAPPED_DENY = {"WETH", "WBTC", "WSOL", "WSTETH", "WEETH", "WBETH", "STETH", "WBNB"}


def _post(payload):
    req = urllib.request.Request(
        ENDPOINT,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        },
    )
    api_key = os.environ.get("NANSEN" + "_API_KEY")
    if api_key:
        req.add_header("NANSEN-API-KEY", api_key)
    elif HAS_SURROGATE:
        add_surrogate_to_request(req, CREDENTIAL, allowed_hosts=ALLOWED_HOSTS)
    else:
        raise RuntimeError("No Nansen API key: set NANSEN_API_KEY or run where the credential helper exists.")
    with urllib.request.urlopen(req, timeout=120) as resp:
        if HAS_SURROGATE:
            body = read_response_body(resp).decode("utf-8", errors="replace")
        else:
            body = resp.read().decode("utf-8", errors="replace")
    lines = [l for l in body.splitlines() if l.strip().startswith("data:")]
    if lines:
        body = lines[-1][len("data:"):].strip()
    return json.loads(body)


def rpc(method, params=None):
    global CALL_COUNT
    CALL_COUNT += 1
    payload = {"jsonrpc": "2.0", "id": CALL_COUNT, "method": method}
    if params is not None:
        payload["params"] = params
    data = _post(payload)
    contents = data.get("result", {}).get("content", [])
    texts = [c.get("text", "") for c in contents if c.get("type") == "text"]
    return "\n".join(texts)


def parse_tables(text):
    tables, current = [], []
    for line in text.splitlines():
        if line.strip().startswith("|"):
            current.append(line)
        elif current:
            tables.append(current)
            current = []
    if current:
        tables.append(current)
    out = []
    for t in tables:
        if len(t) < 3:
            continue
        headers = [h.strip() for h in t[0].strip().strip("|").split("|")]
        for line in t[2:]:
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) == len(headers):
                out.append(dict(zip(headers, cells)))
    return out


def parse_money(s):
    if not s:
        return 0.0
    s = s.strip().replace(",", "").replace("$", "")
    if s in ("N/A", "-", "--", ""):
        return 0.0
    m = re.fullmatch(r"(-?[\d.]+)\s*([kmbKMB])?", s)
    if not m:
        try:
            return float(s)
        except ValueError:
            return 0.0
    val = float(m.group(1))
    mult = {"k": 1e3, "m": 1e6, "b": 1e9}.get((m.group(2) or "").lower(), 1)
    return val * mult


def parse_pct(s):
    if not s:
        return None
    s = s.strip().replace("%", "")
    if s in ("N/A", "-", "--", "", "nan"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def parse_time(s):
    try:
        return datetime.datetime.strptime(s.strip(), "%Y-%m-%d %H:%M:%S")
    except (ValueError, AttributeError):
        return None


def clean_label(s):
    """Redact labels containing slurs/profanity before they reach public output."""
    if not s:
        return ""
    low = s.lower()
    if "nigger" in low or "nigga" in low:
        return "[redacted label]"
    return s


def discover(page):
    """Young tokens (<=7d) with the most smart-money buy volume, 24h window."""
    text = rpc("tools/call", {
        "name": "token_discovery_screener",
        "arguments": {"request": {
            "chains": ["solana", "base", "ethereum", "bnb"],
            "timeframe": "24h",
            "traderType": "sm",
            "tokenAgeDays": {"to": 7},
            "includeStablecoins": False,
            "includeNativeTokens": False,
            "orderBy": "buyVolume",
            "orderByDirection": "desc",
            "page": page,
        }},
    })
    rows = parse_tables(text)
    tokens = []
    for r in rows:
        symbol = r.get("Symbol", "").replace("🌱", "").strip()
        if not symbol or symbol.upper() in WRAPPED_DENY:
            continue
        tokens.append({
            "address": r.get("Token Address", ""),
            "symbol": symbol,
            "chain": r.get("Chain", ""),
            "token_age_days": parse_money(r.get("Token Age (Days)")),
            "market_cap": parse_money(r.get("Market Cap")),
            "liquidity": parse_money(r.get("DEX Liquidity")),
            "price_usd": parse_money(r.get("Price USD")),
            "price_change_pct": parse_pct(r.get("Price Change")),
            "buy_volume": parse_money(r.get("Buy USD Volume")),
            "sell_volume": parse_money(r.get("Sell USD Volume")),
            "netflow": parse_money(r.get("Net Flow USD")),
        })
    return tokens


def dex_buys(symbol, chain):
    text = rpc("tools/call", {
        "name": "smart_traders_and_funds_dex_trades",
        "arguments": {"request": {
            "chains": [chain],
            "tokenBoughtSymbol": symbol,
        }},
    })
    trades = []
    for r in parse_tables(text):
        trades.append({
            "trader": r.get("Trader", ""),
            "label": clean_label(r.get("Trader Label", "")),
            "time": parse_time(r.get("Time", "")),
            "value_usd": parse_money(r.get("Trade Value")),
        })
    return [t for t in trades if t["trader"]]


def heat_signals(candidates, n_tokens):
    now = datetime.datetime.now()
    signals = []
    for tok in candidates[:n_tokens]:
        if not tok["symbol"] or not tok["chain"]:
            continue
        trades = dex_buys(tok["symbol"], tok["chain"])
        buyers = {}
        for t in trades:
            b = buyers.setdefault(t["trader"], {"label": t["label"], "value": 0.0, "times": []})
            b["value"] += t["value_usd"]
            if t["time"]:
                b["times"].append(t["time"])
        n = len(buyers)
        if n < 2:
            continue  # single-wallet noise is not a signal
        labels = {b["label"] for b in buyers.values() if b["label"]}
        all_times = [tm for b in buyers.values() for tm in b["times"]]
        first_touch = min(all_times) if all_times else None
        hours_ago = ((now - first_touch).total_seconds() / 3600) if first_touch else None
        buy_vol = tok["buy_volume"]
        breadth = math.log1p(n)
        conviction = math.log1p(buy_vol)
        ratio = (tok["netflow"] / buy_vol) if buy_vol > 0 else 0
        netflow_pos = 0.5 + 0.5 * max(-1.0, min(1.0, ratio))
        recency = 1.0 / (1.0 + (hours_ago or 48) / 12.0)
        youth = 1.0 + (7.0 - min(tok["token_age_days"], 7.0)) / 7.0
        score = breadth * conviction * netflow_pos * recency * youth
        top_buyers = sorted(buyers.items(), key=lambda kv: kv[1]["value"], reverse=True)[:5]
        signals.append({
            "symbol": tok["symbol"],
            "chain": tok["chain"],
            "address": tok["address"],
            "token_age_days": round(tok["token_age_days"], 1),
            "first_touch": first_touch.strftime("%Y-%m-%d %H:%M:%S") if first_touch else None,
            "first_touch_hours_ago": round(hours_ago, 1) if hours_ago is not None else None,
            "buyers": n,
            "distinct_labels": len(labels),
            "buy_volume_usd": round(buy_vol, 2),
            "sell_volume_usd": round(tok["sell_volume"], 2),
            "netflow_usd": round(tok["netflow"], 2),
            "market_cap": round(tok["market_cap"], 2),
            "liquidity_usd": round(tok["liquidity"], 2),
            "price_usd": tok["price_usd"],
            "price_change_pct": tok["price_change_pct"],
            "heat_score": round(score, 3),
            "top_buyers": [
                {"address": a, "label": b["label"], "value_usd": round(b["value"], 2)}
                for a, b in top_buyers
            ],
        })
    signals.sort(key=lambda s: s["heat_score"], reverse=True)
    return signals


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tokens", type=int, default=15)
    ap.add_argument("--out", default="web/public/data/latest.json")
    args = ap.parse_args()

    candidates = discover(1) + discover(2)
    # dedupe by (chain, address); page 1 wins ties
    seen, uniq = set(), []
    for t in candidates:
        key = (t["chain"], t["address"])
        if key not in seen:
            seen.add(key)
            uniq.append(t)
    signals = heat_signals(uniq, args.tokens)

    report = {
        "scanned_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "api_calls": CALL_COUNT,
        "tokens": signals,
    }
    with open(args.out, "w") as f:
        json.dump(report, f, indent=2)
    top = signals[0]["symbol"] if signals else "none"
    print(f"calls={CALL_COUNT} candidates={len(uniq)} signals={len(signals)} top={top} -> {args.out}")


if __name__ == "__main__":
    main()
