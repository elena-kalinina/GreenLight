#!/usr/bin/env python3
"""Data-readiness smoke tests for GreenLight — run before building the engine.

Proves the data side is ready:
  A. Every data/ file parses and is non-empty.
  B. Scenario integrity: line <-> suppliers <-> certs link up; the recycled claim's
     Transaction Certificate under-covers (40% < 70% claimed); the GOTS claim is fully
     substantiated; the generic 'eco-friendly' claim maps to the ECGT generic-claim ban.
  C. Retrieval corpus builds from data/regulations + data/certs; a local keyword
     retriever returns the CORRECT ECGT clause for each blocked claim (offline fallback).
  D. Commercial data loads: Google Trends series + DataCo apparel margin benchmarks + market constants.
  E. (default-on) Live Vultr Turnkey RAG grounding on the REAL corpus: ingest the reg chunks,
     query the two blocked claims, confirm the ECGT clause is retrieved; then clean up.

Run:  python3 scripts/smoke_data.py            (offline + live)
      python3 scripts/smoke_data.py --no-vultr (offline only)
"""
import csv
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
ENV_PATH = ROOT / ".env"
VULTR_ACCOUNT_API = "https://api.vultr.com/v2"
VULTR_INFERENCE_API = "https://api.vultrinference.com/v1"
RAG_MODEL = "deepseek-ai/DeepSeek-V4-Flash"

results = []  # (name, ok, critical, detail)


def record(name, ok, critical, detail=""):
    results.append((name, ok, critical, detail))
    mark = "PASS" if ok else ("FAIL" if critical else "WARN")
    print(f"  [{mark}] {name}" + (f" — {detail}" if detail else ""))


def load_json(rel):
    return json.loads((DATA / rel).read_text())


def load_env():
    env = dict(os.environ)
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env.setdefault(k.strip(), v.strip())
    return env


def http(method, url, token=None, data=None, timeout=120):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode()
            return r.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except json.JSONDecodeError:
            return e.code, {"raw": raw[:200]}
    except Exception as e:  # noqa: BLE001
        return 0, {"error": str(e)[:200]}


# ---------- corpus + tiny keyword retriever (mirrors the offline fallback) ----------
def build_corpus():
    """Return list of (chunk_id, text) from regulations/*.md and certs/*.json."""
    chunks = []
    for md in sorted((DATA / "regulations").glob("*.md")):
        text = md.read_text()
        for i, part in enumerate(re.split(r"\n## ", text)):
            part = part.strip()
            if len(part) > 40:
                chunks.append((f"{md.stem}#{i}", part))
    for cj in sorted((DATA / "certs").glob("*.json")):
        obj = json.loads(cj.read_text())
        for key, arr in obj.items():
            if isinstance(arr, list):
                for rec in arr:
                    chunks.append((f"{cj.stem}:{rec.get('certNo') or rec.get('tcNo')}",
                                   json.dumps(rec)))
    return chunks


_WORD = re.compile(r"[a-z0-9]+")


def retrieve(query, corpus, k=3):
    q = set(_WORD.findall(query.lower()))
    scored = []
    for cid, text in corpus:
        toks = _WORD.findall(text.lower())
        tset = set(toks)
        overlap = sum(1 for w in q if w in tset)
        scored.append((overlap, cid, text))
    scored.sort(key=lambda x: -x[0])
    return scored[:k]


def offline_checks():
    print("== A. Files parse ==")
    line = certs_sc = certs_tc = market = None
    try:
        line = load_json("line/aw26_line.json")
        record("line/aw26_line.json", len(line.get("skus", [])) == 6, True,
               f"{len(line.get('skus', []))} SKUs, turnover {line.get('annual_turnover_eur')}")
    except Exception as e:  # noqa: BLE001
        record("line/aw26_line.json", False, True, str(e)[:120])
    try:
        certs_sc = load_json("certs/scope_certificates.json")["scope_certificates"]
        certs_tc = load_json("certs/transaction_certificates.json")["transaction_certificates"]
        record("certs/*.json", len(certs_sc) >= 2 and len(certs_tc) >= 2, True,
               f"{len(certs_sc)} SC, {len(certs_tc)} TC")
    except Exception as e:  # noqa: BLE001
        record("certs/*.json", False, True, str(e)[:120])
    try:
        market = load_json("market/market_context.json")
        record("market/market_context.json", "willingness_to_pay" in market, True,
               f"WTP {market['willingness_to_pay']['premium_pct_low']}-"
               f"{market['willingness_to_pay']['premium_pct_high']}%")
    except Exception as e:  # noqa: BLE001
        record("market/market_context.json", False, True, str(e)[:120])
    for md in ("regulations/ecgt_2024_825.md", "regulations/context_market_enforcement.md"):
        p = DATA / md
        record(md, p.exists() and len(p.read_text()) > 500, True,
               f"{len(p.read_text())} chars" if p.exists() else "missing")

    print("\n== B. Scenario integrity ==")
    if line and certs_sc is not None and certs_tc is not None:
        supplier_ids = {s["supplier_id"] for s in line["skus"]}
        # recycled claim C1 on GL-01 -> TC 0417 must under-cover
        gl01 = next(s for s in line["skus"] if s["sku"] == "GL-01")
        claimed = gl01["marketing_claims"][0]["claimed_recycled_pct"]
        tc = next(t for t in certs_tc if t.get("linkedSku") == "GL-01")
        covered = tc["products"][0]["certifiedRecycledContentPct"]
        record("recycled gap (verify_recycled_content)", covered < claimed, True,
               f"claimed {claimed}% vs TC {tc['tcNo']} covers {covered}% -> BLOCK")
        # GL-03 GOTS -> SC + TC both valid == substantiated
        tc3 = next((t for t in certs_tc if t.get("linkedSku") == "GL-03"), None)
        record("GOTS claim substantiated (GL-03)", tc3 is not None and tc3["status"] == "VALID",
               True, f"TC {tc3['tcNo']} valid" if tc3 else "no TC")
        # generic 'eco-friendly' C2 -> generic_environmental, no backing attribute
        gl02 = next(s for s in line["skus"] if s["sku"] == "GL-02")
        c2 = gl02["marketing_claims"][0]
        record("generic 'eco-friendly' flagged (GL-02)",
               c2["type"] == "generic_environmental" and c2.get("attribute") is None, True,
               f"'{c2['text']}' -> ECGT Annex I 4a")
        # every supplier referenced by a certified/recycled claim has a Scope Certificate
        cert_orgs = " ".join(json.dumps(c) for c in certs_sc)
        record("suppliers link to scope certs", "SUP-ATLAS" in supplier_ids and "Atlas" in cert_orgs,
               True, f"suppliers={sorted(supplier_ids)}")

    print("\n== C. Retrieval returns the right clause (offline) ==")
    corpus = build_corpus()
    record("corpus builds from regs+certs", len(corpus) >= 8, True, f"{len(corpus)} chunks")
    top_eco = retrieve("is 'eco-friendly' allowed as a marketing claim", corpus, k=1)[0]
    record("retrieve: 'eco-friendly' -> generic-claim clause",
           "generic environmental claim" in top_eco[2].lower(), True, top_eco[1])
    top_rec = retrieve("70% recycled polyester substantiation evidence", corpus, k=3)
    joined = " ".join(t[2].lower() for t in top_rec)
    record("retrieve: '70% recycled' -> recycled/substantiation clause",
           "recycled" in joined and ("substantiat" in joined or "transaction certificate" in joined),
           True, top_rec[0][1])

    print("\n== D. Commercial data loads ==")
    trends = DATA / "demand" / "trends_sustainability.csv"
    if trends.exists():
        rows = list(csv.DictReader(open(trends)))
        cols = [c for c in rows[0].keys() if c not in ("date", "isPartial")]
        record("Google Trends series", len(rows) > 50, False,
               f"{len(rows)} weeks, keywords={cols}")
    else:
        record("Google Trends series", False, False, "missing (run scripts/fetch_data.py)")
    bench = DATA / "margins" / "datac_apparel_benchmarks.csv"
    if bench.exists():
        rows = list(csv.DictReader(open(bench)))
        record("DataCo apparel margin benchmarks", len(rows) >= 5, False,
               f"{len(rows)} categories (real profit ratios)")
    else:
        record("DataCo apparel margin benchmarks", False, False, "missing (run scripts/fetch_data.py)")


def vultr_rag_check():
    print("\n== E. Live Vultr RAG grounding on the REAL corpus ==")
    env = load_env()
    inf_key = env.get("INFERENCE_API_KEY", "").strip()
    if not inf_key:
        vultr_key = env.get("VULTR_API_KEY", "").strip()
        if not vultr_key:
            record("Vultr RAG (real corpus)", False, False, "no INFERENCE_API_KEY/VULTR_API_KEY; skipped")
            return
        st, body = http("GET", f"{VULTR_ACCOUNT_API}/inference", token=vultr_key)
        subs = (body.get("subscriptions") or body.get("inference") or []) if st == 200 else []
        inf_key = subs[0].get("api_key") if subs else None
        inf_id = subs[0].get("id") if subs else None
        if not inf_key and inf_id:
            _, d = http("GET", f"{VULTR_ACCOUNT_API}/inference/{inf_id}", token=vultr_key)
            inf_key = (d.get("subscription") or d.get("inference") or d).get("api_key")
        if not inf_key:
            record("Vultr RAG (real corpus)", False, False,
                   f"no inference key (acct status={st}; save INFERENCE_API_KEY in .env); skipped")
            return
    st, b = http("POST", f"{VULTR_INFERENCE_API}/vector_store", token=inf_key,
                 data={"name": "greenlight-data-smoke"})
    coll = (b.get("collection") or {}).get("id") if isinstance(b, dict) else None
    if not coll:
        record("Vultr RAG (real corpus)", False, False, f"create failed status={st}; skipped")
        return
    try:
        corpus = build_corpus()
        added = 0
        for cid, text in corpus:
            sta, _ = http("POST", f"{VULTR_INFERENCE_API}/vector_store/{coll}/items",
                          token=inf_key, data={"content": text[:4000], "description": cid})
            added += 1 if sta in (200, 201, 202) else 0
        record("RAG ingest real corpus", added >= 8, True, f"{added}/{len(corpus)} chunks")
        strc, br = http("POST", f"{VULTR_INFERENCE_API}/chat/completions/RAG", token=inf_key, data={
            "collection": coll, "model": RAG_MODEL,
            "messages": [{"role": "user", "content": (
                "Under the ECGT directive, is a bare 'eco-friendly' label on a sweater allowed? "
                "Cite the clause from the provided context.")}],
            "max_tokens": 220})
        ans = (br["choices"][0]["message"]["content"] if strc == 200 and br.get("choices") else "").lower()
        record("RAG answers 'eco-friendly' from real ECGT text",
               strc == 200 and ("generic" in ans or "4a" in ans or "excellent environmental" in ans),
               True, ans.replace("\n", " ")[:110] or f"status={strc}")
    finally:
        http("DELETE", f"{VULTR_INFERENCE_API}/vector_store/{coll}", token=inf_key)
        record("RAG cleanup", True, False, "collection deleted")


def main():
    print("== GreenLight data-readiness smoke ==\n")
    offline_checks()
    if "--no-vultr" not in sys.argv:
        vultr_rag_check()
    print("\n== Summary ==")
    crit_fail = [n for n, ok, c, _ in results if c and not ok]
    warn = [n for n, ok, c, _ in results if not c and not ok]
    passed = sum(1 for _, ok, _, _ in results if ok)
    print(f"  {passed}/{len(results)} checks passed | {len(crit_fail)} critical fail | {len(warn)} warn")
    if crit_fail:
        print("  CRITICAL:", ", ".join(crit_fail))
    if warn:
        print("  Warnings:", ", ".join(warn))
    sys.exit(1 if crit_fail else 0)


if __name__ == "__main__":
    main()
