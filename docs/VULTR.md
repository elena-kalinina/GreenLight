# Running on Vultr

GreenLight runs end-to-end on Vultr — reasoning, document grounding, and hosting.

## Products used

| Product | Role |
|---|---|
| **Vultr Serverless Inference** | The agent's reasoning + structured output (OpenAI-compatible API) |
| **Vultr Turnkey RAG** | Document grounding — private vector-store collections the agent retrieves from |
| **Vultr Compute** | Hosts the web app (`serve.py`) and the UI |

## Model roles

We use the right model for each job rather than one model for everything:

| Job | Model | Why |
|---|---|---|
| **Agent brain** — planning, decisions, tool-calling | **`moonshotai/Kimi-K2.6`** | Strong agentic reasoning; native tool-calling verified on Vultr Serverless Inference |
| **Grounded document reasoning** (RAG) — "is this claim substantiated by the retrieved clause?" | **`deepseek-ai/DeepSeek-V4-Flash`** | Reasoning-tuned and verified against the Turnkey RAG endpoint |
| **Structured output** (reserved — DPP fields, remediation copy) | **`Qwen/Qwen3.6-27B`** | Smoke-tested on Vultr; **not wired** in the demo pipeline |

> Model IDs are the exact catalog names returned by `GET /v1/models` and verified end-to-end
> (chat, tool-calling, and grounded RAG) on 2026-07-04. Roles are cleanly split so each call
> uses a model suited to it. Embeddings for the vector store are handled by Vultr's own
> `vultr/VultronRetriever*` models automatically.
>
> **Launch determination:** memo text comes from Kimi's `finalize_determination` tool call;
> €-metrics are computed from tool outputs (`greenlight/agents/tooling.py`), with a
> deterministic fallback in `greenlight/agents/determination.py`. Qwen is listed in
> `greenlight/config.py` as `MODEL_STRUCTURED` for future auxiliary structured output but is
> not invoked at runtime today.

## Endpoints

```bash
# Chat / reasoning (OpenAI-compatible)
curl "https://api.vultrinference.com/v1/chat/completions" -X POST \
  -H "Authorization: Bearer ${INFERENCE_API_KEY}" -H "Content-Type: application/json" \
  --data '{"model":"moonshotai/Kimi-K2.6","messages":[{"role":"user","content":"..."}]}'

# RAG (grounded on a private collection)
curl "https://api.vultrinference.com/v1/chat/completions/RAG" -X POST \
  -H "Authorization: Bearer ${INFERENCE_API_KEY}" -H "Content-Type: application/json" \
  --data '{"collection":"greenlight-regulations","model":"deepseek-ai/DeepSeek-V4-Flash",
           "messages":[{"role":"user","content":"..."}]}'
```

## RAG collections (the document grounding)

Two private Turnkey RAG collections back the multi-hop retrieval:
1. `greenlight-regulations` — regulation excerpts (see `COMPLIANCE_BASIS.md`) → **retrieval #1**.
2. `greenlight-supplier-certs` — supplier Scope/Transaction certificates → **retrieval #2**.

The on-screen citation is the retrieved chunk, so grounded verdicts trace to a document.

## Deployment

- App (`serve.py` + UI) runs on a small **Vultr Compute** instance; the LLM/RAG run on
  Serverless Inference.
- `INFERENCE_API_KEY` is provided via environment; never committed.
- A deterministic offline fallback (cached responses + local keyword retrieval over the same
  corpus) keeps the app runnable without network/keys.
