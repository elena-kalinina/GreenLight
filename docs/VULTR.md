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
| **Agent brain** — planning, decisions, tool-calling | **`kimi-k2-instruct`** | Strong agentic reasoning; the tool-calling–capable model on Vultr Serverless Inference |
| **Grounded document reasoning** (RAG) — "is this claim substantiated by the retrieved clause?" | **`deepseek-r1-distill-llama-70b`** | Reasoning-tuned and RAG-compatible via the Turnkey RAG endpoint |
| **Structured output / summarization** (determination JSON, DPP fields, remediation copy) | **`llama-3.3-70b-instruct-fp8`** | Fast, stable instruction-following for structured/auxiliary output |

> Note: native tool-calling is available on `kimi-k2-instruct`; the managed RAG endpoint is
> used with a RAG-compatible model (`deepseek-r1-distill-llama-70b`). Roles are cleanly split
> so each call uses a model suited to it.

## Endpoints

```bash
# Chat / reasoning (OpenAI-compatible)
curl "https://api.vultrinference.com/v1/chat/completions" -X POST \
  -H "Authorization: Bearer ${INFERENCE_API_KEY}" -H "Content-Type: application/json" \
  --data '{"model":"kimi-k2-instruct","messages":[{"role":"user","content":"..."}]}'

# RAG (grounded on a private collection)
curl "https://api.vultrinference.com/v1/chat/completions/RAG" -X POST \
  -H "Authorization: Bearer ${INFERENCE_API_KEY}" -H "Content-Type: application/json" \
  --data '{"collection":"greenlight-regulations","model":"deepseek-r1-distill-llama-70b",
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
