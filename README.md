# GreenLight

**The enterprise agent that decides whether to green-light a fashion line — weighing sustainability demand upside against compliance risk, and blocking any claim the brand can't prove.**

> *Claim boldly — but only what you can prove.*

GreenLight is a **line-launch decision agent** for fashion retail. It forecasts the commercial upside of a season's sustainability positioning (demand, market size, margins), then checks every marketing claim against **real EU regulations** and **supplier evidence**. Claims that can't be substantiated are blocked with the exact regulation cited. The output is a **launch determination** a responsible-sourcing team can file: recommendation, per-claim verdicts, €-exposure avoided, and a confidence score.

It plans, calls tools across **multiple data types**, retrieves documents more than once when evidence is missing, and aggregates commercial upside vs fine exposure into one decision.

*Built solo at RAISE 2026 (team **ShipHappens**) for **Vultr Statement Two**, on Vultr Serverless Inference + Turnkey RAG, with Cursor.*

<!-- TODO: hero GIF of the compliance-catch: claim → needs-evidence → 2nd retrieval → BLOCKED + citation + score drop -->
![GreenLight — line launch agent](frontend/wow.gif)

---

## Why now — two engines

**1. Consumer pull (commercial).** Shoppers pay a premium for brands they believe are sustainable — sustainable fashion is a **~$11B market in 2026** (10.8% CAGR), and **9–15% willingness-to-pay** for verified certifications (McKinsey/BoF). That upside is why brands over-claim faster than they can prove.

**2. Regulatory crackdown (compliance).**
- **Directive (EU) 2024/825 (ECGT)** — bans generic claims ("eco-friendly", "green", "sustainable") without proof; **applies 27 Sep 2026**.
- **Penalties up to 4% of annual turnover** (Omnibus 2019/2161).
- **Shein €40M** (France DGCCRF, Jul 2025) for unsubstantiated environmental claims; H&M "Conscious" killed (NL).

GreenLight sits at the intersection: **capture the upside, drop only what you can't prove.**

<sub>Legal basis: [`docs/COMPLIANCE_BASIS.md`](docs/COMPLIANCE_BASIS.md). The *Green Claims Directive* proposal is withdrawn/in limbo — **not cited as law**.</sub>

---

## What it does (the workflow)

### Commercial layer (real data)
1. **`forecast_demand()`** — next-season demand index from **real Google Trends** (261 weeks: *sustainable fashion*, *recycled polyester*, *organic cotton*).
2. **`market_context()`** — cited market size + willingness-to-pay premium from public reports.
3. **`project_margin()`** — line contribution from per-SKU economics + **DataCo apparel margin benchmarks** (real profit ratios).
4. **`compute_risk_exposure()`** — fine exposure cap at **≤4% turnover** (€80M on a €2B brand).

### Compliance layer (document-grounded — the wow)
5. **Plans** — decomposes the AW26 line into commercial steps + *claims × regulations*.
6. **Retrieves (#1)** — regulation clause for each claim (Vultr Turnkey RAG + local fallback).
7. **Decides + finds a gap** — `"70% recycled polyester"` → `needs-evidence`.
8. **Retrieves (#2)** — pulls the **supplier Transaction Certificate** (Scope Cert valid, TC covers only **40%**).
9. **`verify_recycled_content()`** — recalculates claimed % vs TC coverage → **BLOCKED** + ECGT citation + remediation.
10. **Aggregates** → **GREEN-LIGHT WITH CONDITIONS**: net upside vs €-exposure avoided, confidence score.

---

## How it maps to Vultr Statement Two (the rubric)

| Vultr asks for | GreenLight | Code |
|---|---|---|
| **Agent** (not retrieve-then-answer) | Multi-step loop w/ human gates + live trace | `greenlight/engine/coordinator.py` |
| **Plans** | Commercial assessment + claims × regs | `greenlight/agents/planner.py` |
| **Aggregates across data types** | Regulations + certs + Trends + margins + market constants | `greenlight/tools/` + `data/` |
| **Predicts** | `forecast_demand()` → next-season demand index | `greenlight/tools/__init__.py` |
| **Retrieves more than once** | Reg lookup (#1), then **supplier cert** (#2) on gap | `greenlight/sources/vultr_rag.py` |
| **Calls tools** | `forecast_demand`, `market_context`, `project_margin`, `search_regulations`, `lookup_supplier_cert`, `verify_recycled_content`, `compute_risk_exposure` | `greenlight/tools/` |
| **Makes decisions** | Per-claim verdict + **launch recommendation** | `greenlight/agents/claim_checker.py`, `determination.py` |
| **Usable enterprise outcome** | Cited line-launch determination | `greenlight/agents/determination.py` |
| **Grounds in documents** | Every blocked claim cites ECGT + supplier doc | `data/regulations/`, `data/certs/` |

**Objective results (demo run on Élan Studio AW26):**
- Claims: **4 substantiated / 2 blocked** (C1 recycled gap, C2 generic "eco-friendly")
- **100%** of decisions carry a document citation · **0** hallucinated compliance
- Demand index from real Google Trends · line contribution **€5.1M** · up to **€80M** exposure avoided
- **Confidence 0.67** · recommendation: **GREEN-LIGHT WITH CONDITIONS**

---

## Architecture

![GreenLight architecture](frontend/architecture.png)

<sub>Vector source: [`frontend/architecture.svg`](frontend/architecture.svg)</sub>

**Coordination engine** (planner → commercial tools → multi-hop retrieval → claim checker → aggregator) with **human gates** and **SSE event trace** to the UI. **Document layer:** two Vultr Turnkey RAG collections (`greenlight-regulations`, `greenlight-supplier-certs`) seeded from `data/`, with deterministic local keyword fallback so the demo never hard-stops.

Models on Vultr Serverless Inference: `moonshotai/Kimi-K2.6` (brain), `deepseek-ai/DeepSeek-V4-Flash` (RAG reasoning), `Qwen/Qwen3.6-27B` (structured output). Details: [`docs/VULTR.md`](docs/VULTR.md).

---

## Quick start

```bash
python3 serve.py                    # http://localhost:8000/frontend/index.html → ▶ Run live
python3 scripts/demo_test.py        # assertions: 4/6 cleared, 2 blocked
python3 greenlight/run.py           # CLI trace (~instant)
python3 scripts/smoke_data.py       # data + retrieval integrity (17 checks)
python3 scripts/seed_rag.py         # (once) seed Vultr Turnkey RAG collections
```

Runs **fully offline** with local retrieval over the same corpus (no keys needed). With `INFERENCE_API_KEY` in `.env`, live Vultr inference + RAG are available (`GREENLIGHT_LIVE_RAG=1` for live collections; off by default for demo speed).

Deployed demo (Vultr Compute): <!-- TODO URL -->

---

## Data & honesty

| Layer | Source | Real / synthetic |
|---|---|---|
| **Regulations** | ECGT (EU) 2024/825 verbatim excerpts | **Real** ([EUR-Lex](https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32024L0825)) |
| **Enforcement context** | Shein €40M, 4% penalty, recycled-polyester baseline | **Real, cited** |
| **Demand signal** | Google Trends CSV (261 weeks, 3 keywords) | **Real** (`data/demand/trends_sustainability.csv`) |
| **Margins** | DataCo Smart Supply Chain → apparel benchmarks | **Real** (`data/margins/datac_apparel_benchmarks.csv`) |
| **Market / WTP** | Roots Analysis, McKinsey/BoF, Fact.MR | **Real, cited** (`data/market/market_context.json`) |
| **Product line** | 6-SKU AW26 line (Livostyle-derived attributes) | Attributes **real**; marketing **claims synthetic (scenario)** |
| **Supplier certs** | GRS/RCS Scope + Transaction Certificates | **Synthetic**, structurally authentic (Textile Exchange ASR-204/205) |

Full provenance: [`data/README.md`](data/README.md). Re-fetch real series: `python3 scripts/fetch_data.py`.

---

## Author

Architected and built **solo** at RAISE 2026 by **[NAME]** (team ShipHappens). Coordination engine written fresh during the event; document-grounding via Vultr Turnkey RAG; commercial layer on real cited public data.

---

## Status

**Demo-ready:** engine + UI + real data staged; smoke tests green (`scripts/smoke_data.py`, `scripts/smoke_vultr.py`). Backup video + deploy pending.
