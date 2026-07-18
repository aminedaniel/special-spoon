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
import xml.etree.ElementTree as ET
from datetime import date, timedelta

import requests

log = logging.getLogger(__name__)

COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
FILING_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{doc}"
REQUEST_PAUSE_SECS = 0.15  # ~6 req/s, under SEC's 10 req/s cap
LOOKBACK_DAYS = 14
MAX_FILINGS_PER_TICKER = 10  # bounds per-ticker request volume


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

    def _recent_form4_filings(
        self, cik: int, cutoff: str
    ) -> list[tuple[str, str]]:
        """(accessionNumber, primaryDocument) for in-window Form 4 filings."""
        data = self._get_json(SUBMISSIONS_URL.format(cik=cik))
        recent = data.get("filings", {}).get("recent", {})
        rows = zip(
            recent.get("form", []),
            recent.get("filingDate", []),
            recent.get("accessionNumber", []),
            recent.get("primaryDocument", []),
        )
        return [
            (accession, doc)
            for form, filed, accession, doc in rows
            if form == "4" and filed >= cutoff
        ][:MAX_FILINGS_PER_TICKER]

    def _parse_form4(self, xml_text: str) -> tuple[float, float]:
        """Net (buy_dollars, sell_dollars) from a Form 4's open-market
        transactions — code P (purchase) and S (sale) only, ignoring awards,
        option exercises, tax withholding, and gifts."""
        buy = sell = 0.0
        root = ET.fromstring(xml_text)
        for tx in root.iter("nonDerivativeTransaction"):
            code = tx.findtext("transactionCoding/transactionCode")
            if code not in ("P", "S"):
                continue
            shares = tx.findtext(
                "transactionAmounts/transactionShares/value"
            )
            price = tx.findtext(
                "transactionAmounts/transactionPricePerShare/value"
            )
            try:
                dollars = float(shares) * float(price)
            except (TypeError, ValueError):
                continue
            if code == "P":
                buy += dollars
            else:
                sell += dollars
        return buy, sell

    def recent_form4_activity(
        self, ticker: str, lookback_days: int = LOOKBACK_DAYS
    ) -> dict | None:
        """Insider activity for the issuer in the lookback window.

        Returns {"net_dollars": buys - sells, "filings": n} from open-market
        transactions in the issuer's Form 4s, or None when the ticker can't
        be resolved / fetches fail (caller treats as 'no information').
        A filing whose XML can't be fetched or parsed still counts toward
        `filings` but contributes no dollars.
        """
        cik = self.cik_for(ticker)
        if cik is None:
            log.info("no CIK found for %s; insider signal unavailable", ticker)
            return None
        cutoff = (date.today() - timedelta(days=lookback_days)).isoformat()
        try:
            filings = self._recent_form4_filings(cik, cutoff)
        except Exception as exc:  # noqa: BLE001 — per-ticker failures are non-fatal
            log.warning("EDGAR submissions fetch failed for %s: %s", ticker, exc)
            return None

        net = 0.0
        for accession, doc in filings:
            if not doc.endswith(".xml"):
                continue
            url = FILING_URL.format(
                cik=cik, accession=accession.replace("-", ""), doc=doc
            )
            try:
                resp = self.session.get(url, timeout=30)
                resp.raise_for_status()
                buy, sell = self._parse_form4(resp.text)
                net += buy - sell
            except Exception as exc:  # noqa: BLE001 — skip unparseable filings
                log.debug("Form 4 parse failed for %s %s: %s", ticker, accession, exc)
            finally:
                time.sleep(REQUEST_PAUSE_SECS)
        return {"net_dollars": net, "filings": len(filings)}


def fetch_form4_activity(
    tickers: list[str], user_agent: str, lookback_days: int = LOOKBACK_DAYS
) -> dict[str, dict | None]:
    client = EdgarClient(user_agent)
    log.info("Fetching Form 4 activity for %d shortlisted tickers", len(tickers))
    return {t: client.recent_form4_activity(t, lookback_days) for t in tickers}
