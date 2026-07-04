"""Regulation clause lookup — verbatim excerpts from staged ECGT text."""
from pathlib import Path

from greenlight import config

CLAUSE_MAP = {
    "generic_environmental": "PROHIBITION — Annex I point 4a: generic claims without proof",
    "recycled_content": "SUBSTANTIATION principle",
    "partial_claim": "PROHIBITION — Annex I point 4b: partial claim presented as whole",
    "label": "PROHIBITION — Annex I point 2a: unqualified sustainability labels",
}


def _sections():
    text = (config.DATA / "regulations" / "ecgt_2024_825.md").read_text()
    parts = {}
    for block in text.split("\n## "):
        block = block.strip()
        if not block:
            continue
        title = block.split("\n", 1)[0].strip()
        parts[title] = block
    return parts


def clause_for_claim(claim_type, claim_text=""):
    sections = _sections()
    key = CLAUSE_MAP.get(claim_type, "DEFINITION — environmental claim")
    body = sections.get(key, "")
    if not body and claim_type == "generic_environmental":
        body = sections.get(CLAUSE_MAP["generic_environmental"], "")
    cite = "Directive (EU) 2024/825 (ECGT) · EUR-Lex CELEX:32024L0825"
    if claim_type == "generic_environmental":
        cite += " · Annex I point 4a"
    elif claim_type == "recycled_content":
        cite += " · substantiation + Annex I point 4b"
    excerpt = body[:420] if body else f"Environmental claim: {claim_text}"
    return {"citation": cite, "chunk": excerpt, "source": "ecgt_2024_825.md", "clause": key}
