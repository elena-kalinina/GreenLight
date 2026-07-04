"""Local keyword retrieval over data/regulations + data/certs (offline fallback)."""
import json
import re
from pathlib import Path

from greenlight import config

_WORD = re.compile(r"[a-z0-9]+")


def build_corpus():
    chunks = []
    for md in sorted((config.DATA / "regulations").glob("*.md")):
        text = md.read_text()
        for i, part in enumerate(re.split(r"\n## ", text)):
            part = part.strip()
            if len(part) > 40:
                chunks.append({"id": f"{md.stem}#{i}", "text": part, "source": md.name})
    for cj in sorted((config.DATA / "certs").glob("*.json")):
        obj = json.loads(cj.read_text())
        for key, arr in obj.items():
            if isinstance(arr, list):
                for rec in arr:
                    chunks.append({
                        "id": f"{cj.stem}:{rec.get('certNo') or rec.get('tcNo')}",
                        "text": json.dumps(rec),
                        "source": cj.name,
                    })
    return chunks


def search(query, corpus=None, k=3):
    corpus = corpus or build_corpus()
    q = set(_WORD.findall(query.lower()))
    scored = []
    for ch in corpus:
        toks = set(_WORD.findall(ch["text"].lower()))
        overlap = sum(1 for w in q if w in toks)
        scored.append((overlap, ch))
    scored.sort(key=lambda x: -x[0])
    return [ch for _, ch in scored[:k] if _ > 0] or [scored[0][1]] if scored else []
