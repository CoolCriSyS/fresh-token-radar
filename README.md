# Fresh Token Radar

Nansen Meridian Buildathon entry #3. Catches tokens in their first smart-money
hour: young tokens (≤ 7 days old) where Nansen-labeled smart traders & funds are
placing early bets — the meme-hype angle.

## How it works

`scanner.py` runs the pipeline:

1. `token_discovery_screener` — smart-money cohort, token age ≤ 7 days, 24h
   window, sorted by smart buy volume (2 pages).
2. `smart_traders_and_funds_dex_trades` — per-token smart buys: buyer count,
   distinct Nansen label cohorts, first smart-money touch time.

Heat score = log(buyers) × log(buy volume) × netflow positivity × first-touch
recency × token youth. Requires ≥ 2 distinct buyers.

~17 Nansen API calls per scan. A GitHub Actions workflow (`scan.yml`) runs the
scan every 6 hours and commits fresh data.

## Setup

Add `NANSEN_API_KEY` to the repo's Actions secrets (Settings → Secrets and
variables → Actions), or set it as an env var for local runs:

```bash
python3 scanner.py --out web/public/data/latest.json
```

## Dashboard

`web/` is a Next.js 15 static dashboard (dark fintech theme) that reads
`web/public/data/latest.json`:

```bash
cd web && npm install && npm run build
```
