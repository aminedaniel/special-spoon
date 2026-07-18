"""SEC EDGAR insider (Form 4) activity for a shortlist of tickers.

Uses the free EDGAR full-text search API (efts.sec.gov) to find recent Form 4
filings per ticker, then scores on net filing direction. Respects SEC
fair-access policy: descriptive User-Agent required, requests throttled well
below the 10 req/s limit.
"""

from __future__ import annotations

import logging
import time
from datetime import date, timedelta

import requests

log = logging.getLogger(__name__)

EDGAR_SEARCH_URL = "https://efts.sec.gov/LATEST/search-index"
REQUEST_PAUSE_SECS = 0.15  # ~6 req/s, under SEC's 10 req/s cap
LOOKBACK_DAYS = 14


class EdgarClient:
    def __init__(self, user_agent: str):
        if not user_agent:
            raise ValueError(
                "SEC_EDGAR_USER_AGENT is required (SEC fair-access policy); "
                "set it in .env, e.g. 'special-spoon you@example.com'"
            )
        self.session = requests.Session()
        self.session.headers["User-Agent"] = user_agent

    def recent_form4_count(self, ticker: str, lookback_days: int = LOOKBACK_DAYS) -> int | None:
        """Count of Form 4 filings mentioning the ticker in the lookback window.

        Returns None on request failure (caller treats as 'no information').
        """
        end = date.today()
        start = end - timedelta(days=lookback_days)
        params = {
            "q": f'"{ticker}"',
            "forms": "4",
            "startdt": start.isoformat(),
            "enddt": end.isoformat(),
        }
        try:
            resp = self.session.get(EDGAR_SEARCH_URL, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            return int(data.get("hits", {}).get("total", {}).get("value", 0))
        except Exception as exc:  # noqa: BLE001 — per-ticker failures are non-fatal
            log.warning("EDGAR Form 4 lookup failed for %s: %s", ticker, exc)
            return None
        finally:
            time.sleep(REQUEST_PAUSE_SECS)


def fetch_form4_counts(
    tickers: list[str], user_agent: str, lookback_days: int = LOOKBACK_DAYS
) -> dict[str, int | None]:
    client = EdgarClient(user_agent)
    log.info("Fetching Form 4 counts for %d shortlisted tickers", len(tickers))
    return {t: client.recent_form4_count(t, lookback_days) for t in tickers}
