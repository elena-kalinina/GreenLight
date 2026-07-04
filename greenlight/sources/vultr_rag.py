"""Vultr Turnkey RAG — live when seeded, local keyword fallback always available."""
import json
import os
import urllib.error
import urllib.request

from greenlight import config
from greenlight.sources import certs, local_rag, regulations

COLLECTIONS_PATH = config.DATA / "rag_collections.json"
RAG_MODEL = config.MODEL_RAG


def _key():
    return config.inference_key()


def _load_collections():
    if COLLECTIONS_PATH.exists():
        return json.loads(COLLECTIONS_PATH.read_text())
    return {}


def _rag_chat(collection_id, question):
    key = _key()
    if not key or not collection_id:
        return None
    payload = {
        "collection": collection_id,
        "model": RAG_MODEL,
        "messages": [{"role": "user", "content": question}],
        "max_tokens": 300,
    }
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{config.VULTR_INFERENCE_API}/chat/completions/RAG",
        data=body,
        method="POST",
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            data = json.loads(r.read().decode())
        return (data["choices"][0]["message"]["content"] or "").strip()
    except (urllib.error.HTTPError, urllib.error.URLError, KeyError, json.JSONDecodeError):
        return None


def search_regulations(claim_text, claim_type=""):
    live = os.getenv("GREENLIGHT_LIVE_RAG", "0") == "1"
    cols = _load_collections()
    reg_id = cols.get("regulations")
    if live and reg_id:
        q = (
            f"Under Directive (EU) 2024/825 (ECGT), what rule applies to this marketing claim: "
            f"'{claim_text}'? Quote the relevant prohibition or substantiation requirement."
        )
        ans = _rag_chat(reg_id, q)
        if ans:
            base = regulations.clause_for_claim(claim_type or "generic_environmental", claim_text)
            return {
                "citation": base["citation"],
                "chunk": ans[:500],
                "source": "Vultr Turnkey RAG · greenlight-regulations",
                "live": True,
            }
    base = regulations.clause_for_claim(
        claim_type if claim_type in regulations.CLAUSE_MAP else "generic_environmental",
        claim_text,
    )
    hits = local_rag.search(f"regulation {claim_text} {claim_type}")
    if hits:
        base["chunk"] = hits[0]["text"][:500]
        base["source"] = hits[0]["source"]
    base["live"] = False
    return base


def lookup_supplier_cert(sku, attribute=None):
    live = os.getenv("GREENLIGHT_LIVE_RAG", "0") == "1"
    cols = _load_collections()
    cert_id = cols.get("supplier_certs")
    pack = certs.lookup_by_sku(sku)
    tc = pack.get("transaction")
    sc = pack.get("scope")

    if live and cert_id:
        q = (
            f"For SKU {sku}, what does the supplier Transaction Certificate show for "
            f"{attribute or 'certified material'}? Does the Scope Certificate substantiate "
            f"a specific shipment claim, or only facility qualification?"
        )
        ans = _rag_chat(cert_id, q)
        if ans:
            return {
                "cert": certs.format_tc(tc) or ans[:800],
                "citation": f"TC {tc['tcNo']}" if tc else "supplier-certs RAG",
                "scope_valid": sc is not None and sc.get("status") == "VALID",
                "transaction": tc,
                "source": "Vultr Turnkey RAG · greenlight-supplier-certs",
                "live": True,
                "rag_answer": ans[:400],
            }

    if tc:
        return {
            "cert": certs.format_tc(tc),
            "citation": f"TC {tc['tcNo']} · {tc.get('verificationUrl', '')}",
            "scope_valid": sc is not None and sc.get("status") == "VALID",
            "scope_cert": sc.get("certNo") if sc else None,
            "transaction": tc,
            "source": "transaction_certificates.json",
            "live": False,
        }
    hits = local_rag.search(f"transaction certificate {sku} {attribute or ''}")
    return {
        "cert": hits[0]["text"][:800] if hits else None,
        "citation": hits[0]["id"] if hits else None,
        "live": False,
    }
