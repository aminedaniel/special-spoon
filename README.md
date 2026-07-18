# special-spoon — weekly stock selector

Screens a universe of **small/mid-cap US tech stocks** ($300M–$10B) weekly and ranks
them by a weighted composite of:

| Signal | Weight | Source (all free) |
|---|---|---|
| Technicals (trend, momentum, RSI, breakout, volume) | 0.35 | Yahoo Finance via `yfinance` |
| Fundamentals (P/E, growth, debt, ROE, margins) | 0.30 | Yahoo Finance via `yfinance` |
| Insider activity (recent Form 4 filings) | 0.20 | SEC EDGAR full-text search |
| Congressional trading (disclosed buys − sells) | 0.15 | Senate/House Stock Watcher |
| Macro / Fed regime | context only | FRED (`DFF`, `T10Y2Y`, `VIXCLS`) |

The macro signal is deliberately **contextual, not weighted** — a market-wide value is
identical for every ticker and cannot change relative rankings; it renders as a
"Market regime" panel instead.

## How it works

Two-stage funnel to stay inside free-API rate limits:

1. **Stage A** — batched fundamentals + 1y price history for the whole universe,
   quality gate (cap band, extreme P/E), rank on fundamentals + technicals.
2. **Stage B** — only the top `stage_a_shortlist_size` names get the expensive
   per-ticker calls (SEC EDGAR, congressional data). Missing data never zeroes a
   score: weights renormalize over the categories actually present.

Output: `output/report_YYYY-MM-DD.md` (readable report) and
`output/rankings_YYYY-MM-DD.csv` (full scored shortlist).

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env      # then fill in:
#   FRED_API_KEY          — free key: https://fredaccount.stlouisfed.org/apikeys
#   SEC_EDGAR_USER_AGENT  — e.g. "special-spoon you@example.com" (SEC fair-access policy)
```

## Run

```bash
python run_weekly_report.py                       # full weekly run
python run_weekly_report.py --dry-run             # Stage A only, no EDGAR/congress/FRED
python run_weekly_report.py --universe my.csv     # custom watchlist (needs 'ticker' column)
python run_weekly_report.py --top-n 10 -v
```

Tuning lives in `config/weights.yaml` (weights must sum to 1.0, validated at load).

## Weekly automation

Two GitHub Actions workflows:

- `tests.yml` — pytest on every PR and push to main.
- `weekly_report.yml` — Monday 13:00 UTC: generates the report and commits it to
  `reports/` on main. Also runnable on demand from the Actions tab (workflow_dispatch).

Add two repository secrets (Settings → Secrets and variables → Actions) for full
signal coverage: `FRED_API_KEY` and `SEC_EDGAR_USER_AGENT`. Without them the run
still works but skips the insider signal and macro panel.

A weekly Claude Routine then reads the committed report and posts a summary into
chat shortly after the workflow finishes.

## Universe

`config/universe.csv` is a checked-in starter list of small/mid-cap tech names. Market
caps drift, but the pipeline re-checks **live** market cap against the configured band on
every run, so out-of-band names are gated out automatically. To rebuild the list from
exchange listings (occasional, e.g. quarterly):

```bash
python scripts/refresh_universe.py --limit 400
```

## Tests

```bash
python -m pytest tests/ -q
```

All HTTP is mocked in tests; the smoke test runs the full pipeline end-to-end against a
synthetic 5-ticker universe.

## Network requirements

A real run needs outbound HTTPS to: `query1/query2.finance.yahoo.com` + `fc.yahoo.com`
(yfinance), `efts.sec.gov` + `www.sec.gov` (EDGAR), `api.stlouisfed.org` (FRED),
`*.s3-us-west-2.amazonaws.com` (Stock Watcher data), and for universe refresh
`www.nasdaqtrader.com`. In a restricted environment (e.g. a Claude Code cloud sandbox
with a locked-down network policy) these must be allowlisted or the run degrades: every
data source fails soft, but a run with no market data cannot rank anything.

## Known caveats

- **Congressional data lag** — the STOCK Act allows 30–45 days to disclose, so that
  signal reflects trades made weeks earlier. The report footer says so.
- **Senate/House Stock Watcher availability** — these community datasets have had
  outages; if unreachable the congress signal contributes nothing (weights renormalize).
- **yfinance is unofficial** — Yahoo can change endpoints; per-ticker failures are
  skipped and counted in the report header.
- Not investment advice; it's an automated research screen.

## v2 backlog

Reddit/Google-Trends sentiment, FINRA short interest, BLS/FRED hiring & supply-cost
overlays, HTML report, LLM-written per-pick narratives, response caching, weight
backtesting. Per-ticker options flow is excluded — no viable free source.
