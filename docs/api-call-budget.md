# API Call Budget

## Overview

The project is designed to stay well under 200 API calls per evaluation cycle.
The model layer (Vertex AI) is the only paid component, so call volume directly
maps to cost.

## Quality Cycle (daily / every commit)

**Total: RAGAS cycle ~140 calls; DeepEval cycle ~190 calls**

| Component | Dataset | Calls/Q | Total Calls | Notes |
|---|---|---|---|---|
| RAGAS **or** DeepEval | 10 (RAGAS) or 20 (DeepEval) questions | 11 or 8 | ~110 or ~160 | Never both in same cycle |
| promptfoo regression | 15 tests | 2 | ~30 | 1 generate + 1 judge per test |
| **Total** | | | **~140 / ~190** | |

### RAGAS Detail

- **Metrics**: 3 (context precision, faithfulness, answer relevancy) — all real, LLM-judged (no cheaper non-LLM substitute)
- **Context recall dropped** to reduce cost
- **Questions**: 10 from golden dataset (reduced from 20 specifically for RAGAS to fit budget — see below)
- **Calls per question**: 11 — Context Precision issues one judge call per retrieved chunk (`top_k=5` → 5 calls), Faithfulness is 2 calls (fixed), Answer Relevancy at default strictness=3 is 3 calls, plus 1 `/query` call = 10 + 1 = **11**
- **Total**: 10 × 11 = **~110 calls**
- Dataset size had to shrink from the original 20 to keep this under budget — at 20 questions this would be 220 calls, over the 200 hard cap on its own

### DeepEval Detail

- **Metrics**: 4 (answer relevancy, faithfulness, contextual precision, hallucination), all with `include_reason=False` (drops the free-text explanation only, no accuracy cost)
- **Questions**: 20 from golden dataset
- **Calls per question**: 8 — Answer Relevancy 2, Faithfulness 3, Contextual Precision 1, Hallucination 1 = 7 judge calls + 1 `/query` call = **8**
- **Total**: 20 × 8 = **~160 calls**

### promptfoo Detail

- **Tests**: 15 regression tests
- **Calls per test**: 2 (1 generation + 1 Haiku judge)
- **Total**: 15 × 2 = **~30 calls**

## Safety Cycle (weekly / on-demand)

**Total: ≤50 calls (typically ~40–44)**

| Component | Scope | Calls | Notes |
|---|---|---|---|
| PyRIT XPIA | 2 scenarios, 5-turn cap | ≤20 (typ. 10–14) | 1 `/query` + 1 Claude Haiku judge call per turn |
| Garak probes | 10 probes, capped to 1 prompt each | 10 | 1 `/query` call per probe, 0 Claude calls |
| Fairlearn audit | 10 items | 20 | 1 `/query` + 1 Claude Haiku classification per item |
| **Total** | | **≤50 (typ. ~40–44)** | |

### PyRIT XPIA Detail

- **Scenarios**: 2 (ignore-instructions, data-exfiltration)
- **Max turns per scenario**: 5
- **Calls per turn**: 2 — 1 chatbot `/query` call (via `ChatbotQueryTarget`) +
  1 Claude Haiku judge call (via PyRIT's `SelfAskTrueFalseScorer`, backed by
  `ClaudeVertexJudgeTarget`)
- **Total**: worst case 2 scenarios × 5 turns × 2 = **20 calls**; typically
  ~10–14 since a scenario stops early once injection is detected

### Garak Detail

- **Probes**: 10 (DAN jailbreaks, LMRC categories, malware gen, toxicity —
  `gcg.GCGCached` dropped, see `docs/known-limitations.md`)
- **Calls per probe**: 1 — every probe is explicitly capped to a single,
  reproducibly-sampled prompt (`MAX_PROMPTS_PER_PROBE` in
  `src/redteam/garak_probe.py`); uncapped, this probe set costs ~131 calls
  (e.g. `malwaregen.Evasion`=48 prompts, `malwaregen.SubFunctions`=56 prompts
  by default)
- **Total**: **10 calls**, 0 Claude judge calls (garak's own detectors score
  pass/fail)

### Fairlearn Detail

- **Audit items**: 10 (balanced across 5 groups × 2 items — reduced from 20
  when the length-heuristic placeholder was replaced with a real Claude
  Haiku judge call, which doubled the per-item cost)
- **Calls per item**: 2 — 1 `/query` call + 1 Claude Haiku POSITIVE/NEGATIVE
  classification call
- **Total**: **20 calls**

## Interactive Dev Traffic

Not counted in cycle budgets:
- ~2–3 calls per user query during development
- Retrieval is free (Chroma is local)
- Generation: 1 Gemini call
- Condensation: 1 Gemini call (multi-turn only)

## Monthly Projection

| Category | Frequency | Calls/Cycle | Monthly Calls |
|---|---|---|---|
| Quality cycles | Daily × 30 | ~140–190 | ~4,200–5,700 |
| Safety cycles | Weekly × 4 | ≤50 | ~200 |
| Dev traffic | Ad-hoc | ~3/query | ~300 (est.) |
| **Total** | | | **~4,700–6,200** |

## Cost Estimate

Assuming Vertex AI pricing (approximate):
- Gemini Flash: ~$0.0001 per 1K input tokens
- Claude Sonnet: ~$0.003 per 1K input tokens
- Claude Haiku: ~$0.00025 per 1K input tokens

At ~5,000 calls/month with average 1K tokens per call:
- **Estimated monthly cost**: $10–25 depending on model mix

## Scaling Notes

- Quality cycle budget grows **linearly** with golden dataset size and
  promptfoo test count
- RAGAS's dataset size (10) is already tuned to the 200 hard cap given its
  real LLM-judged Context Precision metric costs 5 calls/question on its
  own (`top_k=5`) — don't raise it without re-checking the total. DeepEval's
  dataset (20) has more headroom (~160 of 200) if it needs to grow.
- Safety cycle is more stable — scenario count and probe count are
  controlled independently
- **Never run quality and safety cycles concurrently** (MLflow SQLite
  write contention)
