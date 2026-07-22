# special-spoon — weekly stock selector

Screens a universe of **small/mid-cap US tech stocks** ($300M–$20B) weekly and ranks
them by a weighted composite of:

| Signal | Base weight | Source (all free) |
|---|---|---|
| Technicals (trend, momentum, RSI, breakout, volume) | 0.23 | Yahoo Finance via `yfinance` |
| Fundamentals (P/E, growth, debt, ROE, margins) | 0.23 | Yahoo Finance via `yfinance` |
| Insider activity (net open-market Form 4 dollars) | 0.15 | SEC EDGAR issuer submissions + Form 4 XML |
| Quality (accrual gap, share dilution) | 0.10 | Yahoo Finance financial fields + share history |
| Corporate events (13D/13G stakes, S-3 shelves, 8-K 4.02) | 0.09 | SEC EDGAR submissions feed |
| Filing-language stability ("lazy prices") | 0.08 | SEC EDGAR 10-Q/10-K text diff |
| Search-interest momentum (retail attention) | 0.07 | Google Trends via `pytrends` |
| Congressional trading (disclosed buys − sells) | 0.05 | Senate/House Stock Watcher |
| Macro / Fed regime | context only | FRED (`DFF`, `T10Y2Y`, `VIXCLS`) |

Weights are *base* weights: once enough graded history accumulates, the scoreboard
tilts them toward signals with demonstrated predictive power (see "Adaptive
reweighting" below).

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

### Performance scoreboard

Each weekly run also grades every past report old enough to matter (≥7 days):
the equal-weighted return of that week's top picks from report date to now,
vs QQQ and IWM, with per-report alpha and hit rate. Results land in
`reports/scoreboard.md` / `scoreboard.csv`. Once a few weeks accumulate, this
is the evidence for tuning `config/weights.yaml`. Run manually with
`python run_scoreboard.py --reports-dir reports`.

### Adaptive reweighting

The scoreboard also computes each signal's **information coefficient** (IC — the
rank correlation between the signal's scores and the returns that actually
followed) per graded report, saved to `reports/signal_ic.csv`. Once at least 6
graded reports exist, it writes `reports/adaptive_weights.yaml`: base weights
tilted toward signals with sustained positive IC. Guardrails keep it honest —
measured IC is shrunk 50% toward zero, the tilt is capped at ±50% of base weight,
and no signal can fall below 25% of its base weight (a cold streak never kills a
signal's chance to recover). The next weekly run picks up the adapted weights
automatically (`--no-adaptive` opts out).

### Backtesting

```bash
python run_backtest.py --start 2024-07-01 --end 2026-07-01 --step-weeks 4 --top-n 10
```

Walk-forward simulation: every 4 weeks, score the universe **as of that date**,
hold the top N to the next rebalance, compare against QQQ/IWM, and record each
signal's IC. Adaptive reweighting runs walk-forward too (weights at each rebalance
use only *prior* periods' ICs). Output: `output/backtest_*.md` with cumulative
performance, per-signal predictive power, and the biggest wins ("gems") and losses.

Only truly point-in-time signals participate: technical, insider, events, and
(with `--include-filing-text`, document-heavy) filing language. Fundamentals,
quality, and congress are excluded — free sources only serve *current* snapshots
for those, and backtesting them with today's data would be lookahead bias.
Results also carry survivorship bias: today's universe omits delisted names, so
absolute returns flatter; treat relative signal comparisons as the useful output.

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
  outages and may no longer be maintained. Staleness is detected (no in-window
  transactions feed-wide) and the congress signal is marked unavailable rather than
  scored as zeros; its weight redistributes and the report says so. A maintained
  free replacement source is an open v2 item.
- **yfinance is unofficial** — Yahoo can change endpoints; per-ticker failures are
  skipped and counted in the report header.
- Not investment advice; it's an automated research screen.

## v2 backlog

Reddit sentiment (OAuth app + VADER/ticker-disambiguation), FINRA short interest,
BLS/FRED hiring & supply-cost overlays, HTML report, LLM-written per-pick narratives,
response caching. Per-ticker options flow is excluded — no viable free source.
Google Trends search-interest momentum is now **implemented** as a scored signal.

### Search-interest momentum (Google Trends)

Free, no auth. For each shortlisted ticker it pulls Google Trends interest for
`"<ticker> stock"` and scores **recent-vs-baseline momentum** (last ~14 days vs the
trailing ~90). Momentum, not raw interest, is used deliberately: Trends normalizes
every request to its own peak, so raw 0-100 values aren't comparable across tickers —
a recent/baseline *ratio* is self-normalizing and comparable after ranking. It
measures retail *attention*, whose predictive sign is unproven, so it carries a small
base weight (0.07) and the adaptive-reweighting IC tracking decides its real value.
Google Trends is heavily rate-limited; requests batch 5 tickers at a time and the
signal fails soft (weight redistributes) if throttled. Because Trends data is
historical, this signal is backtest-ready — wiring it into the walk-forward loop is
a follow-up.
