#!/usr/bin/env python3
"""Reproducible fetch of the REAL external datasets GreenLight uses.

Downloads/derives (idempotent):
  1. DataCo Smart Supply Chain (real order-item profit/discount/price) -> data/margins/
     and a small committed apparel/footwear benchmark CSV.
  2. Google Trends interest-over-time for sustainability keywords -> data/demand/ (real signal).

NOT fetched here (manual, form-gated): Visuelle 2.0 -> see data/README.md.
The scenario files (data/line, data/certs) are authored, not regenerated.

Run:  python3 scripts/fetch_data.py
Deps for trends:  python3 -m pip install --user pytrends-modern
"""
import csv
import collections
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MARGINS = ROOT / "data" / "margins"
DEMAND = ROOT / "data" / "demand"
DATACO_URL = ("https://raw.githubusercontent.com/devkoustavdas/"
              "supply-chain-and-sales-analysis/main/DataCoSupplyChainDataset.csv")
DATACO_RAW = MARGINS / "DataCoSupplyChainDataset.csv"  # gitignored (large)
APPAREL_KEEP = ("apparel", "clothing", "footwear", "accessories", "cleats")
TREND_KEYWORDS = ["sustainable fashion", "recycled polyester", "organic cotton"]
ETHICAL_TREND_KEYWORDS = ["cruelty free fashion", "responsible wool", "vegan fashion"]


def fetch_dataco():
    MARGINS.mkdir(parents=True, exist_ok=True)
    if not DATACO_RAW.exists():
        print(f"Downloading DataCo -> {DATACO_RAW} (~96MB) ...")
        urllib.request.urlretrieve(DATACO_URL, DATACO_RAW)
    agg = collections.defaultdict(lambda: {"n": 0, "pr": 0.0, "dr": 0.0, "pz": 0.0})
    with open(DATACO_RAW, encoding="latin-1") as f:
        for row in csv.DictReader(f):
            c = row.get("Category Name", "").strip()
            if not c or not any(k in c.lower() for k in APPAREL_KEEP):
                continue
            a = agg[c]
            a["n"] += 1

            def fl(k):
                try:
                    return float(row.get(k, "") or 0)
                except ValueError:
                    return 0.0
            a["pr"] += fl("Order Item Profit Ratio")
            a["dr"] += fl("Order Item Discount Rate")
            a["pz"] += fl("Order Item Product Price")
    out = []
    for c, a in sorted(agg.items(), key=lambda x: -x[1]["n"]):
        n = a["n"]
        out.append({"category": c, "n_orders": n,
                    "avg_profit_ratio": round(a["pr"] / n, 4),
                    "avg_discount_rate": round(a["dr"] / n, 4),
                    "avg_unit_price_usd": round(a["pz"] / n, 2)})
    bench = MARGINS / "datac_apparel_benchmarks.csv"
    with open(bench, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0].keys()))
        w.writeheader()
        w.writerows(out)
    print(f"Wrote {bench} ({len(out)} categories)")


def fetch_trends():
    DEMAND.mkdir(parents=True, exist_ok=True)
    try:
        from pytrends_modern import TrendReq
    except ImportError:
        print("pytrends-modern not installed; skipping trends. "
              "Install: python3 -m pip install --user pytrends-modern")
        return
    p = TrendReq(hl="en-US", tz=0)
    p.build_payload(TREND_KEYWORDS, timeframe="today 5-y", geo="")
    df = p.interest_over_time()
    out = DEMAND / "trends_sustainability.csv"
    df.to_csv(out)
    print(f"Wrote {out} ({df.shape[0]} weekly rows, {list(df.columns)})")


def fetch_ethical_trends():
    DEMAND.mkdir(parents=True, exist_ok=True)
    try:
        from pytrends_modern import TrendReq
    except ImportError:
        print("pytrends-modern not installed; skipping ethical trends.")
        return
    p = TrendReq(hl="en-US", tz=0)
    p.build_payload(ETHICAL_TREND_KEYWORDS, timeframe="today 5-y", geo="")
    df = p.interest_over_time()
    out = DEMAND / "trends_ethical.csv"
    df.to_csv(out)
    print(f"Wrote {out} ({df.shape[0]} weekly rows, {list(df.columns)})")


if __name__ == "__main__":
    fetch_dataco()
    fetch_trends()
    fetch_ethical_trends()
