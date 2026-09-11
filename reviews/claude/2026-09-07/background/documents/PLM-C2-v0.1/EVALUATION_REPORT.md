# PLM-C2 v0.1 Evaluation Report

C1 v0.3を凍結比較対象とし、C1 v0.3 challengeを開発診断として使用した。C2完成後に新規未見challengeを固定し、初回実行後のengine/Concept-data調整は行っていない。

新規challenge SHA-256: `fd87b7663e9912b4898c8023f65c54955d826fdf8782631adb12d490ec6c1c85`。

## Frozen regression (216 test cases)

| Metric | C2 v0.1 | C1 v0.3 | C1 v0.2 | C1 v0.1 | C0 v0.3 | Lexical | Δ C2-C1v0.3 |
|---|---:|---:|---:|---:|---:|---:|---:|
| top1_accuracy | 1.0 | 1.0 | 1.0 | 1.0 | 0.8333 | 0.5833 | 0.0 |
| top5_recall | 1.0 | 1.0 | 1.0 | 1.0 | 0.8889 | 0.8056 | 0.0 |
| mrr | 0.9514 | 0.9514 | 0.9514 | 0.9514 | 0.8083 | 0.7431 | 0.0 |
| macro_f1 | 1.0 | 1.0 | 1.0 | 1.0 | 0.8894 | 0.7152 | 0.0 |
| unresolved_precision | 1.0 | 1.0 | 1.0 | 1.0 | 0.9231 | 0.3333 | 0.0 |
| unresolved_recall | 1.0 | 1.0 | 1.0 | 1.0 | 0.6 | 0.4 | 0.0 |
| contradiction_rejection | 1.0 | 1.0 | 1.0 | 1.0 | 0.7333 | 0.2667 | 0.0 |
| coverage | 0.7222 | 0.7222 | 0.7222 | 0.7222 | 0.8194 | 0.6667 | 0.0 |
| selective_accuracy | 1.0 | 1.0 | 1.0 | 1.0 | 0.8136 | 0.7083 | 0.0 |
| expected_calibration_error | 0.2016 | 0.2016 | 0.1655 | 0.1655 | 0.0874 | 0.2288 | 0.0 |
| brier_score | 0.0802 | 0.0802 | 0.0567 | 0.0567 | 0.1537 | 0.2717 | 0.0 |

C2 Top-1 95% cluster-bootstrap CI: `[1.0000, 1.0000]`

C2-C1 v0.3 Top-1 delta 95% CI: `[0.0000, 0.0000]`

## Known C1 v0.1 challenge (60 cases)

| Metric | C2 v0.1 | C1 v0.3 | C1 v0.2 | C1 v0.1 | C0 v0.3 | Δ C2-C1v0.3 |
|---|---:|---:|---:|---:|---:|---:|
| top1_accuracy | 1.0 | 1.0 | 1.0 | 0.2 | 0.1 | 0.0 |
| top5_recall | 1.0 | 1.0 | 1.0 | 0.55 | 0.5 | 0.0 |
| mrr | 1.0 | 1.0 | 1.0 | 0.325 | 0.25 | 0.0 |
| macro_f1 | 1.0 | 1.0 | 1.0 | 0.1718 | 0.1032 | 0.0 |
| unresolved_precision | 1.0 | 1.0 | 1.0 | 0.4 | 0.0 | 0.0 |
| unresolved_recall | 1.0 | 1.0 | 1.0 | 0.2222 | 0.0 | 0.0 |
| contradiction_rejection | 1.0 | 1.0 | 1.0 | 0.0 | 0.0 | 0.0 |
| coverage | 0.55 | 0.55 | 0.55 | 0.75 | 0.85 | 0.0 |
| selective_accuracy | 1.0 | 1.0 | 1.0 | 0.1333 | 0.1176 | 0.0 |
| expected_calibration_error | 0.1903 | 0.1903 | 0.1903 | 0.681 | 0.6883 | 0.0 |
| brier_score | 0.0725 | 0.0725 | 0.0725 | 0.5993 | 0.5989 | 0.0 |

C2 Top-1 95% cluster-bootstrap CI: `[1.0000, 1.0000]`

C2-C1 v0.3 Top-1 delta 95% CI: `[0.0000, 0.0000]`

## Known C1 v0.2 challenge (60 cases)

| Metric | C2 v0.1 | C1 v0.3 | C1 v0.2 | C1 v0.1 | C0 v0.3 | Δ C2-C1v0.3 |
|---|---:|---:|---:|---:|---:|---:|
| top1_accuracy | 1.0 | 1.0 | 0.65 | 0.25 | 0.3 | 0.0 |
| top5_recall | 1.0 | 1.0 | 0.8 | 0.55 | 0.65 | 0.0 |
| mrr | 1.0 | 1.0 | 0.7 | 0.375 | 0.45 | 0.0 |
| macro_f1 | 1.0 | 1.0 | 0.5953 | 0.1524 | 0.2413 | 0.0 |
| unresolved_precision | 1.0 | 1.0 | 0.625 | 0.25 | 0.375 | 0.0 |
| unresolved_recall | 1.0 | 1.0 | 0.7143 | 0.2857 | 0.4286 | 0.0 |
| contradiction_rejection | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 0.0 |
| coverage | 0.65 | 0.65 | 0.6 | 0.6 | 0.6 | 0.0 |
| selective_accuracy | 1.0 | 1.0 | 0.6667 | 0.25 | 0.25 | 0.0 |
| expected_calibration_error | 0.1624 | 0.163 | 0.299 | 0.5752 | 0.5467 | -0.0006 |
| brier_score | 0.0505 | 0.0506 | 0.2723 | 0.5224 | 0.4932 | -0.0001 |

C2 Top-1 95% cluster-bootstrap CI: `[1.0000, 1.0000]`

C2-C1 v0.3 Top-1 delta 95% CI: `[0.0000, 0.0000]`

## Development C1 v0.3 challenge (60 cases)

| Metric | C2 v0.1 | C1 v0.3 | C1 v0.2 | C1 v0.1 | C0 v0.3 | Δ C2-C1v0.3 |
|---|---:|---:|---:|---:|---:|---:|
| top1_accuracy | 1.0 | 0.7 | 0.3 | 0.25 | 0.2 | 0.3 |
| top5_recall | 1.0 | 0.75 | 0.55 | 0.55 | 0.5 | 0.25 |
| mrr | 1.0 | 0.7125 | 0.375 | 0.35 | 0.3 | 0.2875 |
| macro_f1 | 1.0 | 0.7969 | 0.3175 | 0.2175 | 0.2021 | 0.2031 |
| unresolved_precision | 1.0 | 0.6 | 0.25 | 0.25 | 0.1429 | 0.4 |
| unresolved_recall | 1.0 | 0.5 | 0.3333 | 0.3333 | 0.1667 | 0.5 |
| contradiction_rejection | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 0.0 |
| coverage | 0.7 | 0.75 | 0.6 | 0.6 | 0.65 | -0.05 |
| selective_accuracy | 1.0 | 0.7333 | 0.3333 | 0.25 | 0.2308 | 0.2667 |
| expected_calibration_error | 0.2002 | 0.1288 | 0.5474 | 0.6484 | 0.6839 | 0.0714 |
| brier_score | 0.0635 | 0.1769 | 0.5133 | 0.5642 | 0.6009 | -0.1134 |

C2 Top-1 95% cluster-bootstrap CI: `[1.0000, 1.0000]`

C2-C1 v0.3 Top-1 delta 95% CI: `[0.1000, 0.5000]`

## Unseen C2 v0.1 challenge (60 cases)

| Metric | C2 v0.1 | C1 v0.3 | C1 v0.2 | C1 v0.1 | C0 v0.3 | Δ C2-C1v0.3 |
|---|---:|---:|---:|---:|---:|---:|
| top1_accuracy | 0.8 | 0.35 | 0.3 | 0.2 | 0.25 | 0.45 |
| top5_recall | 0.95 | 0.55 | 0.55 | 0.5 | 0.55 | 0.4 |
| mrr | 0.875 | 0.4125 | 0.375 | 0.325 | 0.375 | 0.4625 |
| macro_f1 | 0.7712 | 0.2868 | 0.2667 | 0.1254 | 0.1841 | 0.4844 |
| unresolved_precision | 0.8 | 0.4444 | 0.4286 | 0.2857 | 0.3333 | 0.3556 |
| unresolved_recall | 1.0 | 0.5 | 0.375 | 0.25 | 0.25 | 0.5 |
| contradiction_rejection | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 0.0 |
| coverage | 0.5 | 0.55 | 0.65 | 0.65 | 0.7 | -0.05 |
| selective_accuracy | 0.8 | 0.2727 | 0.2308 | 0.1538 | 0.2143 | 0.5273 |
| expected_calibration_error | 0.2582 | 0.4444 | 0.6175 | 0.6534 | 0.6111 | -0.1862 |
| brier_score | 0.2187 | 0.4438 | 0.543 | 0.5887 | 0.5398 | -0.2251 |

C2 Top-1 95% cluster-bootstrap CI: `[0.6000, 0.9500]`

C2-C1 v0.3 Top-1 delta 95% CI: `[0.2500, 0.6500]`

### Unseen C2 challenge failures

- `coreference_latter`: expected `CAT`, predicted `ANIMAL`, mean confidence `0.7805`
- `correction_rather`: expected `CAT`, predicted `UNRESOLVED`, mean confidence `1.0000`
- `relation_sponsored_cleanup`: expected `FINANCIAL_BANK`, predicted `UNRESOLVED`, mean confidence `0.3734`
- `revision_colon`: expected `CAT`, predicted `ANIMAL`, mean confidence `0.7805`

## Ablation on C1 v0.3 development challenge

| Variant | Top-1 | MRR | ECE |
|---|---:|---:|---:|
| full | 1.0 | 1.0 | 0.2002 |
| no_sentence_boundaries | 0.95 | 0.95 | 0.1679 |
| no_temporal_relations | 0.95 | 0.95 | 0.1679 |
| no_revision_relations | 0.95 | 0.9625 | 0.1677 |
| no_irregular_lemmas | 0.95 | 0.95 | 0.174 |
| no_closed_compounds | 0.95 | 0.95 | 0.1718 |
| no_typed_relation_gate | 0.95 | 0.95 | 0.126 |
| no_typed_claim_graph | 1.0 | 1.0 | 0.2002 |

## Typed Claim Graph audit

Semantic groups audited: `151`; invariant failures: `{}`.

Node types: `{'CLAUSE': 210, 'CONCEPT': 1661, 'ENTITY': 173, 'EVENT': 210, 'EVIDENCE': 334, 'RELATION': 35, 'SOURCE': 182}`.

Edge relations: `{'ABOUT': 703, 'CONTAINS': 210, 'CONTRADICTS': 50, 'DESCRIBES': 210, 'DOES_NOT_GROUND': 11, 'GROUNDS': 24, 'NEXT_DISTINCT_TARGET': 16, 'SAME_TARGET_SEQUENCE': 43, 'SUPERSEDES': 18, 'SUPPORTS': 284, 'YIELDS': 369}`.

Operations: `{'ISOLATE': 210, 'ISOLATE_CONFLICT': 15, 'NEGATE': 50, 'NORMALIZE_IRREGULAR': 2, 'NORMALIZE_MORPHOLOGY': 11, 'POLARITY_COMPOSE': 3, 'RELATE': 35, 'RELATION_GATE': 4, 'RETRACT': 4, 'SEGMENT_COMPOUND': 5, 'STATE_TRANSITION': 40, 'SUPERSEDE': 18, 'TARGET_SHIFT': 16}`; relation-gated Evidence: `4`.

Graph sample full `{'node_count': 18, 'edge_count': 10}` / disabled `{'node_count': 0, 'edge_count': 0}`.

## Acceptance

- PASS - `regression_top1_at_least_0_98`
- PASS - `v01_challenge_top1_at_least_0_98`
- PASS - `v02_challenge_top1_at_least_0_98`
- PASS - `v03_challenge_top1_at_least_0_95`
- PASS - `unseen_c2_challenge_top1_at_least_0_75`
- PASS - `unseen_c2_beats_c1_v03`
- PASS - `unseen_c2_ece_at_most_0_30`
- PASS - `all_accuracy_features_have_ablation_effect`
- PASS - `claim_graph_invariants_hold`

Overall: **PASS**

## Interpretation

C2は旧4セットをすべて解決し、新規未見セットでC1 v0.3を0.45上回った。型付きgraphの参照整合性にも違反はなかった。

残る失敗はcolon内の改訂、`rather`による訂正、スポンサー行為から金融機関へのaffordance推論、`latter`照応である。現在のgraphは明示構造を持つが、汎用構文解析・語用論・世界知識モデルではない。各データセットは手作業の機能benchmarkである。
