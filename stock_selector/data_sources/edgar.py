"""Shared SEC EDGAR client: CIK resolution, cached submissions, throttling.

One client instance per run; the submissions feed for each issuer is fetched
once and shared by every EDGAR-based signal (insider, events, filing text).
Respects SEC fair-access policy: descriptive User-Agent, well under 10 req/s.

Note: the cached "recent" submissions block covers an issuer's ~1000 latest
filings — years of history for small/mid caps, which is what both the weekly
run and the backtest consume.
"""

from __future__ import annotations

import logging
import time

import requests

log = logging.getLogger(__name__)

COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
FILING_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{doc}"
REQUEST_PAUSE_SECS = 0.15  # ~6 req/s, under SEC's 10 req/s cap
MAX_DOC_CHARS = 800_000  # cap filing-document reads


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
        self._submissions: dict[int, dict] = {}

    def _get(self, url: str) -> requests.Response:
        try:
            resp = self.session.get(url, timeout=30)
            resp.raise_for_status()
            return resp
        finally:
            time.sleep(REQUEST_PAUSE_SECS)

    def _get_json(self, url: str) -> dict:
        return self._get(url).json()

    def cik_for(self, ticker: str) -> int | None:
        """Resolve a ticker to its issuer CIK (map cached for the run)."""
        if self._cik_map is None:
            try:
                raw = self._get_json(COMPANY_TICKERS_URL)
                self._cik_map = {
                    entry["ticker"].upper(): int(entry["cik_str"])
                    for entry in raw.values()
                }
            except Exception as exc:  # noqa: BLE001 — map failure disables EDGAR signals
                log.warning("EDGAR ticker->CIK map fetch failed: %s", exc)
                self._cik_map = {}
        return self._cik_map.get(ticker.upper())

    def recent_filings(self, cik: int) -> list[dict]:
        """The issuer's recent filings as row dicts, newest first, cached.

        Keys: form, filingDate, accessionNumber, primaryDocument, items.
        """
        if cik not in self._submissions:
            self._submissions[cik] = self._get_json(SUBMISSIONS_URL.format(cik=cik))
        recent = self._submissions[cik].get("filings", {}).get("recent", {})
        forms = recent.get("form", [])
        n = len(forms)

        def col(name: str) -> list:
            values = recent.get(name, [])
            return values if len(values) == n else [""] * n

        return [
            {
                "form": forms[i],
                "filingDate": col("filingDate")[i],
                "accessionNumber": col("accessionNumber")[i],
                "primaryDocument": col("primaryDocument")[i],
                "items": col("items")[i],
            }
            for i in range(n)
        ]

    def filing_text(self, cik: int, accession: str, doc: str) -> str:
        """Fetch a filing document's text (HTML included), size-capped."""
        url = FILING_URL.format(cik=cik, accession=accession.replace("-", ""), doc=doc)
        return self._get(url).text[:MAX_DOC_CHARS]
