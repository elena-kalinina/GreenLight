"""Per-claim verdict — regulation retrieval #1, cert retrieval #2 on gap, calc tool."""
from greenlight.engine.ledger import ClaimCheck
from greenlight.sources import vultr_rag
from greenlight.tools import verify_recycled_content

GENERIC_CITATION = (
    "Directive (EU) 2024/825 (ECGT) · Annex I point 4a — generic environmental claim "
    "without recognised excellent environmental performance"
)


def check_claim(check: ClaimCheck, events):
    events.emit("claim", "ClaimChecker", claim_id=check.claim_id, text=check.text, status="checking")
    check.status = "checking"

    reg = vultr_rag.search_regulations(check.text, check.claim_type)
    if reg.get("chunk"):
        check.regulation = reg["citation"]
        check.citation = reg["chunk"][:320]
        events.emit(
            "retrieval",
            "ClaimChecker",
            claim_id=check.claim_id,
            retrieval=1,
            text="regulation retrieval #1",
            source=reg.get("source"),
            live=reg.get("live", False),
            citation=check.regulation,
        )

    if check.claim_type == "generic_environmental":
        check.status = "blocked"
        check.regulation = GENERIC_CITATION
        check.citation = (
            "Making a generic environmental claim for which the trader is not able to demonstrate "
            "recognised excellent environmental performance relevant to the claim. "
            "Examples: 'eco-friendly', 'green', 'sustainable'."
        )
        check.remediation = "Remove generic tag or prove recognised excellent environmental performance (EU Ecolabel / EN ISO 14024)."
        events.emit(
            "claim",
            "ClaimChecker",
            claim_id=check.claim_id,
            status="blocked",
            text=check.remediation,
            citation=check.citation,
        )
        return check

    if check.claim_type == "recycled_content":
        check.status = "needs-evidence"
        events.emit(
            "claim",
            "ClaimChecker",
            claim_id=check.claim_id,
            status="needs-evidence",
            text="Quantified claim — evidence not yet substantiated; retrieving supplier certificate",
        )
        cert = vultr_rag.lookup_supplier_cert(check.sku, check.meta.get("attribute"))
        events.emit(
            "retrieval",
            "ClaimChecker",
            claim_id=check.claim_id,
            retrieval=2,
            text="supplier cert retrieval #2 (multi-hop)",
            citation=cert.get("citation"),
            scope_valid=cert.get("scope_valid"),
            source=cert.get("source"),
            live=cert.get("live", False),
        )
        check.evidence = cert.get("cert")
        tc = cert.get("transaction")
        claimed = check.meta.get("claimed_recycled_pct", 0)
        payload = tc if tc else (check.evidence or "{}")
        v = verify_recycled_content(claimed, payload)
        events.emit("tool", "verify_recycled_content", claim_id=check.claim_id, result=v)
        if cert.get("scope_valid") and not v["passes"]:
            check.status = "blocked"
            check.regulation = (
                "Directive (EU) 2024/825 (ECGT) · substantiation + Annex I point 4b"
            )
            check.citation = (
                f"Scope Certificate valid, but Transaction Certificate {cert.get('citation', '')} "
                f"covers only {v['verified_pct']}% — cannot substantiate {claimed}% claim."
            )
            check.remediation = (
                f"Correct marketing to {v['verified_pct']}% recycled polyester (GRS-certified); "
                f"attach TC {cert.get('citation', '')}."
            )
        elif v["passes"]:
            check.status = "substantiated"
        else:
            check.status = "blocked"
            check.remediation = "No valid Transaction Certificate for this shipment."
        events.emit(
            "claim",
            "ClaimChecker",
            claim_id=check.claim_id,
            status=check.status,
            citation=check.citation,
            remediation=check.remediation,
        )
        return check

    if check.claim_type == "certified_material":
        cert = vultr_rag.lookup_supplier_cert(check.sku, check.meta.get("attribute"))
        tc = cert.get("transaction")
        if tc and tc.get("status") == "VALID" and tc.get("linkedSku") == check.sku:
            check.status = "substantiated"
            check.evidence = cert.get("citation")
            check.citation = f"Scope + Transaction certificate substantiate {check.text}."
        else:
            check.status = "substantiated"
            check.evidence = "Certification scheme named; no environmental generic claim under ECGT."
            check.citation = "Specific certified-material claim with named scheme (not a generic environmental claim)."

    elif check.claim_type == "specific_verifiable":
        check.status = "substantiated"
        check.citation = "Specific, verifiable performance claim — not a generic environmental claim under ECGT."
    else:
        check.status = "substantiated"

    events.emit(
        "claim",
        "ClaimChecker",
        claim_id=check.claim_id,
        status=check.status,
        citation=check.citation,
    )
    return check
