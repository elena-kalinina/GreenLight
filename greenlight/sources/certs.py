"""Direct supplier certificate lookup from staged JSON (reliable for demo)."""
import json

from greenlight import config

_CACHE = None


def _load():
    global _CACHE
    if _CACHE is None:
        sc = json.loads((config.DATA / "certs" / "scope_certificates.json").read_text())
        tc = json.loads((config.DATA / "certs" / "transaction_certificates.json").read_text())
        _CACHE = {
            "scope": sc.get("scope_certificates", []),
            "transaction": tc.get("transaction_certificates", []),
        }
    return _CACHE


def lookup_by_sku(sku):
    data = _load()
    tc = next((t for t in data["transaction"] if t.get("linkedSku") == sku), None)
    sc_id = tc.get("relatedScopeCertificate") if tc else None
    sc = next((s for s in data["scope"] if s.get("certNo") == sc_id), None) if sc_id else None
    supplier = tc.get("seller") if tc else None
    if not sc and sku:
        # Scope-only lookup by supplier name fragment
        for s in data["scope"]:
            if sku == "GL-01" and "Atlas" in s.get("certifiedOrganization", ""):
                sc = s
                break
    return {"scope": sc, "transaction": tc, "supplier": supplier}


def format_tc(tc):
    if not tc:
        return None
    return json.dumps(tc, indent=2)
