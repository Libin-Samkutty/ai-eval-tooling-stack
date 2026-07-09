# API Call Budget

## Overview

The project is designed to stay well under 200 API calls per evaluation cycle.
The model layer (Vertex AI) is the only paid component, so call volume directly
maps to cost.

## Quality Cycle (daily / every commit)

**Total: ~90–110 calls**

| Component | Dataset | Calls/Q | Total Calls | Notes |
|---|---|---|---|---|
| RAGAS **or** DeepEval | 20 questions | ~3 or ~4 | ~60 or ~80 | Never both in same cycle |
| promptfoo regression | 15 tests | 2 | ~30 | 1 generate + 1 judge per test |
| **Total** | | | **~90–110** | |

### RAGAS Detail

- **Metrics**: 3 (context precision, faithfulness, answer relevancy)
- **Context recall dropped** to reduce cost
- **Questions**: 20 from golden dataset
- **Calls per question**: ~3 (1 generation + 2 judge calls)
- **Total**: 20 × 3 = **~60 calls**

### DeepEval Detail

- **Metrics**: 4 (answer relevancy, faithfulness, contextual precision, hallucination)
- **Questions**: 20 from golden dataset
- **Calls per question**: ~4 (1 generation + 3 judge calls)
- **Total**: 20 × 4 = **~80 calls**

### promptfoo Detail

- **Tests**: 15 regression tests
- **Calls per test**: 2 (1 generation + 1 Haiku judge)
- **Total**: 15 × 2 = **~30 calls**

## Safety Cycle (weekly / on-demand)

**Total: ~50–60 calls**

| Component | Scope | Calls | Notes |
|---|---|---|---|
| PyRIT XPIA | 2 scenarios, 5-turn cap | ~20–30 | Claude judge calls |
| Garak probes | 10 probes | ~10 | 1 call per probe |
| Fairlearn audit | 20 items | ~20 | 1 inference per item |
| **Total** | | **~50–60** | |

### PyRIT XPIA Detail

- **Scenarios**: 2 (ignore-instructions, data-exfiltration)
- **Max turns per scenario**: 5
- **Claude calls per scenario**: ~10–15 (turns + judge)
- **Total**: 2 × ~12.5 = **~20–30 calls**

### Garak Detail

- **Probes**: 10 (DAN, GCG, LMRC categories, malware gen, toxicity)
- **Calls per probe**: ~1
- **Total**: **~10 calls**

### Fairlearn Detail

- **Audit items**: 20 (balanced across 5 groups × 4 items)
- **Calls per item**: 1 (inference)
- **Total**: **~20 calls**

## Interactive Dev Traffic

Not counted in cycle budgets:
- ~2–3 calls per user query during development
- Retrieval is free (Chroma is local)
- Generation: 1 Gemini call
- Condensation: 1 Gemini call (multi-turn only)

## Monthly Projection

| Category | Frequency | Calls/Cycle | Monthly Calls |
|---|---|---|---|
| Quality cycles | Daily × 30 | ~100 | ~3,000 |
| Safety cycles | Weekly × 4 | ~55 | ~220 |
| Dev traffic | Ad-hoc | ~3/query | ~300 (est.) |
| **Total** | | | **~3,520** |

## Cost Estimate

Assuming Vertex AI pricing (approximate):
- Gemini Flash: ~$0.0001 per 1K input tokens
- Claude Sonnet: ~$0.003 per 1K input tokens
- Claude Haiku: ~$0.00025 per 1K input tokens

At ~3,500 calls/month with average 1K tokens per call:
- **Estimated monthly cost**: $5–15 depending on model mix

## Scaling Notes

- Quality cycle budget grows **linearly** with golden dataset size and
  promptfoo test count
- If golden dataset grows beyond 20 questions, re-evaluate RAGAS metric
  count before expanding
- Safety cycle is more stable — scenario count and probe count are
  controlled independently
- **Never run quality and safety cycles concurrently** (MLflow SQLite
  write contention)
