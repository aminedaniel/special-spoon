# special-spoon — weekly stock selector

Screens a universe of **small/mid-cap US tech stocks** ($300M–$20B) weekly and ranks
them by a weighted composite of:

| Signal | Base weight | Source (all free) |
|---|---|---|
| Earnings drift / PEAD (standardized earnings surprise) | 0.11 | Yahoo Finance earnings dates via `yfinance` |
| Technicals (12-1 momentum, trend, breakout, volume) | 0.09 | Yahoo Finance via `yfinance` |
| Fundamentals (growth, debt, ROE, margins) | 0.11 | Yahoo Finance via `yfinance` |
| Profitability (GP/assets, asset growth — Novy-Marx/CMA) | 0.07 | Yahoo Finance statements via `yfinance` |
| Insider activity (officer-weighted cluster buys, discounted sells, 90d) | 0.13 | SEC EDGAR issuer submissions + Form 4 XML |
| Stability (low beta vs QQQ + low idiosyncratic vol) | 0.07 | Yahoo Finance via `yfinance` |
| Short interest (% of float + MoM change — high/rising = bad) | 0.07 | Exchange short reports via `yfinance` |
| Quality (accrual gap, share dilution) | 0.08 | Yahoo Finance financial fields + share history |
| Valuation (P/E, P/S, EV/Sales, EV/EBITDA, PEG, P/FCF — cheaper = better) | 0.06 | Yahoo Finance via `yfinance` |
| Corporate events (13D/13G stakes, S-3 shelves, 8-K 4.02) | 0.08 | SEC EDGAR submissions feed |
| Filing-language stability ("lazy prices") | 0.08 | SEC EDGAR 10-Q/10-K text diff |
| Search-interest momentum (retail attention) | 0.05 | Google Trends via `pytrends` |
| Macro / Fed regime | context only | FRED (`DFF`, `T10Y2Y`, `VIXCLS`) |

Weights are *base* weights: once enough graded history accumulates, the scoreboard
tilts them toward signals with demonstrated predictive power (see "Adaptive
reweighting" below).

The macro signal is deliberately **contextual, not weighted** — a market-wide value is
identical for every ticker and cannot change relative rankings; it renders as a
"Market regime" panel instead. `FRED_API_KEY` is therefore genuinely optional: without
it the panel is simply omitted and *every pick is identical*. Set it only if you want
the fed-funds/curve/VIX readout printed alongside the picks.

(The one way macro could legitimately move rankings is regime-*conditional weighting* —
switching the weight vector in stressed regimes rather than adding a market-wide score.
Not implemented: regimes are rare, so a rule like that would be fitted on a handful of
effective observations, which is how backtests get flattered.)

## How it works

Two-stage funnel to stay inside free-API rate limits:

1. **Stage A** — batched fundamentals + 1y price history for the whole universe,
   quality gate (cap band, extreme P/E), rank on fundamentals + technicals.
2. **Stage B** — only the top `stage_a_shortlist_size` names get the expensive
   per-ticker calls (SEC EDGAR, Google Trends). Missing data never zeroes a
   score: weights renormalize over the categories actually present.

A signal that comes back **identical for every ticker** is dropped and its weight
redistributed, same as a missing one. Percentile-ranking an all-constant input
(e.g. no ticker had open-market insider activity in the window) hands everyone the
same mid-rank, which cannot reorder anything — it is the inert-scalar trap that
keeps macro unweighted. Left in, it would still consume its weight and dilute the
signals that do discriminate. The report says which signals this hit.

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
python run_weekly_report.py --dry-run             # Stage A only, no EDGAR/Trends/FRED
python run_weekly_report.py --universe my.csv     # custom watchlist (needs 'ticker' column)
python run_weekly_report.py --top-n 10 -v
```

Tuning lives in `config/weights.yaml` (weights must sum to 1.0, validated at load).

## Automation

Two GitHub Actions workflows:

- `tests.yml` — pytest on every PR and push to main.
- `weekly_report.yml` — **Monday** morning (11:37 UTC): generates the report and
  commits it to `reports/` on main. Also runnable on demand from the Actions tab
  (workflow_dispatch).
- `backtest.yml` / `diagnose.yml` — manual only. `diagnose` prints what the SEC
  submissions feed actually contains for a few tickers, so signal behaviour can be
  checked against live data instead of guessed at (`scripts/diagnose_edgar.py`).

Add `SEC_EDGAR_USER_AGENT` as a repository secret (Settings → Secrets and variables →
Actions) — it unlocks the insider, corporate-event, and filing-text signals, 0.29 of the
weight budget. `FRED_API_KEY` is optional and affects only the contextual regime panel,
never the ranking.

Delivery (Claude Routine, Monday 16:00 UTC) posts the full analyst deep dive +
insider analysis and the recommendation tracker shortly after the workflow finishes.

### Recommendation tracker

A running ledger of the **week's #1 pick**, updated **weekly (Mondays)**: each new
top pick is anchored once — to the date and price at which the screener first
recommended it — and never re-dated, even if it leaves the top spot and returns later.
Each run refreshes the current price and shows the change since first recommendation.
Output: `reports/recommendations.md` (readable table) and `recommendations.csv` (the
durable ledger). Run manually with `python run_tracker.py --reports-dir reports`.

To seed the ledger from existing reports using historical closes on each report date,
run the workflow manually (Actions tab → "Weekly stock report" → Run workflow →
`backfill_tracker: true`), or locally: `python run_tracker.py --reports-dir reports --backfill`.

Distinct from the scoreboard below: the scoreboard grades a *cohort* (each week's full
top-N return vs benchmarks) to tune weights; the tracker follows the *single top pick*
from first recommendation so you can watch how it plays out.

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

Only truly point-in-time signals participate: technical, stability (trailing-year
beta/idio-vol from the same sliced prices), earnings-drift (dated announcements via
the same `surprise_asof` the weekly run uses for "today"), insider, events, and
(with `--include-filing-text`, document-heavy) filing language. Fundamentals,
valuation, quality, short interest, and trends are excluded — free sources only
serve *current* snapshots for those, and backtesting them with today's data would
be lookahead bias. Results also carry survivorship bias: today's universe omits
delisted names, so absolute returns flatter; treat relative signal comparisons
as the useful output.

Form 4 history is fetched per ticker with a cap that **scales to the window**
(`--max-form4` overrides). This matters: the fetch keeps the *newest* filings, so a
cap sized for one year would leave every early rebalance of a multi-year run with no
in-window insider activity — a constant column that looks like a working signal and
measures nothing. Small/mid-cap tech issuers file roughly 70–110 Form 4s a year.

Also runnable from the Actions tab (**Backtest** → Run workflow) with start/end,
step-weeks, top-n, and filing-text as inputs; results are committed to
`reports/backtests/`. Set the `SEC_EDGAR_USER_AGENT` secret first — without it the
run measures the technical signal only.

### How much data before re-weighting?

IC is a rank correlation, so the standard error of its mean scales as `σ_IC/√T`.
With typical cross-sectional IC volatility (~0.15), reaching a t-stat of 2 takes
roughly **9 periods for a strong signal (IC ≈ 0.10), ~36 for a modest one
(IC ≈ 0.05), and ~100 for a weak one (IC ≈ 0.03)**. The adaptive machinery starts
tilting after 6 graded reports, but that early tilt is deliberately shrunk and
capped — treat ~6 months as the point where a live-measured weight change is worth
acting on manually, and ~1 year before trusting a modest signal.

Two measurement caveats worth knowing:

- **Scoreboard ICs overlap.** Each report is graded on its return *to today*, so
  consecutive weekly reports share nearly the same return window. They are not
  independent samples, and the report count overstates the evidence.
- **Backtest ICs don't.** The walk-forward loop uses non-overlapping forward
  returns per rebalance, so its ICs are the statistically sound number. Prefer the
  backtest for weight decisions; treat the scoreboard as the running indicator.

Reading the output: sustained mean IC above **+0.03** is likely real, **|IC| < 0.02**
is noise regardless of sign, and a consistently *negative* IC means the signal is
scored backwards.

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

- **Congressional trading was removed** (was 0.05). Two independent reasons, either
  sufficient: the Senate/House Stock Watcher datasets stopped returning in-window
  transactions and appear unmaintained, and even at full health the STOCK Act allows
  30–45 days to disclose — so the signal reports trades that are already six weeks
  stale in a screen that reruns weekly. Its weight was redistributed across the
  remaining eight. Reinstating it needs a *maintained* free source, which is an open
  v2 item; the code is recoverable from git history.
- **Corporate-events signal returns nothing so far** — the first live run with SEC
  credentials scored 0.0 events for all 63 shortlisted names despite 120-day
  stake/shelf windows. Likely cause: SC 13D/13G are filed *by the holder*, so they
  may not appear in the subject issuer's own `data.sec.gov` submissions feed, which
  is what this reads. Unverified — needs a live check against a name known to have a
  recent 13D. Until then the degenerate-signal guard marks it unavailable and
  redistributes its 0.09 weight, so it costs nothing but contributes nothing.
- **yfinance is unofficial** — Yahoo can change endpoints; per-ticker failures are
  skipped and counted in the report header.
- Not investment advice; it's an automated research screen.

## v2 backlog

Reddit sentiment (OAuth app + VADER/ticker-disambiguation),
BLS/FRED hiring & supply-cost overlays, supply-chain links from 10-K customer
disclosures (Cohen-Frazzini), HTML report, LLM-written per-pick narratives,
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
