# PLM-C0 v0.3 Evaluation Report

Benchmark: **288 cases** (72 dev / 216 test), 72 semantic template groups.

## Held-out wrapper test split

| Metric | PLM-C0 v0.3 | Positive lexical baseline | Delta |
|---|---:|---:|---:|
| top1_accuracy | 0.8333 | 0.5833 | 0.25 |
| top5_recall | 0.8889 | 0.8056 | 0.0833 |
| mrr | 0.8083 | 0.7431 | 0.0652 |
| macro_f1 | 0.8894 | 0.7152 | 0.1742 |
| unresolved_precision | 0.9231 | 0.3333 | 0.5898 |
| unresolved_recall | 0.6 | 0.4 | 0.2 |
| minority_evidence_retention | 1.0 | 1.0 | 0.0 |
| contradiction_rejection | 0.7333 | 0.2667 | 0.4666 |
| coverage | 0.8194 | 0.6667 | 0.1527 |
| selective_accuracy | 0.8136 | 0.7083 | 0.1053 |
| expected_calibration_error | 0.0874 | 0.2288 | -0.1414 |
| brier_score | 0.1537 | 0.2717 | -0.118 |
| average_candidates_evaluated | 4.18 | 4.18 | 0.0 |
| average_patterns_checked | 48.4 | 46.04 | 2.36 |

PLM Top-1 95% CI: [0.7500, 0.9167]

Paired Top-1 delta 95% CI: [0.1250, 0.3889]

## Ablation study (test split)

| Variant | Top-1 | Macro-F1 | UNRESOLVED F1 | Contradiction rejection | ECE |
|---|---:|---:|---:|---:|---:|
| full | 0.8333 | 0.8894 | 0.7273 | 0.7333 | 0.0874 |
| no_negation | 0.7361 | 0.8209 | 0.5517 | 0.4667 | 0.1575 |
| no_context | 0.7778 | 0.8486 | 0.6977 | 0.7333 | 0.06 |
| no_hierarchy | 0.7222 | 0.8064 | 0.5581 | 0.7333 | 0.0694 |
| no_sibling_contradiction | 0.8194 | 0.8891 | 0.6667 | 0.7333 | 0.1023 |
| no_overlap_suppression | 0.8333 | 0.8894 | 0.7273 | 0.7333 | 0.0846 |
| no_ascii_boundaries | 0.8056 | 0.8659 | 0.6 | 0.5333 | 0.0886 |

## Selected tag breakdown (test split)

| Tag | Cases | PLM Top-1 | Baseline Top-1 | PLM Top-5 |
|---|---:|---:|---:|---:|
| stress | 36 | 0.0 | 0.4167 | 0.3333 |
| negation | 42 | 0.5714 | 0.2143 | 0.6429 |
| context_scope | 15 | 0.0 | 0.8 | 0.2 |
| correction | 9 | 0.0 | 0.3333 | 1.0 |
| boundary | 9 | 1.0 | 0.0 | 1.0 |
| hierarchy | 24 | 1.0 | 0.25 | 1.0 |
| minority_evidence | 12 | 1.0 | 0.25 | 1.0 |

## Coverage-accuracy (PLM test split)

| Confidence threshold | Coverage | Accuracy among accepted | Accepted |
|---:|---:|---:|---:|
| 0.0 | 0.8194 | 0.8136 | 177 |
| 0.5 | 0.8194 | 0.8136 | 177 |
| 0.6 | 0.8194 | 0.8136 | 177 |
| 0.7 | 0.8194 | 0.8136 | 177 |
| 0.8 | 0.7361 | 0.8302 | 159 |
| 0.9 | 0.2361 | 0.7647 | 51 |

## PLM errors on test split

- `stress_complex_negation_ja` (3 wrapper variants): expected `UNRESOLVED`, predicted `DOG`, mean confidence `0.8455`
- `stress_correction_en` (3 wrapper variants): expected `CAT`, predicted `ANIMAL`, mean confidence `0.7805`
- `stress_correction_ja` (3 wrapper variants): expected `CAT`, predicted `ANIMAL`, mean confidence `0.7805`
- `stress_cross_input_context` (3 wrapper variants): expected `UNRESOLVED`, predicted `RIVER_BANK`, mean confidence `0.9011`
- `stress_discontinuous_negation_en` (3 wrapper variants): expected `UNRESOLVED`, predicted `BARK`, mean confidence `0.8455`
- `stress_financial_negative_affordance` (3 wrapper variants): expected `FINANCIAL_BANK`, predicted `UNRESOLVED`, mean confidence `0.3734`
- `stress_long_negation_en` (3 wrapper variants): expected `UNRESOLVED`, predicted `DOG`, mean confidence `0.8455`
- `stress_negated_context` (3 wrapper variants): expected `UNRESOLVED`, predicted `RIVER_BANK`, mean confidence `0.9011`
- `stress_ordered_correction` (3 wrapper variants): expected `CAT`, predicted `DOG`, mean confidence `0.8748`
- `stress_predicate_negation_ja` (3 wrapper variants): expected `UNRESOLVED`, predicted `BARK`, mean confidence `0.8455`
- `stress_two_places` (3 wrapper variants): expected `UNRESOLVED`, predicted `RIVER_BANK`, mean confidence `0.9703`
- `stress_unrelated_clause_context` (3 wrapper variants): expected `UNRESOLVED`, predicted `RIVER_BANK`, mean confidence `0.9011`

## Interpretation limits

- This is a deterministic, closed-vocabulary functional benchmark, not an external corpus.
- Dev and test use different wrappers but share 72 semantic seeds; this is not a fully independent blind test.
- Confidence intervals cluster by semantic template group to avoid treating wrapper variants as independent examples.
- Calibration metrics assess the current heuristic confidence, not a trained probability model.
