# PLM-C1 v0.3 Evaluation Report

v0.2の未見失敗を開発診断へ移し、凍結したv0.2/v0.1/C0と同条件で比較した。v0.3完成後に別の未見challengeを固定し、初回実行後の調整は行っていない。

新規challenge SHA-256: `90a8f9d28b5e2abd86a66b9c60d309992c6c30c123586afcdf51751453e544a8`。

## Frozen v0.3 regression (216 test cases)

| Metric | C1 v0.3 | C1 v0.2 | C1 v0.1 | C0 v0.3 | Lexical | Δ v0.3-v0.2 |
|---|---:|---:|---:|---:|---:|---:|
| top1_accuracy | 1.0 | 1.0 | 1.0 | 0.8333 | 0.5833 | 0.0 |
| top5_recall | 1.0 | 1.0 | 1.0 | 0.8889 | 0.8056 | 0.0 |
| mrr | 0.9514 | 0.9514 | 0.9514 | 0.8083 | 0.7431 | 0.0 |
| macro_f1 | 1.0 | 1.0 | 1.0 | 0.8894 | 0.7152 | 0.0 |
| unresolved_precision | 1.0 | 1.0 | 1.0 | 0.9231 | 0.3333 | 0.0 |
| unresolved_recall | 1.0 | 1.0 | 1.0 | 0.6 | 0.4 | 0.0 |
| contradiction_rejection | 1.0 | 1.0 | 1.0 | 0.7333 | 0.2667 | 0.0 |
| coverage | 0.7222 | 0.7222 | 0.7222 | 0.8194 | 0.6667 | 0.0 |
| selective_accuracy | 1.0 | 1.0 | 1.0 | 0.8136 | 0.7083 | 0.0 |
| expected_calibration_error | 0.2016 | 0.1655 | 0.1655 | 0.0874 | 0.2288 | 0.0361 |
| brier_score | 0.0802 | 0.0567 | 0.0567 | 0.1537 | 0.2717 | 0.0235 |

v0.3 Top-1 95% cluster-bootstrap CI: `[1.0000, 1.0000]`

v0.3-v0.2 Top-1 delta 95% CI: `[0.0000, 0.0000]`

## Known v0.1 challenge (60 cases)

| Metric | C1 v0.3 | C1 v0.2 | C1 v0.1 | C0 v0.3 | Δ v0.3-v0.2 |
|---|---:|---:|---:|---:|---:|
| top1_accuracy | 1.0 | 1.0 | 0.2 | 0.1 | 0.0 |
| top5_recall | 1.0 | 1.0 | 0.55 | 0.5 | 0.0 |
| mrr | 1.0 | 1.0 | 0.325 | 0.25 | 0.0 |
| macro_f1 | 1.0 | 1.0 | 0.1718 | 0.1032 | 0.0 |
| unresolved_precision | 1.0 | 1.0 | 0.4 | 0.0 | 0.0 |
| unresolved_recall | 1.0 | 1.0 | 0.2222 | 0.0 | 0.0 |
| contradiction_rejection | 1.0 | 1.0 | 0.0 | 0.0 | 0.0 |
| coverage | 0.55 | 0.55 | 0.75 | 0.85 | 0.0 |
| selective_accuracy | 1.0 | 1.0 | 0.1333 | 0.1176 | 0.0 |
| expected_calibration_error | 0.1903 | 0.1903 | 0.681 | 0.6883 | 0.0 |
| brier_score | 0.0725 | 0.0725 | 0.5993 | 0.5989 | 0.0 |

v0.3 Top-1 95% cluster-bootstrap CI: `[1.0000, 1.0000]`

v0.3-v0.2 Top-1 delta 95% CI: `[0.0000, 0.0000]`

## Development v0.2 challenge (60 cases)

| Metric | C1 v0.3 | C1 v0.2 | C1 v0.1 | C0 v0.3 | Δ v0.3-v0.2 |
|---|---:|---:|---:|---:|---:|
| top1_accuracy | 1.0 | 0.65 | 0.25 | 0.3 | 0.35 |
| top5_recall | 1.0 | 0.8 | 0.55 | 0.65 | 0.2 |
| mrr | 1.0 | 0.7 | 0.375 | 0.45 | 0.3 |
| macro_f1 | 1.0 | 0.5953 | 0.1524 | 0.2413 | 0.4047 |
| unresolved_precision | 1.0 | 0.625 | 0.25 | 0.375 | 0.375 |
| unresolved_recall | 1.0 | 0.7143 | 0.2857 | 0.4286 | 0.2857 |
| contradiction_rejection | 1.0 | 1.0 | 1.0 | 1.0 | 0.0 |
| coverage | 0.65 | 0.6 | 0.6 | 0.6 | 0.05 |
| selective_accuracy | 1.0 | 0.6667 | 0.25 | 0.25 | 0.3333 |
| expected_calibration_error | 0.163 | 0.299 | 0.5752 | 0.5467 | -0.136 |
| brier_score | 0.0506 | 0.2723 | 0.5224 | 0.4932 | -0.2217 |

v0.3 Top-1 95% cluster-bootstrap CI: `[1.0000, 1.0000]`

v0.3-v0.2 Top-1 delta 95% CI: `[0.1500, 0.5500]`

## Unseen v0.3 challenge (60 cases)

| Metric | C1 v0.3 | C1 v0.2 | C1 v0.1 | C0 v0.3 | Δ v0.3-v0.2 |
|---|---:|---:|---:|---:|---:|
| top1_accuracy | 0.7 | 0.3 | 0.25 | 0.2 | 0.4 |
| top5_recall | 0.75 | 0.55 | 0.55 | 0.5 | 0.2 |
| mrr | 0.7125 | 0.375 | 0.35 | 0.3 | 0.3375 |
| macro_f1 | 0.7969 | 0.3175 | 0.2175 | 0.2021 | 0.4794 |
| unresolved_precision | 0.6 | 0.25 | 0.25 | 0.1429 | 0.35 |
| unresolved_recall | 0.5 | 0.3333 | 0.3333 | 0.1667 | 0.1667 |
| contradiction_rejection | 1.0 | 1.0 | 1.0 | 1.0 | 0.0 |
| coverage | 0.75 | 0.6 | 0.6 | 0.65 | 0.15 |
| selective_accuracy | 0.7333 | 0.3333 | 0.25 | 0.2308 | 0.4 |
| expected_calibration_error | 0.1288 | 0.5474 | 0.6484 | 0.6839 | -0.4186 |
| brier_score | 0.1769 | 0.5133 | 0.5642 | 0.6009 | -0.3364 |

v0.3 Top-1 95% cluster-bootstrap CI: `[0.5000, 0.9000]`

v0.3-v0.2 Top-1 delta 95% CI: `[0.2000, 0.6000]`

### Unseen v0.3 challenge failures

- `compound_riverbank_closed`: expected `RIVER_BANK`, predicted `UNRESOLVED`, mean confidence `0.3500`
- `morph_bitten`: expected `BITE`, predicted `UNRESOLVED`, mean confidence `0.3500`
- `relation_river_statistics`: expected `UNRESOLVED`, predicted `RIVER_BANK`, mean confidence `0.8572`
- `revision_originally_revised`: expected `CAT`, predicted `ANIMAL`, mean confidence `0.7805`
- `target_separate_case_inline`: expected `UNRESOLVED`, predicted `ANIMAL`, mean confidence `0.7805`
- `target_subsequently`: expected `UNRESOLVED`, predicted `ANIMAL`, mean confidence `0.7805`

## Ablation on v0.2 development challenge

| Variant | Top-1 | MRR | ECE |
|---|---:|---:|---:|
| full | 1.0 | 1.0 | 0.163 |
| no_lemma_normalization | 0.85 | 0.875 | 0.1371 |
| no_transition_roles | 0.9 | 0.925 | 0.1817 |
| no_event_identity | 0.9 | 0.9 | 0.1822 |
| no_compound_analysis | 0.95 | 0.975 | 0.1429 |
| no_open_set_confidence | 1.0 | 1.0 | 0.163 |
| no_residual | 0.8 | 0.85 | 0.2443 |

## Open-set confidence ablation on unseen v0.3 challenge

| Variant | Top-1 | ECE | Brier |
|---|---:|---:|---:|
| full | 0.7 | 0.1288 | 0.1769 |
| no_open_set_confidence | 0.7 | 0.2203 | 0.2435 |

## Explicit operation audit

Semantic groups audited: `132`; operation counts: `{'ISOLATE': 181, 'ISOLATE_CONFLICT': 9, 'NEGATE': 45, 'NORMALIZE_MORPHOLOGY': 11, 'POLARITY_COMPOSE': 3, 'RELATE': 31, 'RETRACT': 3, 'SEGMENT_COMPOUND': 2, 'STATE_TRANSITION': 33, 'SUPERSEDE': 16, 'TARGET_SHIFT': 11}`.

Normalizations: `{'approved_compound': 2, 'inflection': 11}`; relations: `22/31` applied; residual weight removed: `19.0`.

## Acceptance

- PASS - `regression_top1_at_least_0_98`
- PASS - `v01_challenge_top1_at_least_0_98`
- PASS - `v02_challenge_top1_at_least_0_90`
- PASS - `unseen_v03_challenge_top1_at_least_0_70`
- PASS - `unseen_v03_ece_better_than_v02`

Overall: **PASS**

## Interpretation

v0.3は旧回帰を維持し、v0.2の未見失敗を開発セット上ですべて解消した。新規未見セットではv0.2を0.40上回り、ECEも改善した。

一方、ピリオドを含む同一入力のevent分割、`subsequently`や`revised`の未知談話表現、`bitten`、閉じた複合語`riverbank`、非空間的な`river`言及は未解決である。すべて手作業の機能benchmarkであり、実世界性能を示すものではない。
