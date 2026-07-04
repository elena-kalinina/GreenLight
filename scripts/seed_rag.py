#!/usr/bin/env python3
"""Seed Vultr Turnkey RAG collections from data/regulations + data/certs.

Creates (or recreates) two collections and writes IDs to data/rag_collections.json.
Run once before demo recording (or when corpus changes):

    python3 scripts/seed_rag.py

Requires INFERENCE_API_KEY in .env (IP-independent).
"""
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT = DATA / "rag_collections.json"
API = "https://api.vultrinference.com/v1"


def load_env():
    env = {}
    dotenv = ROOT / ".env"
    if dotenv.exists():
        for line in dotenv.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env


def http(method, url, token, data=None):
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {token}"}
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            raw = r.read().decode()
            return r.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode()) if e.read() else {}


def build_chunks():
    reg_chunks, cert_chunks = [], []
    for md in sorted((DATA / "regulations").glob("*.md")):
        text = md.read_text()
        for i, part in enumerate(re.split(r"\n## ", text)):
            part = part.strip()
            if len(part) > 40:
                reg_chunks.append({"content": part[:4000], "description": f"{md.stem}#{i}"})
    for cj in sorted((DATA / "certs").glob("*.json")):
        obj = json.loads(cj.read_text())
        for key, arr in obj.items():
            if isinstance(arr, list):
                for rec in arr:
                    cert_chunks.append({
                        "content": json.dumps(rec, indent=2)[:4000],
                        "description": f"{cj.stem}:{rec.get('certNo') or rec.get('tcNo')}",
                    })
    return reg_chunks, cert_chunks


def seed_collection(token, name, chunks):
    st, body = http("POST", f"{API}/vector_store", token, {"name": name})
    coll_id = (body.get("collection") or {}).get("id")
    if not coll_id:
        print(f"FAIL create {name}: status={st} {body}", file=sys.stderr)
        return None
    added = 0
    for ch in chunks:
        sta, _ = http("POST", f"{API}/vector_store/{coll_id}/items", token, ch)
        if sta in (200, 201, 202):
            added += 1
    print(f"  {name}: {coll_id} ({added}/{len(chunks)} chunks)")
    return coll_id


def main():
    key = load_env().get("INFERENCE_API_KEY", "").strip()
    if not key:
        print("INFERENCE_API_KEY missing in .env — run scripts/save_inference_key.py first", file=sys.stderr)
        sys.exit(1)
    reg_chunks, cert_chunks = build_chunks()
    print(f"Seeding {len(reg_chunks)} regulation + {len(cert_chunks)} cert chunks…")
    reg_id = seed_collection(key, "greenlight-regulations", reg_chunks)
    cert_id = seed_collection(key, "greenlight-supplier-certs", cert_chunks)
    if not reg_id or not cert_id:
        sys.exit(1)
    OUT.write_text(json.dumps({
        "regulations": reg_id,
        "supplier_certs": cert_id,
        "reg_chunks": len(reg_chunks),
        "cert_chunks": len(cert_chunks),
    }, indent=2))
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
