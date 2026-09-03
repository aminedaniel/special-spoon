"""Statement-quality signal: the cashflow-vs-earnings gap.

  - accrual gap: (operating cash flow - net income) / market cap, higher
    better (earnings backed by cash beat paper earnings — Sloan's accruals
    anomaly).

Share dilution used to be a second sub-signal here, averaged 50/50 with
accruals. It now lives in signals/issuance.py. The two are not comparable
evidence: issuance survived Hou/Xue/Zhang's (2020) replication among the best
of 452 anomalies, while Green/Hand/Soliman (2011) found the accruals anomaly
had largely disappeared from US equities after publication. Averaging a
survivor with a casualty and reporting one number hid both.

The split also removed a quiet failure: when share data was missing for a
ticker, combine_subscores(skipna=True) silently produced a full-strength
accruals-only score that the composite could not distinguish from a
fully-covered one.
"""

from __future__ import annotations

import pandas as pd

from .base import percentile_score


def score(fundamentals: pd.DataFrame) -> pd.Series:
    f = fundamentals
    ocf = pd.to_numeric(f.get("operatingCashflow"), errors="coerce")
    ni = pd.to_numeric(f.get("netIncomeToCommon"), errors="coerce")
    cap = pd.to_numeric(f.get("marketCap"), errors="coerce")
    return percentile_score((ocf - ni) / cap)
