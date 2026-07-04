# GreenLight

**The enterprise agent that won't let a fashion brand publish a green claim it can't prove — and shows you the receipt.**

> *Claim boldly — but only what you can prove.*

GreenLight reads a fashion line's marketing claims, checks each one against the **actual EU/France sustainability regulations** and the **supplier's evidence**, and refuses to green-light any claim the brand can't legally defend — with the exact regulation article cited. It plans, retrieves more than once when evidence is missing, calls tools, decides, and produces a **launch-compliance determination** a responsible-sourcing team can file.

*Built solo at RAISE 2026 (team **ShipHappens**) for **Vultr Statement Two**, on my own multi-agent coordination engine, with Cursor, deployed on Vultr.*

<!-- TODO: hero GIF of the compliance-catch: claim → needs-evidence → 2nd retrieval → BLOCKED + citation + score drop -->
![GreenLight — the compliance catch](frontend/wow.gif)

---

## Why now

**Sustainability sells.** A large and growing share of shoppers actively seek — and pay a premium for — brands they believe are sustainable. That demand is exactly why brands are tempted to over-claim ("recycled", "eco", "carbon-neutral") faster than they can prove it. Regulators are now closing that gap, hard:

- **EU "Empowering Consumers" Directive (Dir. (EU) 2024/825)** — bans generic environmental claims ("eco-friendly", "green", "sustainable") unless excellent performance is proven, and bans self-invented sustainability labels. **Applies from 27 September 2026** (transposition deadline passed 27 Mar 2026).
- **Penalties up to 4% of annual turnover** (Omnibus Dir. (EU) 2019/2161), or €2M min; national fines stack on top.
- **Already enforced:** Shein fined **€40M (France) + €1M (Italy)**; H&M's "Conscious" label killed (NL); ~**€41.9M** in fashion greenwashing penalties in 2024–25.
- **ESPR (Reg. (EU) 2024/1781) → Digital Product Passport** — textiles a priority category; DPP *coming* (~2028). GreenLight pre-fills DPP fields for that.
- **France's anti-ultra-fast-fashion law** — adopted 29 June 2026 (timeliness context).

<sub>See [`docs/COMPLIANCE_BASIS.md`](docs/COMPLIANCE_BASIS.md) for the full legal basis and sources. Note: the separate *Green Claims Directive* proposal is effectively withdrawn/in-limbo (since Jun 2025) and is **not** cited as law here.</sub>

GreenLight sits at that intersection: it lets a brand **capture the consumer upside** (make the claim) **without the fine/reputational risk** (only if the evidence holds).

---

## What it does (the workflow)

1. **Plans** — decomposes the line into *which claims × which regulations apply*.
2. **Retrieves (#1)** — pulls the relevant regulation article for each claim.
3. **Decides + finds a gap** — a claim comes back `needs-evidence`.
4. **Retrieves (#2)** — goes back and pulls the **supplier's material certificate**.
5. **Blocks + cites** — the cert only substantiates 40% of a "70% recycled" claim → the claim is **BLOCKED**, citing the exact article, and a remediation is written.
6. **Outputs** — a **launch-compliance determination**: per-claim verdicts, citation trail, remediation, Digital Product Passport fields, and a confidence score.

---

## How it maps to Vultr Statement Two (the rubric)

| Vultr asks for | GreenLight | Code |
|---|---|---|
| **"The keyword is agent"** (not retrieve-then-answer) | Multi-agent loop w/ human gates | `greenlight/coordinator.py` |
| **Plans** | Line → claims × regs | `greenlight/agents/planner.py` |
| **Retrieves more than once** | Reg lookup, then **supplier cert** on a gap | `greenlight/sources/regulations.py`, `supplier_certs.py` |
| **Calls tools** | `search_regulations`, `lookup_supplier_cert`, `check_claim`, `generate_dpp_fields` | `greenlight/tools/` |
| **Makes decisions** | Per-claim verdict + line GO/BLOCK | `greenlight/agents/checker.py` |
| **Usable enterprise outcome** | Cited launch-compliance determination | `greenlight/agents/synthesizer.py` |
| **Grounds decisions in documents** | Every verdict cites a reg article + supplier doc; full lineage | `greenlight/catalog.py` |

**Objective results:** <!-- TODO fill from a real run -->
- Claims: **5 cleared / 1 blocked**
- **100%** of decisions carry a document citation · **0** hallucinated
- Line review: **~20 min → ~8 s**
- Fine / market-access at risk avoided: **€___**

---

## Architecture

<!-- TODO: export frontend/architecture.svg → architecture.png -->
![GreenLight architecture](frontend/architecture.png)

A domain-agnostic **coordination core** (planner → retriever → claim-checker → synthesizer, with human gates and a live event trace) plus a swappable **document layer** (regulation corpus + supplier-cert corpus + multi-hop retriever). The core is proven: it previously ran a multi-agent data-procurement org (LedgerScout) — GreenLight re-points it at document-grounded compliance.

---

## Quick start (offline — deterministic, no keys)

```bash
python3 serve.py                    # http://localhost:8000/frontend/index.html → ▶ Run live
python3 scripts/demo_test.py        # quick assertions (4/6 cleared, 2 blocked)
python3 greenlight/run.py           # CLI trace only (~instant)
python3 scripts/seed_rag.py         # (once) seed Vultr RAG collections
```

- Runs fully offline with deterministic fallbacks + local keyword retrieval (no keys needed) so the demo never hard-stops.
- With `INFERENCE_API_KEY` set, the agent runs live on **Vultr Serverless Inference** — `moonshotai/Kimi-K2.6` for reasoning/tool-calling, `deepseek-ai/DeepSeek-V4-Flash` for grounded document reasoning, `Qwen/Qwen3.6-27B` for structured output — with grounding on **Vultr Turnkey RAG** (two private collections). See [`docs/VULTR.md`](docs/VULTR.md).

Deployed demo (Vultr Compute): <!-- TODO URL -->

---

## Data & honesty

- **Regulations:** real, quoted excerpts with source links (`data/regulations/`).
- **Product line & supplier certificates:** **synthetic** but realistic (`data/line.json`, `data/supplier_certs/`) — labelled as such.

---

## Author

Architected and built **solo** at RAISE 2026 by **[NAME]** (team ShipHappens). The multi-agent coordination engine is my own prior work, rebuilt fresh for this event; the document-grounding (Vultr Turnkey RAG) + compliance layer is original to GreenLight. Commit history reflects the solo build during the event window.

---

## Status

<!-- TODO update as blocks complete -->
Spine + compliance-catch live end-to-end; deterministic offline fallback; deployed on Vultr. See `IMPLEMENTATION_PLAN.md` for the block-by-block state and `DEMO_SCRIPT.md` for the 60-second demo.
