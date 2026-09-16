#!/usr/bin/env python3
"""Can a Cohen-Frazzini supply-chain signal be built from free EDGAR data?

Cohen & Frazzini (2008), "Economic Links and Predictable Returns", is the
strongest piece of evidence this project has not tried: a customer firm's stock
move predicts its supplier's move over the following month, because investors
do not join the two up promptly. Reported monthly alpha above 1.5% in the
original sample.

The data requirement looks satisfiable for free. SFAS 131 requires an issuer to
disclose any customer above 10% of revenue, and those disclosures sit in 10-K
Item 1 and in the concentration-of-credit-risk note, which EDGAR serves at no
cost. And the correction to an earlier claim of mine: the customer does NOT
need to be in this universe. The signal needs the CUSTOMER'S RETURNS, and those
are fetchable for any listed ticker. Universe membership is irrelevant.

What is genuinely unknown is entity resolution. Disclosures are prose --
"one customer accounted for approximately 14% of net revenue" names nobody at
all; "Apple Inc." resolves cleanly; "a large North American wireless carrier"
resolves to a guess. Nothing can be built on a graph that is mostly unnamed,
and no amount of argument settles what fraction is which. So this measures the
funnel and stops.

STOP CONDITIONS, FIXED BEFORE THE RUN (the point of writing them here):

  Under ~25 universe names with at least one resolved customer ticker, the
  signal is near-constant across the cross-section, the degenerate guard drops
  it, and the weight is wasted. That is not a prediction -- it is what already
  happened to congressional trading, to insider buying (35 of 66 tied), and to
  corporate events (55 of 66 tied). Record the finding and stop. Do not build
  on a sparse graph and hope.

  Under ~40% of 10-Ks containing any parseable concentration disclosure, the
  disclosure itself is not reliably extractable and the rest is moot.

Writes nothing. Read-only against EDGAR, throttled by the shared client.

    SEC_EDGAR_USER_AGENT="..." python scripts/diagnose_supply_chain.py --limit 99
"""

from __future__ import annotations

import argparse
import csv
import os
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from stock_selector.data_sources.edgar import COMPANY_TICKERS_URL, EdgarClient  # noqa: E402
from stock_selector.data_sources.edgar_filings import strip_html  # noqa: E402

# Language that actually appears in these disclosures. Collected from the forms
# rather than invented: issuers write "accounted for", "represented",
# "comprised", and the noun is customer/client/distributor.
CONCENTRATION_RE = re.compile(
    r"(?:customer|client|distributor|reseller)s?\b[^.]{0,200}?"
    r"(?:accounted for|represented|comprised|made up)\b[^.]{0,120}?\d{1,2}(?:\.\d+)?\s*%"
    r"|\d{1,2}(?:\.\d+)?\s*%[^.]{0,120}?(?:of (?:our |total |net |consolidated )*"
    r"(?:revenue|sales|net sales|accounts receivable))",
    re.IGNORECASE,
)
# A named entity: two or more capitalised words, or one followed by a corporate
# suffix. Deliberately generous -- the point is to measure how many candidates
# survive RESOLUTION, so over-generating here is the conservative direction.
ENTITY_RE = re.compile(
    r"\b([A-Z][A-Za-z&.\-]+(?:\s+[A-Z][A-Za-z&.\-]+){0,4}"
    r"(?:\s+(?:Inc|Corp|Corporation|Company|Co|Ltd|Limited|LLC|LP|PLC|Holdings|Group|Technologies|Systems)\.?)?)\b"
)
SUFFIX_RE = re.compile(
    r"\b(inc|corp|corporation|company|co|ltd|limited|llc|lp|plc|holdings|holding|"
    r"group|international|worldwide|na|nv|sa|ag|kk)\b",
    re.IGNORECASE,
)
# Words that start a sentence or head a section and are never a customer.
STOPWORDS = {
    "the", "we", "our", "this", "these", "those", "item", "note", "for", "in",
    "during", "as", "at", "no", "one", "two", "three", "customer", "customers",
    "revenue", "revenues", "sales", "accounts", "receivable", "united", "states",
    "december", "january", "february", "march", "april", "may", "june", "july",
    "august", "september", "october", "november", "fiscal", "year", "company",
    "consolidated", "financial", "statements", "management", "risk", "factors",
}
MIN_NAMES_WITH_A_LINK = 25
MIN_DISCLOSURE_RATE = 0.40
WINDOW_CHARS = 400          # text around a concentration hit to scan for names


def normalize(name: str) -> str:
    """Collapse a company name to a comparable key."""
    s = name.lower().replace("&", " and ")
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    s = SUFFIX_RE.sub(" ", s)
    return re.sub(r"\s+", " ", s).strip()


def build_name_index(client: EdgarClient) -> dict[str, str]:
    """normalized company name -> ticker, from EDGAR's own registry.

    This is the resolution backbone and also its ceiling: a customer that is
    private, foreign-listed, or referred to by a brand rather than its
    registrant name cannot resolve, no matter how cleanly it was extracted.
    """
    raw = client._get_json(COMPANY_TICKERS_URL)
    index: dict[str, str] = {}
    for entry in raw.values():
        key = normalize(entry.get("title", ""))
        if len(key) >= 3 and key not in index:
            index[key] = entry["ticker"].upper()
    return index


def candidate_names(text: str) -> set[str]:
    """Entity-looking strings near a concentration disclosure."""
    out: set[str] = set()
    for m in CONCENTRATION_RE.finditer(text):
        lo = max(m.start() - WINDOW_CHARS, 0)
        window = text[lo : m.end() + WINDOW_CHARS]
        for cand in ENTITY_RE.findall(window):
            words = cand.split()
            if len(words) == 1 and words[0].lower() in STOPWORDS:
                continue
            if all(w.lower() in STOPWORDS for w in words):
                continue
            out.add(cand.strip(" .,"))
    return out


def latest_10k(client: EdgarClient, cik: int) -> dict | None:
    for f in client.recent_filings(cik):
        if f["form"] == "10-K" and f["primaryDocument"]:
            return f
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=99)
    ap.add_argument("--universe", default="config/universe.csv")
    args = ap.parse_args()

    ua = os.environ.get("SEC_EDGAR_USER_AGENT", "")
    if not ua:
        print("SEC_EDGAR_USER_AGENT is required (SEC fair-access policy)")
        return 2
    client = EdgarClient(ua)

    with open(args.universe) as fh:
        tickers = [r["ticker"].strip() for r in csv.DictReader(fh) if r.get("ticker")]
    tickers = tickers[: args.limit]
    print(f"[0] universe: {len(tickers)} tickers from {args.universe}\n")

    print("[1] building the EDGAR name -> ticker index")
    index = build_name_index(client)
    print(f"    {len(index)} registrant names indexed\n")

    fetched = with_disclosure = 0
    no_cik = no_10k = fetch_failed = 0
    truncated = 0
    all_candidates: Counter = Counter()
    resolved_links: dict[str, set[str]] = {}
    unresolved: Counter = Counter()

    print("[2] scanning the newest 10-K per ticker")
    for i, t in enumerate(tickers, 1):
        cik = client.cik_for(t)
        if cik is None:
            no_cik += 1
            continue
        try:
            filing = latest_10k(client, cik)
            if filing is None:
                no_10k += 1
                continue
            raw = client.filing_text(cik, filing["accessionNumber"], filing["primaryDocument"])
            if len(raw) >= 800_000:
                truncated += 1
            text = strip_html(raw)
            fetched += 1
        except Exception as exc:  # noqa: BLE001
            fetch_failed += 1
            print(f"    {t}: fetch failed ({type(exc).__name__})")
            continue

        # strip_html lowercases, so re-read the raw HTML for capitalisation.
        plain = re.sub(r"<[^>]+>", " ", raw)
        plain = re.sub(r"\s+", " ", plain)
        if not CONCENTRATION_RE.search(text):
            continue
        with_disclosure += 1

        names = candidate_names(plain)
        all_candidates[t] = len(names)
        for n in names:
            key = normalize(n)
            hit = index.get(key)
            if hit and hit != t:
                resolved_links.setdefault(t, set()).add(hit)
            elif len(key) >= 4:
                unresolved[n] += 1
        if i % 10 == 0:
            print(f"    ...{i}/{len(tickers)}")

    linked = {t: v for t, v in resolved_links.items() if v}
    total_links = sum(len(v) for v in linked.values())
    rate = with_disclosure / fetched if fetched else 0.0

    print("\n[3] funnel")
    print(f"    tickers attempted                    {len(tickers)}")
    print(f"      no CIK                             {no_cik}")
    print(f"      no 10-K in the feed                {no_10k}")
    print(f"      fetch failed                       {fetch_failed}")
    print(f"    10-Ks fetched                        {fetched}")
    print(f"      hit the 800k char cap (truncated)  {truncated}")
    print(f"    with a concentration disclosure      {with_disclosure}  ({rate:.0%})")
    print(f"    candidate names extracted            {sum(all_candidates.values())}")
    print(f"    names RESOLVED to a ticker           {total_links}")
    print(f"    universe names with >=1 usable link  {len(linked)}")

    if linked:
        print("\n[4] sample of resolved links")
        for t, cs in list(sorted(linked.items()))[:15]:
            print(f"    {t:6s} -> {', '.join(sorted(cs))}")

    if unresolved:
        print("\n[5] most common UNRESOLVED candidates (the ceiling on this approach)")
        for name, n in unresolved.most_common(20):
            print(f"    {n:4d}  {name}")

    print("\n[6] verdict against the pre-committed stop conditions")
    ok = True
    if rate < MIN_DISCLOSURE_RATE:
        print(f"    STOP: only {rate:.0%} of 10-Ks had a parseable disclosure "
              f"(needed >= {MIN_DISCLOSURE_RATE:.0%}). The disclosure itself is "
              f"not reliably extractable; the rest is moot.")
        ok = False
    if len(linked) < MIN_NAMES_WITH_A_LINK:
        print(f"    STOP: only {len(linked)} names have a resolved customer link "
              f"(needed >= {MIN_NAMES_WITH_A_LINK}). The column would be "
              f"near-constant and the degenerate guard would drop it, exactly as "
              f"happened to events (55 of 66 tied) and insider buying (35 of 66).")
        ok = False
    if ok:
        print(f"    PROCEED: {len(linked)} names carry {total_links} resolved links "
              f"from {rate:.0%} disclosure coverage. A signal is worth building.")
    print("\n    Whatever this says, it is the finding. Record it either way.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
