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


def lookup_by_sku(sku, attribute=None):
    data = _load()
    tcs = [t for t in data["transaction"] if t.get("linkedSku") == sku]
    tc = _pick_tc(tcs, attribute)
    sc_id = tc.get("relatedScopeCertificate") if tc else None
    sc = next((s for s in data["scope"] if s.get("certNo") == sc_id), None) if sc_id else None
    supplier = tc.get("seller") if tc else None
    if not sc and sku:
        for s in data["scope"]:
            if sku == "GL-01" and "Atlas" in s.get("certifiedOrganization", ""):
                if attribute == "rds_down_fill" and "RDS" in s.get("standard", ""):
                    sc = s
                    break
                if attribute in (None, "recycled_polyester") and "GRS" in s.get("standard", ""):
                    sc = s
                    break
            if sku == "GL-02" and "Nova" in s.get("certifiedOrganization", "") and "RWS" in s.get("standard", ""):
                sc = s
                break
    return {"scope": sc, "transaction": tc, "supplier": supplier}


def _pick_tc(tcs, attribute):
    if not tcs:
        return None
    if attribute == "rds_down_fill":
        for t in tcs:
            if "RDS" in t.get("standard", ""):
                return t
    if attribute in (None, "recycled_polyester"):
        for t in tcs:
            if "GRS" in t.get("standard", ""):
                return t
    if attribute == "rws_wool":
        for t in tcs:
            if "RWS" in t.get("standard", ""):
                return t
    if attribute == "organic_cotton":
        for t in tcs:
            if "GOTS" in t.get("standard", ""):
                return t
    return tcs[0]


def format_tc(tc):
    if not tc:
        return None
    return json.dumps(tc, indent=2)
