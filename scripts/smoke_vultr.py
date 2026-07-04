#!/usr/bin/env python3
"""Smoke tests for the GreenLight stack on Vultr (+ the Gradium/Groq demo key).

Verifies, before we build:
  1. The account API key reaches Vultr and finds (or creates) a Serverless Inference sub.
  2. The Inference API key lists models and our role models are actually available.
  3. Chat completions work on each role model.
  4. Native tool-calling works on the agent-brain model (Kimi).
  5. Turnkey RAG end-to-end: create collection -> add item -> RAG chat grounded on it -> delete.
  6. The GRADIUM_API_KEY synthesizes speech (Gradium TTS — the demo voiceover).

Run:  python3 scripts/smoke_vultr.py
Never prints secret values. Exits non-zero if any CRITICAL check fails.
"""
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT / ".env"

VULTR_ACCOUNT_API = "https://api.vultr.com/v2"
VULTR_INFERENCE_API = "https://api.vultrinference.com/v1"

# Real Vultr model IDs (verified via /v1/models on 2026-07-04) mapped to their role.
ROLE_MODELS = {
    "brain (plan + tool-calling)": "moonshotai/Kimi-K2.6",
    "RAG reasoning": "deepseek-ai/DeepSeek-V4-Flash",
    "structured output": "Qwen/Qwen3.6-27B",
}
BRAIN_MODEL = ROLE_MODELS["brain (plan + tool-calling)"]
RAG_MODEL = ROLE_MODELS["RAG reasoning"]

results = []  # (name, ok, critical, detail)


def load_env():
    env = dict(os.environ)
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env.setdefault(k.strip(), v.strip())
    return env


def http(method, url, token=None, data=None, timeout=120, extra_headers=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if extra_headers:
        headers.update(extra_headers)
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode()
            return r.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            parsed = json.loads(raw)
        except Exception:
            parsed = {"raw": raw[:300]}
        return e.code, parsed


def http_bytes(method, url, headers=None, data=None, timeout=120):
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, headers=headers or {}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.headers.get("Content-Type", ""), r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get("Content-Type", ""), e.read()


def record(name, ok, critical, detail=""):
    results.append((name, ok, critical, detail))
    mark = "PASS" if ok else ("FAIL" if critical else "WARN")
    print(f"  [{mark}] {name}" + (f" — {detail}" if detail else ""))


def main():
    env = load_env()
    vultr_key = env.get("VULTR_API_KEY", "").strip()
    gradium_key = env.get("GRADIUM_API_KEY", "").strip()

    print("== GreenLight Vultr smoke tests ==\n")
    if not vultr_key:
        record("VULTR_API_KEY present", False, True, "missing in .env/env")
        summarize_and_exit()
    record("VULTR_API_KEY present", True, True, f"len={len(vultr_key)}")

    # ---- 1. Get the inference key: prefer INFERENCE_API_KEY (IP-independent) ----
    inf_key, inf_id = None, None
    direct = env.get("INFERENCE_API_KEY", "").strip()
    if direct:
        inf_key = direct
        record("Inference key from .env (IP-independent)", True, True, f"len={len(direct)}")
    else:
        status, body = http("GET", f"{VULTR_ACCOUNT_API}/inference", token=vultr_key)
        if status == 200:
            subs = body.get("subscriptions") or body.get("inference") or []
            record("Vultr account API reachable", True, True, f"{len(subs)} inference sub(s)")
            if subs:
                inf_id = subs[0].get("id")
                inf_key = subs[0].get("api_key")
                if not inf_key and inf_id:
                    _, d = http("GET", f"{VULTR_ACCOUNT_API}/inference/{inf_id}", token=vultr_key)
                    inf_key = (d.get("subscription") or d.get("inference") or d).get("api_key")
            else:
                st2, b2 = http("POST", f"{VULTR_ACCOUNT_API}/inference", token=vultr_key,
                               data={"label": "greenlight"})
                sub = b2.get("subscription") or b2.get("inference") or (b2 if st2 in (200, 201, 202) else {})
                inf_id, inf_key = sub.get("id"), sub.get("api_key")
                record("Create inference subscription", bool(inf_key), True, f"status={st2}")
        else:
            record("Vultr account API reachable", False, True,
                   f"status={status} body={str(body)[:200]} (tip: save INFERENCE_API_KEY in .env)")

    if not inf_key:
        record("Inference API key obtained", False, True, "cannot proceed")
        summarize_and_exit()
    record("Inference API key obtained", True, True, "via INFERENCE_API_KEY" if direct else f"sub_id={inf_id}")

    # ---- 2. List models; confirm the role models exist ----
    status, body = http("GET", f"{VULTR_INFERENCE_API}/models", token=inf_key)
    available = set()
    if status == 200:
        for m in body.get("data", body.get("models", [])):
            mid = (m.get("id") or m.get("model")) if isinstance(m, dict) else m
            if mid:
                available.add(mid)
        record("List inference models", True, True, f"{len(available)} models")
    else:
        record("List inference models", False, True, f"status={status} {str(body)[:160]}")
    for role, mid in ROLE_MODELS.items():
        record(f"Model available [{role}]: {mid}", mid in available, True,
               "" if mid in available else "NOT in catalog")

    # ---- 3. Chat completions on each role model ----
    for role, mid in ROLE_MODELS.items():
        st, b = http("POST", f"{VULTR_INFERENCE_API}/chat/completions", token=inf_key, data={
            "model": mid,
            "messages": [{"role": "user", "content": "Reply with the single word: READY"}],
            "max_tokens": 16,
        })
        ok = st == 200 and bool(b.get("choices"))
        txt = (b["choices"][0].get("message", {}).get("content", "") or "").strip()[:40] if ok else ""
        record(f"Chat [{role}]: {mid}", ok, True, txt if ok else f"status={st} {str(b)[:140]}")

    # ---- 4. Native tool-calling on the brain model ----
    tools = [{
        "type": "function",
        "function": {
            "name": "search_regulations",
            "description": "Look up the EU regulation clause governing a marketing claim.",
            "parameters": {"type": "object",
                           "properties": {"claim": {"type": "string"}},
                           "required": ["claim"]},
        },
    }]
    st, b = http("POST", f"{VULTR_INFERENCE_API}/chat/completions", token=inf_key, data={
        "model": BRAIN_MODEL,
        "messages": [{"role": "user",
                      "content": "Is the label 'eco-friendly jacket' allowed? Use the tool to check."}],
        "tools": tools, "tool_choice": "auto", "max_tokens": 200,
    })
    calls = b["choices"][0].get("message", {}).get("tool_calls") or [] if st == 200 and b.get("choices") else []
    record(f"Tool-calling [{BRAIN_MODEL}]", bool(calls), True,
           f"{len(calls)} tool_call(s)" if calls else f"status={st} {str(b)[:140]}")

    # ---- 5. Turnkey RAG end-to-end ----
    coll_id = None
    st, b = http("POST", f"{VULTR_INFERENCE_API}/vector_store", token=inf_key,
                 data={"name": "greenlight-smoke"})
    coll_id = (b.get("collection") or {}).get("id") if isinstance(b, dict) else None
    record("RAG: create collection", bool(coll_id), True, f"status={st}" + ("" if coll_id else f" {str(b)[:140]}"))
    if coll_id:
        sta, ba = http("POST", f"{VULTR_INFERENCE_API}/vector_store/{coll_id}/items", token=inf_key, data={
            "content": ("Directive (EU) 2024/825 (ECGT) bans generic environmental claims such as "
                        "'eco-friendly' unless backed by recognised third-party evidence. Applies from 27 Sep 2026."),
            "description": "ECGT generic-claims ban",
        })
        record("RAG: add collection item", sta in (200, 201, 202), True, f"status={sta}" + ("" if sta in (200,201,202) else f" {str(ba)[:120]}"))

        strc, br = http("POST", f"{VULTR_INFERENCE_API}/chat/completions/RAG", token=inf_key, data={
            "collection": coll_id,
            "model": RAG_MODEL,
            "messages": [{"role": "user",
                          "content": "Under ECGT, is a generic 'eco-friendly' label allowed? Answer using the provided context."}],
            "max_tokens": 200,
        })
        ok = strc == 200 and bool(br.get("choices"))
        ans = (br["choices"][0].get("message", {}).get("content", "") or "").strip().replace("\n", " ")[:90] if ok else ""
        record("RAG: grounded chat query", ok, True, ans if ok else f"status={strc} {str(br)[:140]}")

        std, _ = http("DELETE", f"{VULTR_INFERENCE_API}/vector_store/{coll_id}", token=inf_key)
        record("RAG: delete collection (cleanup)", std in (200, 204), False, f"status={std}")

    # ---- 6. Gradium TTS demo key (voiceover for the 1-min video) ----
    if gradium_key:
        st, ctype, payload = http_bytes(
            "POST", "https://api.gradium.ai/api/post/speech/tts",
            headers={"x-api-key": gradium_key, "Content-Type": "application/json"},
            data={"text": "GreenLight blocks the claim.", "voice_id": "YTpq7expH9539ERJ",
                  "output_format": "wav", "only_audio": True})
        ok = st == 200 and "audio" in ctype and len(payload) > 1000
        if ok:
            out = Path("/tmp/greenlight_gradium_smoke.wav")
            out.write_bytes(payload)
            record("Gradium TTS synthesis", True, False, f"{len(payload)} bytes {ctype} -> {out}")
        else:
            record("Gradium TTS synthesis", False, False,
                   f"status={st} ctype={ctype} {payload[:160]!r}")
    else:
        record("GRADIUM_API_KEY present", False, False, "missing (demo only)")

    summarize_and_exit()


def summarize_and_exit():
    print("\n== Summary ==")
    crit_fail = [n for n, ok, crit, _ in results if crit and not ok]
    warn = [n for n, ok, crit, _ in results if not crit and not ok]
    passed = sum(1 for _, ok, _, _ in results if ok)
    print(f"  {passed}/{len(results)} checks passed | {len(crit_fail)} critical fail | {len(warn)} warn")
    if crit_fail:
        print("  CRITICAL FAILURES:", ", ".join(crit_fail))
    if warn:
        print("  Warnings:", ", ".join(warn))
    sys.exit(1 if crit_fail else 0)


if __name__ == "__main__":
    main()
