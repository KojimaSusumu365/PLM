# PLM-C1 v0.2 Evaluation Report

PLM-C1 v0.1を凍結比較対象とし、v0.3回帰セット、既存v0.1チャレンジ、実装後に凍結した新規v0.2チャレンジの3層で評価した。

新規チャレンジ SHA-256: `34b396ab0916b617e31e0162dc44c4a2eed52ecc57556a29c328dc1cd8808d53`。初回実行後のengine/Concept-data調整は行っていない。

## Frozen v0.3 regression (216 test cases)

| Metric | C1 v0.2 | C1 v0.1 | C0 v0.3 | Lexical | Δ v0.2-v0.1 |
|---|---:|---:|---:|---:|---:|
| top1_accuracy | 1.0 | 1.0 | 0.8333 | 0.5833 | 0.0 |
| top5_recall | 1.0 | 1.0 | 0.8889 | 0.8056 | 0.0 |
| mrr | 0.9514 | 0.9514 | 0.8083 | 0.7431 | 0.0 |
| macro_f1 | 1.0 | 1.0 | 0.8894 | 0.7152 | 0.0 |
| unresolved_precision | 1.0 | 1.0 | 0.9231 | 0.3333 | 0.0 |
| unresolved_recall | 1.0 | 1.0 | 0.6 | 0.4 | 0.0 |
| contradiction_rejection | 1.0 | 1.0 | 0.7333 | 0.2667 | 0.0 |
| coverage | 0.7222 | 0.7222 | 0.8194 | 0.6667 | 0.0 |
| selective_accuracy | 1.0 | 1.0 | 0.8136 | 0.7083 | 0.0 |
| expected_calibration_error | 0.1655 | 0.1655 | 0.0874 | 0.2288 | 0.0 |
| brier_score | 0.0567 | 0.0567 | 0.1537 | 0.2717 | 0.0 |

v0.2 Top-1 95% cluster-bootstrap CI: `[1.0000, 1.0000]`

v0.2-v0.1 Top-1 delta 95% CI: `[0.0000, 0.0000]`

## Known v0.1 challenge (60 cases)

| Metric | C1 v0.2 | C1 v0.1 | C0 v0.3 | Δ v0.2-v0.1 |
|---|---:|---:|---:|---:|
| top1_accuracy | 1.0 | 0.2 | 0.1 | 0.8 |
| top5_recall | 1.0 | 0.55 | 0.5 | 0.45 |
| mrr | 1.0 | 0.325 | 0.25 | 0.675 |
| macro_f1 | 1.0 | 0.1718 | 0.1032 | 0.8282 |
| unresolved_precision | 1.0 | 0.4 | 0.0 | 0.6 |
| unresolved_recall | 1.0 | 0.2222 | 0.0 | 0.7778 |
| contradiction_rejection | 1.0 | 0.0 | 0.0 | 1.0 |
| coverage | 0.55 | 0.75 | 0.85 | -0.2 |
| selective_accuracy | 1.0 | 0.1333 | 0.1176 | 0.8667 |
| expected_calibration_error | 0.1903 | 0.681 | 0.6883 | -0.4907 |
| brier_score | 0.0725 | 0.5993 | 0.5989 | -0.5268 |

v0.2 Top-1 95% cluster-bootstrap CI: `[1.0000, 1.0000]`

v0.2-v0.1 Top-1 delta 95% CI: `[0.6000, 0.9500]`

## Unseen v0.2 challenge (60 cases)

| Metric | C1 v0.2 | C1 v0.1 | C0 v0.3 | Δ v0.2-v0.1 |
|---|---:|---:|---:|---:|
| top1_accuracy | 0.65 | 0.25 | 0.3 | 0.4 |
| top5_recall | 0.8 | 0.55 | 0.65 | 0.25 |
| mrr | 0.7 | 0.375 | 0.45 | 0.325 |
| macro_f1 | 0.5953 | 0.1524 | 0.2413 | 0.4429 |
| unresolved_precision | 0.625 | 0.25 | 0.375 | 0.375 |
| unresolved_recall | 0.7143 | 0.2857 | 0.4286 | 0.4286 |
| contradiction_rejection | 1.0 | 1.0 | 1.0 | 0.0 |
| coverage | 0.6 | 0.6 | 0.6 | 0.0 |
| selective_accuracy | 0.6667 | 0.25 | 0.25 | 0.4167 |
| expected_calibration_error | 0.299 | 0.5752 | 0.5467 | -0.2762 |
| brier_score | 0.2723 | 0.5224 | 0.4932 | -0.2501 |

v0.2 Top-1 95% cluster-bootstrap CI: `[0.4500, 0.8500]`

v0.2-v0.1 Top-1 delta 95% CI: `[0.2000, 0.6000]`

### Unseen challenge failures

- `discourse_formerly_en`: expected `CAT`, predicted `ANIMAL`, mean confidence `0.7805`
- `discourse_torikeshi_ja`: expected `CAT`, predicted `ANIMAL`, mean confidence `0.7805`
- `morph_barked_en`: expected `BARK`, predicted `UNRESOLVED`, mean confidence `1.0000`
- `morph_puppies_en`: expected `DOG`, predicted `UNRESOLVED`, mean confidence `1.0000`
- `relation_dry_riverbed_en`: expected `RIVER_BANK`, predicted `UNRESOLVED`, mean confidence `0.3734`
- `target_another_case_en`: expected `UNRESOLVED`, predicted `ANIMAL`, mean confidence `0.7805`
- `target_betsu_case_ja`: expected `UNRESOLVED`, predicted `ANIMAL`, mean confidence `0.7805`

## Ablation on known v0.1 challenge

| Variant | Top-1 | MRR | ECE |
|---|---:|---:|---:|
| full | 1.0 | 1.0 | 0.1903 |
| no_polarity_composition | 0.7 | 0.7 | 0.2752 |
| no_discourse_state | 0.65 | 0.725 | 0.3817 |
| no_morphology | 0.95 | 1.0 | 0.1702 |
| no_target_tracking | 0.9 | 0.9 | 0.18 |
| no_relation_context | 0.95 | 0.95 | 0.1981 |
| no_residual | 0.7 | 0.775 | 0.3571 |

## Explicit operation audit

Semantic groups audited: `112`; operation counts: `{'ISOLATE': 151, 'ISOLATE_CONFLICT': 5, 'NEGATE': 41, 'POLARITY_COMPOSE': 3, 'RELATE': 27, 'STATE_TRANSITION': 21, 'SUPERSEDE': 13}`.

Relations: `19/27` applied; superseded evidence: `13`; residual weight removed: `13.0`.

## Acceptance

- PASS — `regression_top1_at_least_0_98`
- PASS — `known_challenge_top1_at_least_0_70`
- PASS — `known_challenge_ece_better_than_v01`
- PASS — `unseen_challenge_beats_v01`

Overall: **PASS**

## Interpretation

v0.2は固定回帰を維持し、v0.1が失敗した既存チャレンジをすべて解決した。新規未見セットでもv0.1を上回ったが、Top-1は0.65に留まる。

残る失敗は、辞書にない談話・対象切替マーカー、英語の不規則複数・過去形、複合語内部の関係語である。いずれも手作業の機能benchmarkであり、実世界性能を示すものではない。
