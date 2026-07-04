# GreenLight data — provenance & acquisition

Real-first. Every file states its source; synthetic parts are labelled and used only where real data
can't be sourced or reliably integrated. See `internal_docs/DATA_SOURCES.md` for the full map.

## In this repo (staged, ready)
| Path | What | Real / synthetic |
|---|---|---|
| `regulations/ecgt_2024_825.md` | ECGT (EU) 2024/825 operative clauses (verbatim) | **Real** (EUR-Lex CELEX:32024L0825) |
| `regulations/context_market_enforcement.md` | Penalty basis, Shein enforcement, France law, recycled-content stats | **Real, cited** |
| `market/market_context.json` | Market size, willingness-to-pay, demand signals | **Real, cited** |
| `line/aw26_line.json` | The AW26 line (6 SKUs) + marketing claims | Attributes modeled on real Livostyle catalog; **claims synthetic (scenario)** |
| `certs/scope_certificates.json` | Supplier Scope Certificates | Synthetic, structurally authentic (Textile Exchange ASR-204) |
| `certs/transaction_certificates.json` | Supplier Transaction Certificates (incl. the 40% vs 70% mismatch) | Synthetic, structurally authentic (ASR-205) |
| `demand/trends_sustainability.csv` | **Google Trends** interest-over-time, 261 weekly rows (sustainable fashion / recycled polyester / organic cotton) | **Real** (pulled via `scripts/fetch_data.py`) |
| `margins/datac_apparel_benchmarks.csv` | Per-category profit ratio / discount / price benchmarks (apparel, footwear, clothing…) | **Real** (derived from DataCo, 10 categories) |

## Fetched & reproducible
`scripts/fetch_data.py` re-downloads DataCo (→ gitignored 96MB raw + committed benchmark) and
re-pulls Google Trends. Deps: `python3 -m pip install --user pytrends-modern`.

## Still manual (form-gated — optional upgrade)
- **Visuelle 2.0** (real per-SKU sales + Google Trends + weather, Nuna Lie): download requires a
  Google Form → https://forms.gle/8Sk431AsEgCot9Kv5 (linked from
  https://humaticslab.github.io/forecasting/visuelle). Extract under `data/demand/visuelle/`.
  Not required: `forecast_demand()` already runs on the committed Google-Trends series.

## Smokes (run before building)
- `python3 scripts/smoke_data.py` — validates every file, the SC/TC 40-vs-70 gap, offline
  retrieval returns the right ECGT clause, and commercial data loads. (`--no-vultr` for offline only.)
- `python3 scripts/smoke_vultr.py` — live Vultr inference + Turnkey RAG + Gradium TTS.

## Note
Only the 96MB DataCo raw and any Visuelle download are gitignored; the small real derived files
(`trends_sustainability.csv`, `datac_apparel_benchmarks.csv`) are committed. RAG collections are
seeded from `regulations/` and `certs/` at build time.
