"""SEC EDGAR insider (Form 4) activity for a shortlist of tickers.

Tickers are resolved to issuer CIKs via the official company_tickers.json
map, and Form 4 counts come from each issuer's own submissions feed
(data.sec.gov) — never from full-text search, which would match unrelated
filings for short/common tickers like 'S' or 'U'.

Respects SEC fair-access policy: descriptive User-Agent required, requests
throttled well below the 10 req/s limit.
"""

from __future__ import annotations

import logging
import time
from datetime import date, timedelta

import requests

log = logging.getLogger(__name__)

COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
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
        self._cik_map: dict[str, int] | None = None

    def _get_json(self, url: str) -> dict:
        try:
            resp = self.session.get(url, timeout=30)
            resp.raise_for_status()
            return resp.json()
        finally:
            time.sleep(REQUEST_PAUSE_SECS)

    def cik_for(self, ticker: str) -> int | None:
        """Resolve a ticker to its issuer CIK (cached for the run)."""
        if self._cik_map is None:
            try:
                raw = self._get_json(COMPANY_TICKERS_URL)
                self._cik_map = {
                    entry["ticker"].upper(): int(entry["cik_str"])
                    for entry in raw.values()
                }
            except Exception as exc:  # noqa: BLE001 — map failure disables the signal
                log.warning("EDGAR ticker->CIK map fetch failed: %s", exc)
                self._cik_map = {}
        return self._cik_map.get(ticker.upper())

    def recent_form4_count(
        self, ticker: str, lookback_days: int = LOOKBACK_DAYS
    ) -> int | None:
        """Form 4 filings BY THIS ISSUER in the lookback window.

        Returns None when the ticker can't be resolved or the fetch fails
        (caller treats as 'no information').
        """
        cik = self.cik_for(ticker)
        if cik is None:
            log.info("no CIK found for %s; insider signal unavailable", ticker)
            return None
        cutoff = (date.today() - timedelta(days=lookback_days)).isoformat()
        try:
            data = self._get_json(SUBMISSIONS_URL.format(cik=cik))
            recent = data.get("filings", {}).get("recent", {})
            forms = recent.get("form", [])
            dates = recent.get("filingDate", [])
            return sum(
                1
                for form, filed in zip(forms, dates)
                if form == "4" and filed >= cutoff
            )
        except Exception as exc:  # noqa: BLE001 — per-ticker failures are non-fatal
            log.warning("EDGAR submissions fetch failed for %s: %s", ticker, exc)
            return None


def fetch_form4_counts(
    tickers: list[str], user_agent: str, lookback_days: int = LOOKBACK_DAYS
) -> dict[str, int | None]:
    client = EdgarClient(user_agent)
    log.info("Fetching Form 4 counts for %d shortlisted tickers", len(tickers))
    return {t: client.recent_form4_count(t, lookback_days) for t in tickers}
