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
