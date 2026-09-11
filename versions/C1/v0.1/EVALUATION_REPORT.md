# PLM-C1 v0.1 Evaluation Report

## Frozen PLM-C0 v0.3 regression benchmark

288 total cases, evaluated on the fixed 216-case test split (72 semantic groups).

| Metric | PLM-C1 v0.1 | PLM-C0 v0.3 | Lexical baseline | C1 - C0 |
|---|---:|---:|---:|---:|
| top1_accuracy | 1.0 | 0.8333 | 0.5833 | 0.1667 |
| top5_recall | 1.0 | 0.8889 | 0.8056 | 0.1111 |
| mrr | 0.9514 | 0.8083 | 0.7431 | 0.1431 |
| macro_f1 | 1.0 | 0.8894 | 0.7152 | 0.1106 |
| unresolved_precision | 1.0 | 0.9231 | 0.3333 | 0.0769 |
| unresolved_recall | 1.0 | 0.6 | 0.4 | 0.4 |
| contradiction_rejection | 1.0 | 0.7333 | 0.2667 | 0.2667 |
| coverage | 0.7222 | 0.8194 | 0.6667 | -0.0972 |
| selective_accuracy | 1.0 | 0.8136 | 0.7083 | 0.1864 |
| expected_calibration_error | 0.1655 | 0.0874 | 0.2288 | 0.0781 |
| brier_score | 0.0567 | 0.1537 | 0.2717 | -0.097 |

C1 Top-1 95% CI: [1.0000, 1.0000]

C1-C0 paired Top-1 delta 95% CI: [0.0833, 0.2500]

Known stress tag Top-1: C1 `1.0` / C0 `0.0`.

## C1 ablation on frozen regression test

| Variant | Top-1 | Macro-F1 | Stress Top-1 | Contradiction rejection |
|---|---:|---:|---:|---:|
| full | 1.0 | 1.0 | 1.0 | 1.0 |
| no_scope | 0.9583 | 0.9785 | 0.75 | 1.0 |
| no_correction | 0.9583 | 0.9585 | 0.75 | 1.0 |
| no_residual | 0.9583 | 0.9585 | 0.75 | 1.0 |
| no_negation | 0.8333 | 0.8892 | 0.5833 | 0.4667 |

## Explicit operation audit

Audited semantic groups: `72`

Operation counts: `{'ISOLATE': 88, 'ISOLATE_CONFLICT': 1, 'NEGATE': 26, 'SUPERSEDE': 4}`

Superseded evidence items: `4`; residual weight removed: `4.0`

Forced unresolved domains: `{'place': 1}`

## Post-implementation challenge

The 20 semantic challenge templates (60 wrapper cases) were frozen before their first run and were not used to tune v0.1.

| Metric | PLM-C1 v0.1 | PLM-C0 v0.3 | C1 - C0 |
|---|---:|---:|---:|
| top1_accuracy | 0.2 | 0.1 | 0.1 |
| top5_recall | 0.55 | 0.5 | 0.05 |
| mrr | 0.325 | 0.25 | 0.075 |
| macro_f1 | 0.1718 | 0.1032 | 0.0686 |
| unresolved_precision | 0.4 | 0.0 | 0.4 |
| unresolved_recall | 0.2222 | 0.0 | 0.2222 |
| contradiction_rejection | 0.0 | 0.0 | 0.0 |
| coverage | 0.75 | 0.85 | -0.1 |
| selective_accuracy | 0.1333 | 0.1176 | 0.0157 |
| expected_calibration_error | 0.681 | 0.6883 | -0.0073 |
| brier_score | 0.5993 | 0.5989 | 0.0004 |

C1 challenge Top-1 95% CI: [0.0500, 0.4000]

C1-C0 challenge Top-1 delta 95% CI: [-0.1000, 0.3000]

### Challenge failures by semantic group

- `context_conditional_water`: expected `UNRESOLVED`, predicted `RIVER_BANK`, mean confidence `0.9011`
- `context_negated_river_ja`: expected `UNRESOLVED`, predicted `RIVER_BANK`, mean confidence `0.9011`
- `context_nowhere_river`: expected `UNRESOLVED`, predicted `RIVER_BANK`, mean confidence `0.9703`
- `context_plural_account`: expected `FINANCIAL_BANK`, predicted `UNRESOLVED`, mean confidence `0.3734`
- `context_separate_sentences`: expected `UNRESOLVED`, predicted `RIVER_BANK`, mean confidence `0.9011`
- `correction_actually_dash_en`: expected `CAT`, predicted `ANIMAL`, mean confidence `0.7805`
- `correction_however_en`: expected `CAT`, predicted `ANIMAL`, mean confidence `0.7805`
- `correction_initially_en`: expected `CAT`, predicted `ANIMAL`, mean confidence `0.7805`
- `correction_initially_ja`: expected `CAT`, predicted `ANIMAL`, mean confidence `0.7805`
- `correction_iya_ja`: expected `CAT`, predicted `ANIMAL`, mean confidence `0.7805`
- `correction_update_en`: expected `CAT`, predicted `ANIMAL`, mean confidence `0.7805`
- `double_negation_en`: expected `DOG`, predicted `UNRESOLVED`, mean confidence `1.0000`
- `double_negation_ja`: expected `DOG`, predicted `UNRESOLVED`, mean confidence `1.0000`
- `predicate_scope_ja`: expected `UNRESOLVED`, predicted `BARK`, mean confidence `0.8455`
- `reported_denial_en`: expected `UNRESOLVED`, predicted `DOG`, mean confidence `0.8455`
- `scope_afterward_sources`: expected `UNRESOLVED`, predicted `RIVER_BANK`, mean confidence `0.8572`

## Interpretation

- C1 closes all failures in the known v0.3 regression benchmark without regressing its ordinary cases.
- The challenge score remains low, showing that marker dictionaries and shallow scope rules do not generalize reliably.
- Remaining gaps are unseen correction markers, double negation, reported denial, morphology, conditionals, and broader discourse boundaries.
- Both datasets are authored functional benchmarks, not external corpora. Statistical intervals do not establish real-world validity.
