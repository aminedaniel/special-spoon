# Portfolio-construction comparison (2024-07-01 → 2026-07-29)

Three walk-forward runs over the same window, same universe, same signal
(technical only — `SEC_EDGAR_USER_AGENT` was unset, so insider/events/filing-text
never ran). Each variant changes exactly **one** knob from the baseline, so this
measures **portfolio construction**, not signal quality.

| | top-10 / 4w (baseline) | top-20 / 4w | top-10 / 2w |
|---|---|---|---|
| Cumulative | **+28.6%** | **+53.3%** | **+99.5%** |
| QQQ / IWM over same window | +43.0% / +48.8% | +43.0% / +48.8% | +43.0% / +48.8% |
| Periods | 27 | 27 | 54 |
| Mean return / period | +1.85% | +2.21% | +1.62% |
| Std dev / period | 13.34% | 11.11% | 8.17% |
| Worst period | −27.8% | −24.1% | −18.8% |
| Beta vs QQQ | 1.68 | 1.44 | 1.32 |
| CAPM alpha (annualized) | −8.9% | +0.3% | **+17.5%** |
| t(alpha) | −0.43 | +0.02 | +0.76 |
| Alpha hit rate | 48% | 48% | 57% |
| Mean signal IC | +0.016 | +0.016 | +0.005 |

## What actually changed

**Not the signal.** IC is the honest measure of predictive power, and it did not
improve — it is +0.016 in both 4-week variants (identical, as expected: IC is
computed across the whole scored universe and does not depend on how many names
you hold) and *falls* to +0.005 at the 2-week horizon. By that measure the
technical signal is no better in any variant, and slightly worse at two weeks.

**Volatility drag did.** Cumulative return rose monotonically as per-period
volatility fell (13.3% → 11.1% → 8.2%). Geometric return lags arithmetic return
by roughly σ²/2, so a portfolio of high-beta small-caps loses a large share of its
average return to compounding. The top-10 baseline gave up ~0.91 percentage points
per period to drag; top-20 gave up 0.62; the 2-week variant only 0.33.

**Beta fell too** (1.68 → 1.44 → 1.32), which is why the baseline looked like
leveraged QQQ. Once you regress out beta, the baseline's alpha is *negative*
(−8.9%/yr): it did not merely lag the benchmark, it lagged what its own market
exposure predicted.

## Reading it honestly

The 2-week variant is the best on every dimension — return, volatility, drawdown,
beta, alpha, hit rate — but **none of these alphas is statistically significant**.
t(alpha) = 0.76 over 54 non-overlapping periods is roughly p ≈ 0.45. The ranking
is directionally consistent, not proven.

Two further caveats specific to the 2-week variant:

- **Turnover doubles.** 26 rebalances a year in small/mid-cap tech, where spreads
  run 5–20 bps a side, plausibly costs 2–4%/yr — real but not enough to erase a
  17.5% gross alpha. The backtest is gross of costs.
- **Lower IC with higher return** is a tension worth watching. It is possible for
  the top decile to outperform while universe-wide rank correlation is ~0 (IC is a
  monotonic, whole-distribution measure and the tails can behave differently), but
  it is also what overfitting to one 2-year window looks like. Treat it as a
  hypothesis to re-test, not a settled result.

## Implication for the live setup

The live config is already on the better side of both knobs: `report.top_n: 20`
and weekly reports. Nothing here argues for changing `config/weights.yaml`.

The one change these runs *do* argue for is **holding more names and rebalancing
more often**, i.e. diversification — not a different weighting of signals. Signal
weights cannot be evaluated from these runs at all, because only one signal ran.
Adding the `SEC_EDGAR_USER_AGENT` secret and re-running would put insider, events,
and filing-text into the comparison and make the IC column meaningful.

---

# Five-signal run (2026-07-29, 2-year window) — SUPERSEDED, see below

> **The insider result in this section is wrong.** It was produced with a Form 4
> fetch cap of 80 filings/ticker, far too small for the window; the longer run
> that follows shows the +0.068 disappears once coverage is fixed. The section is
> kept unedited as the record of what was believed and why.

Everything above measured **one signal**. The insider signal was silently
returning $0 for every ticker in every one of those runs: `primaryDocument` for
Form 3/4/5 carries an XSL-viewer prefix, so fetching it returned rendered HTML
instead of XML and every parse failed. That is fixed, and `stability` and
`earnings_drift` are now wired into the walk-forward loop, so this run grades
five signals over the same window and cadence as the top-10/4w baseline.

## Per-signal IC — 27 non-overlapping periods

| Signal | Mean IC | sd | t | 95% CI | % periods positive |
|---|---|---|---|---|---|
| insider | **+0.068** | 0.179 | **+1.96** | [+0.000, +0.135] | 67% |
| technical | +0.029 | 0.249 | +0.61 | [−0.064, +0.123] | 59% |
| earnings_drift | +0.001 | 0.115 | +0.03 | [−0.043, +0.044] | 56% |
| events | −0.002 | 0.124 | −0.10 | [−0.049, +0.044] | 48% |
| stability | −0.077 | 0.269 | −1.49 | [−0.179, +0.025] | 41% |

## Portfolio-level, same window and cadence

| | Technical only | Five signals |
|---|---|---|
| Cumulative | +28.6% | **+38.9%** |
| Std dev / period | 13.3% | **9.7%** |
| Worst period | −27.8% | **−20.3%** |
| Beta vs QQQ | 1.68 | **1.32** |
| CAPM alpha (annualized) | −8.9% | **−4.3%** |
| Alpha hit rate | 48% | 52% |

Better on every dimension, and still behind QQQ (+43.0%) with negative alpha.
The gain is risk reduction, not edge.

## What this changed

- **insider 0.13 → 0.18.** The only signal whose CI clears zero, the most
  consistent (67%), and the lowest-volatility of the meaningful ones. It also
  has the best prior: it is the one signal here reading *private information*
  rather than public prices.
- **stability 0.07 → 0.02.** Measured backwards. The weight was set hours
  earlier on this repo's *portfolio-level* finding that lower beta compounded
  better — the direct per-name test says that inference was wrong. Floored
  rather than removed: 2024-26 was a momentum-led small-cap market, which is
  exactly when betting against beta loses, and a zero weight can never recover.
- **earnings_drift held at 0.11** despite a flat IC. Only ~20 of 99 names have
  an announcement inside the drift window in any period, so the cross-section
  being ranked is small and the estimate is correspondingly weak — that is
  absence of evidence, not evidence of absence.
- **events held at 0.08.** Its ~0.000 IC was measured with the *old* code: the
  shelf-family match (S-3ASR/F-3) and Friday-dump penalty landed after this
  data was generated, and the diagnostic showed plain "S-3" never matched
  anything. Worth re-measuring, not reweighting.

## Honest limits

27 periods over 2 years, one universe, one regime. t=1.96 on insider is exactly
at the conventional threshold, and with five signals examined, some multiple-
comparisons discount is warranted — treat it as "promising and worth weight",
not "established". Survivorship bias still inflates absolute returns. The seven
signals that cannot be backtested on free data (fundamentals, valuation,
quality, profitability, short interest, filing-text, trends) remain unmeasured.


---

# Four-year run (2026-07-29) — the correction

53 non-overlapping periods, 2022-07-01 -> 2026-07-29, top 10, 4-week rebalances.
Same code as the two-year run above except for one fix: the Form 4 cap now scales
with the window (80 -> 635 filings/ticker).

That fix changes the answer completely.

## Per-signal IC — 53 periods

| Signal | Mean IC | t | 95% CI | % positive |
|---|---|---|---|---|
| technical | +0.013 | +0.47 | [-0.042, +0.069] | 58% |
| insider | +0.000 | +0.00 | [-0.039, +0.039] | 49% |
| events | -0.004 | -0.25 | [-0.038, +0.029] | 53% |
| earnings_drift | -0.006 | -0.34 | [-0.044, +0.031] | 42% |
| stability | -0.022 | -0.64 | [-0.090, +0.046] | 49% |

**Not one signal is distinguishable from zero.** Every confidence interval
straddles it.

## Why the insider result changed

`fetch_form4_history` keeps the *newest* `max_filings` rows. With the cap at 80
and a fetch window opening 2024-01, active filers (~70-110 Form 4s/year) had only
their most recent ~9 months retained — so early rebalances saw no insider activity
at all, and coverage varied **systematically with filing frequency**: infrequent
filers got complete history, frequent filers got zeros. That is a biased
cross-section, not random noise, and it manufactured a signal.

Over the identical 2024-07 onward window:

| Run | Form 4 cap | Insider IC |
|---|---|---|
| 2-year | 80 | **+0.068** |
| 4-year, same window | 635 | **+0.009** |

Same dates, same scoring code, different data coverage.

## The one finding that survives

Stability splits by regime exactly as the low-risk anomaly predicts:

| Window | Stability IC |
|---|---|
| 2022-07 -> 2024-06 (bear + recovery) | **+0.029** |
| 2024-07 -> 2026-07 (momentum-led) | **-0.076** |

Betting against beta pays in drawdowns and loses in momentum markets. That is the
factor behaving normally, not a broken signal — so cutting it to 0.02 on the
momentum half alone was over-reading a single regime.

## Portfolio level

| | 2-year (27p) | 4-year (53p) |
|---|---|---|
| Cumulative | +38.9% (QQQ +43.0%) | +145.7% (QQQ +148.5%) |
| Beta vs QQQ | 1.32 | 1.15 |
| CAPM alpha (annualized) | -4.3% | -1.9% |
| t(alpha) | -0.33 | -0.23 |

Over four years the strategy is a slightly-levered index tracker: it roughly
matches QQQ, with no alpha in either direction.

## What this means for the weights

Nothing in `config/weights.yaml` is validated on this universe. The weights rest
on published evidence and judgement, which is the honest basis available — but
they should not be described as measured. Two lessons worth keeping:

1. **A weight change needs the data pipeline audited first.** Both false signals
   found today (insider looking dead, then insider looking strong) were data-
   coverage artifacts, not scoring bugs. Check what was actually fetched before
   believing an IC.
2. **53 periods of nothing is itself informative.** It says any real edge here is
   small enough to need far more data — or a different kind of signal than
   free-tier sources provide. It does not say the screen is worthless; it says
   the screen has not been shown to beat holding QQQ.

---

# Cost-adjusted run (2026-09-04) — and the benchmark was wrong

54 non-overlapping periods, 2022-07-01 -> 2026-09-04, top 10, 4-week rebalances.
First run to include: the five correctness fixes (#39-#43), issuance split out
and scored point-in-time (#46-#49), insider buy/sell ranked separately (#50),
and transaction costs charged on turnover (#53).

## The finding that changes how everything above should be read

The strategy's CAPM alpha depends almost entirely on which benchmark it is
measured against, and this repo has been using the wrong one.

| Benchmark | Beta | Alpha (annualised) | t |
|---|---|---|---|
| **QQQ** (used everywhere above) | 1.11 | **-16.1%** | **-2.06** |
| **IWM** | 0.99 | -4.7% | -0.48 |

Against QQQ the screen shows *statistically significant negative alpha*. Against
IWM it is indistinguishable from zero — and beta is 0.99, meaning IWM is simply
the right risk cohort for it.

QQQ is a mega-cap index. This universe is $300M-$20B. Over 2022-2026 mega-caps
led by an enormous margin (QQQ +159.1% against IWM +84.3%), so benchmarking a
small/mid-cap screen against QQQ charges it for not being a mega-cap fund.
**That is a size artifact, not stock selection**, and it retroactively qualifies
the "+145.7% vs QQQ +148.5%" headline in the four-year section above: matching
QQQ over that window was, if anything, flattering.

Correct reading: on the appropriate benchmark, this screen has no measurable
alpha in either direction. Which is exactly what the per-signal ICs say.

## Per-signal IC — 54 periods

| Signal | Mean IC | t | 95% CI | % positive |
|---|---|---|---|---|
| issuance | +0.005 | +0.28 | [-0.033, +0.044] | 59% |
| technical | +0.003 | +0.09 | [-0.056, +0.061] | 57% |
| insider | +0.000 | +0.01 | [-0.039, +0.040] | 56% |
| events | -0.004 | -0.29 | [-0.033, +0.024] | 52% |
| earnings_drift | -0.016 | -0.82 | [-0.052, +0.021] | 43% |
| stability | -0.017 | -0.50 | [-0.084, +0.050] | 50% |
| filing_text | -0.030 | -1.31 | [-0.076, +0.015] | 41% |

Not one signal is distinguishable from zero. Every interval straddles it, and
the largest |t| is filing_text at -1.31.

**Issuance is measured here for the first time.** It is the best-replicated
factor in the table — it survived Hou/Xue/Zhang (2020) where roughly 65% of 452
anomalies failed — and on this universe it is +0.005, t = +0.28. Being able to
measure it at all required `get_shares_full`'s dated history plus a 45-day
reporting lag; every other fundamentals-family signal remains untestable on
snapshot data.

**Insider is +0.000 after two rounds of repair** — excluding the 47% of Form 4s
that are 10b5-1 planned trades, and separating buy conviction from sell pressure
after the raw-dollar netting was shown to be dominated 1,145:1 by selling. The
signal can now express insider buying, which it demonstrably could not before.
There is simply almost none to express: roughly 2 of 63 names had any
discretionary buying in a 90-day window.

## Portfolio level, with costs

| | gross | net |
|---|---|---|
| Cumulative (54 periods) | +39.5% | +32.9% |
| Benchmarks | QQQ +159.1% / IWM +84.3% | |
| Beta / alpha / t vs QQQ | 1.11 / -16.1% / -2.06 | 1.11 / -17.2% / -2.22 |
| Beta / alpha / t vs IWM | 0.99 / -4.7% / -0.48 | 0.99 / -5.9% / -0.60 |
| Mean turnover | — | 39%/period |
| Cost drag | — | 6.6% cumulative (0.091%/period) |

Costs are charged per name at its own market-cap band (25bps one-way at this
universe's size), using shares x price as of each rebalance rather than today's
market cap. Two estimates of mine were wrong and are corrected here: I predicted
50-70% turnover and 15-20% cumulative drag. Actual: 39% and 6.6%.

## The return fell from +145.7% to +39.5%. That is not evidence the fixes hurt.

Same window, near-identical benchmark path, but cumulative return collapsed
between the 53-period run above and this one. The signals changed underneath it
— events went from near-inert to firing on 13D stakes, insider stopped
effectively ranking on inverse selling, filing_text switched to year-over-year —
so the picks changed substantially.

It is tempting to read that as the corrections destroying performance. It is not
readable that way. With every IC at zero, a 10-name monthly portfolio's return
path is close to a random draw; +145.7% and +39.5% are both samples from the
same zero-alpha distribution, and neither is evidence about signal quality. What
*is* stable across both runs is the conclusion: no measurable edge, and no
selection ability against the correct benchmark.

The fixes should be judged on whether they made each signal measure what it
claims to — which they did, and which is checkable — not on a return path that
carries no information.

## What this means

1. **Do not reweight.** No signal met the pre-committed |t| >= 2 bar; the best
   is +0.28. `config/weights.yaml` remains unvalidated on this universe.
2. **Report against IWM.** `backtest.py` and `scoreboard.py` both headline alpha
   vs QQQ. For a $300M-$20B universe that is the wrong cohort and manufactures
   a spurious -16%/yr. Worth its own change.
3. **Smaller caps would make this worse, not better.** More names would genuinely
   help statistical power (IC noise scales ~1/sqrt(N); 63 -> 300 names cuts it
   ~2.2x). But the cost bands are 75bps at $50-300M and 150bps below that,
   against 25bps here — at the same 39% turnover, drag goes from 6.6% to roughly
   20-40% cumulative. Paying that to better measure something that measures zero
   is not a trade worth making.
4. **The binding constraint is still power, not coverage.** 54 periods against
   12 signals. Detecting IC 0.03 needs ~100 independent periods. Point-in-time
   fundamentals would make 0.315 of the weight table testable and extend history
   to 1990 — that is the purchase that changes what is knowable here, and it
   adds no trading cost.
