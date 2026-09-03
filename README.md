# special-spoon — weekly stock selector

Screens a universe of **small/mid-cap US tech stocks** ($300M–$20B) weekly and ranks
them by a weighted composite of:

| Signal | Base weight | Source (all free) |
|---|---|---|
| Earnings drift / PEAD (standardized earnings surprise) | 0.11 | Yahoo Finance earnings dates via `yfinance` |
| Technicals (12-1 momentum, trend, breakout, volume) | 0.09 | Yahoo Finance via `yfinance` |
| Fundamentals (growth, debt, ROE, margins) | 0.13 | Yahoo Finance via `yfinance` |
| Profitability (GP/assets, asset growth — Novy-Marx/CMA) | 0.09 | Yahoo Finance statements via `yfinance` |
| Insider activity (officer-weighted cluster buys, discounted sells, 90d) | 0.14 | SEC EDGAR issuer submissions + Form 4 XML |
| Stability (low beta vs QQQ + low idiosyncratic vol) | 0.05 | Yahoo Finance via `yfinance` |
| Short interest (% of float + MoM change — high/rising = bad) | 0.07 | Exchange short reports via `yfinance` |
| Quality (accrual gap, share dilution) | 0.09 | Yahoo Finance financial fields + share history |
| Valuation (P/E, P/S, EV/Sales, EV/EBITDA, PEG, P/FCF — cheaper = better) | 0.07 | Yahoo Finance via `yfinance` |
| Corporate events (13D activist stakes, S-3 shelves, 8-K 4.02) | 0.08 | SEC EDGAR submissions feed |
| Filing-language stability ("lazy prices", year-over-year) | 0.08 | SEC EDGAR 10-Q/10-K text diff |
| Macro / Fed regime | context only | FRED (`DFF`, `T10Y2Y`, `VIXCLS`) |

Weights are *base* weights: once enough graded history accumulates, the scoreboard
tilts them toward signals with demonstrated predictive power (see "Adaptive
reweighting" below).

No weight here is validated on this universe. A 53-period walk-forward backtest
(2022-07 → 2026-07, non-overlapping forward returns) found **every backtestable
signal statistically indistinguishable from zero**:

| Signal | Measured IC | t | 95% CI |
|---|---|---|---|
| technical | +0.013 | +0.47 | [−0.042, +0.069] |
| insider | +0.000 | +0.00 | [−0.039, +0.039] |
| events | −0.004 | −0.25 | [−0.038, +0.029] |
| earnings_drift | −0.006 | −0.34 | [−0.044, +0.031] |
| stability | −0.022 | −0.64 | [−0.090, +0.046] |

An earlier 27-period run appeared to show insider at +0.068 (t=1.96). That was an
artifact of a Form 4 fetch cap too small for the window — coverage varied with each
issuer's filing frequency, which biased the cross-section — and it vanished once the
cap was fixed. The episode is written up in `reports/backtests/COMPARISON.md`; the
short version is **audit what the pipeline actually fetched before believing an IC**.

Stability is the one signal with structure worth noting: IC **+0.029** in the
2022–24 bear/recovery half and **−0.076** in the 2024–26 momentum half. Betting
against beta pays in drawdowns and loses in momentum markets — the factor behaving
as theory predicts, which is why it is held small rather than cut.

Over the full four years the strategy returns +145.7% against QQQ's +148.5% with
beta 1.15 — a slightly-levered index tracker, no alpha in either direction. Treat
this as a research screen whose edge is unproven, not a validated strategy.

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
   per-ticker calls (SEC EDGAR, earnings dates, statements). Missing data never zeroes a
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
python run_weekly_report.py --dry-run             # Stage A only, no EDGAR/FRED
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
valuation, quality, and short interest are excluded — free sources only
serve *current* snapshots for those, and backtesting them with today's data would
be lookahead bias. Results also carry survivorship bias: today's universe omits
delisted names, so absolute returns flatter; treat relative signal comparisons
as the useful output.

Form 4 history is fetched per ticker with a cap that **scales to the window**
(`--max-form4` overrides). This matters: the fetch keeps the *newest* filings, so a
cap sized for one year would leave every early rebalance of a multi-year run with no
in-window insider activity — a constant column that looks like a working signal and
measures nothing. Small/mid-cap tech issuers file roughly 70–110 Form 4s a year.

Also runnable from the Actions tab (**Backtest** → Run workflow) with universe,
start/end, step-weeks, top-n, filing-text, and `skip_edgar` as inputs; results are
committed to `reports/backtests/`, stamped with the universe so variants don't
clobber each other.

`--skip-edgar` scores only the signals that need no SEC calls (technical, stability,
earnings-drift). EDGAR is the entire runtime cost — roughly 1.6 min/ticker over a
four-year window — so a 186-name universe takes ~20 minutes with the flag and would
take **10+ hours** without it, past both this workflow's timeout and GitHub's job cap.

### Universe size experiment

Three checked-in, mutually disjoint universes let the screen be tested across the
size spectrum:

| File | Names | Band |
|---|---|---|
| `config/universe.csv` | 99 | $300M–$20B (the live screen) |
| `config/universe_largecap.csv` | 87 | >$20B US tech / comm services |
| `config/universe_merged.csv` | 186 | the union |

Run separately rather than blended by design. Most of these anomalies are documented
to concentrate in small caps (limits to arbitrage: PEAD is strongest in thinly
covered names, insider buying in small firms, short interest where borrow is
constrained), so the expectation is that they *weaken* with size.

More importantly, ranking across a merged universe makes **size itself the dominant
hidden factor** — beta, volatility, multiples and momentum all correlate with market
cap, so a blended composite becomes a size bet wearing twelve signals as a costume.
Over 2022–2026 mega-cap tech massively outperformed small-cap tech, so a merged run
would likely look *better* while measuring nothing new. Comparing the merged result
against the two separate runs is what isolates that confound. Set the `SEC_EDGAR_USER_AGENT` secret first — without it the
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
- **Corporate-events signal was seasonally blind — diagnosed and fixed.** It scored
  ~90% of the universe identically for months. The explanation carried here since #12
  ("SC 13D/13G are filed *by the holder*, so they may not appear in the issuer's own
  submissions feed") was **wrong**: a live check found 443 stake filings across ten
  issuers, form strings matching exactly. The real cause was measured instead
  (`scripts/diagnose_events.py`, 4210 stake filings over the live universe):

  | month | Jan | **Feb** | Mar | Apr | May | Jun | Jul | Aug | Sep | Oct | Nov | Dec |
  |---|---|---|---|---|---|---|---|---|---|---|---|---|
  | filings | 590 | **2612** | 110 | 86 | 65 | 69 | 85 | 86 | 85 | 95 | 250 | 77 |

  Schedule 13G amendments are due within 45 days of year end, so 62% of stake
  filings land in February and a 120-day window ending anywhere in Jun–Dec sees
  **none** of them — the run found zero in-window across all 93 resolved tickers.
  The stake window is now 365 days. Separately, the passive 13G family (94% of
  stake filings, near-universal over a year) is no longer scored at all: it would
  add the same constant to every ticker and cannot rank, the same inert-scalar
  reason macro stays unweighted. Only SC 13D/13D/A — the activist form, and the one
  with documented abnormal returns — scores, flat rather than summed so a
  long-running campaign's amendments cannot compound. **Not yet validated in the
  backtest**; it fires where it previously could not, which is a precondition for
  having predictive power, not evidence of it.
- **yfinance is unofficial** — Yahoo can change endpoints; per-ticker failures are
  skipped and counted in the report header.
- Not investment advice; it's an automated research screen.

## v2 backlog

Reddit sentiment (OAuth app + VADER/ticker-disambiguation),
BLS/FRED hiring & supply-cost overlays, supply-chain links from 10-K customer
disclosures (Cohen-Frazzini), HTML report, LLM-written per-pick narratives,
response caching. Per-ticker options flow is excluded — no viable free source.

### Removed: search-interest momentum (Google Trends)

Removed after eight weeks in which it produced **zero** data points: no
`score_trends` column was ever written to a rankings CSV, and `trends` never
appeared in `reports/signal_ic.csv`. The report's "likely rate-limited" note was
guess text, never a diagnosis — so it was measured before being cut.

The diagnostic (run four times from CI) found the behaviour is **non-deterministic
rate limiting**, not a categorical block and not a code bug:

| Run | Outcome |
|---|---|
| 3 probes | all succeeded — full frames, real momentum values for every ticker |
| 5+ probes, minutes later | `TooManyRequestsError`, HTTP 429, `Error 429 (Bad Request)` |

Google enforces a small per-IP quota, and GitHub runner IPs are shared and
recycled, so whether a request succeeds depends on what other people's workflows
have already spent. The weekly run needs **20 sequential batch requests**
(99 tickers / 5), which exceeds that quota comfortably — and on an already-spent
IP even the first batch fails, so every ticker returns None.

No batching or backoff scheme fits 20 requests into a quota of a few, so this is
not engineerable around on shared CI. It was also the weakest-evidence signal in
the set — search attention predicts *volatility*, not direction — and its 0.05
redistributed cleanly, so removal costs nothing measurable.

Reinstating it would need a non-datacenter egress path (a self-hosted runner or a
proxy) and would still be worth only a small weight until its IC could be measured.

