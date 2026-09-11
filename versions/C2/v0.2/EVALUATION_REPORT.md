# PLM-C2 v0.2 Evaluation Report

C2 v0.1と全先行実装を凍結比較対象とした。C2 v0.1 challengeを開発診断に使用し、v0.2 engineとConcept dataをハッシュ固定してから新規challengeを作成した。新規challenge初回実行後のengine/Concept-data調整は行っていない。

凍結engine SHA-256: `4ccc0aa39f2b551c7a392bab2a69948c45a3752575542bda2aa49d5583a59c50`。

新規challenge SHA-256: `0a35d31af985633987ae465e7c91c340be20cabcbe820431981b5de208804717`。

## Frozen regression (216 test cases)

| Metric | C2 v0.2 | C2 v0.1 | C1 v0.3 | C1 v0.2 | C1 v0.1 | C0 v0.3 | Lexical | Δ v0.2-v0.1 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| top1_accuracy | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 0.8333 | 0.5833 | 0.0 |
| top5_recall | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 0.8889 | 0.8056 | 0.0 |
| mrr | 0.9514 | 0.9514 | 0.9514 | 0.9514 | 0.9514 | 0.8083 | 0.7431 | 0.0 |
| macro_f1 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 0.8894 | 0.7152 | 0.0 |
| unresolved_precision | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 0.9231 | 0.3333 | 0.0 |
| unresolved_recall | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 0.6 | 0.4 | 0.0 |
| contradiction_rejection | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 0.7333 | 0.2667 | 0.0 |
| coverage | 0.7222 | 0.7222 | 0.7222 | 0.7222 | 0.7222 | 0.8194 | 0.6667 | 0.0 |
| selective_accuracy | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 0.8136 | 0.7083 | 0.0 |
| expected_calibration_error | 0.1846 | 0.2016 | 0.2016 | 0.1655 | 0.1655 | 0.0874 | 0.2288 | -0.017 |
| brier_score | 0.0363 | 0.0802 | 0.0802 | 0.0567 | 0.0567 | 0.1537 | 0.2717 | -0.0439 |

C2 v0.2 Top-1 95% cluster-bootstrap CI: `[1.0000, 1.0000]`

C2 v0.2 - v0.1 Top-1 delta 95% CI: `[0.0000, 0.0000]`

## Known C1 v0.1 challenge (60 cases)

| Metric | C2 v0.2 | C2 v0.1 | C1 v0.3 | C1 v0.2 | C1 v0.1 | C0 v0.3 | Δ v0.2-v0.1 |
|---|---:|---:|---:|---:|---:|---:|---:|
| top1_accuracy | 1.0 | 1.0 | 1.0 | 1.0 | 0.2 | 0.1 | 0.0 |
| top5_recall | 1.0 | 1.0 | 1.0 | 1.0 | 0.55 | 0.5 | 0.0 |
| mrr | 1.0 | 1.0 | 1.0 | 1.0 | 0.325 | 0.25 | 0.0 |
| macro_f1 | 1.0 | 1.0 | 1.0 | 1.0 | 0.1718 | 0.1032 | 0.0 |
| unresolved_precision | 1.0 | 1.0 | 1.0 | 1.0 | 0.4 | 0.0 | 0.0 |
| unresolved_recall | 1.0 | 1.0 | 1.0 | 1.0 | 0.2222 | 0.0 | 0.0 |
| contradiction_rejection | 1.0 | 1.0 | 1.0 | 1.0 | 0.0 | 0.0 | 0.0 |
| coverage | 0.55 | 0.55 | 0.55 | 0.55 | 0.75 | 0.85 | 0.0 |
| selective_accuracy | 1.0 | 1.0 | 1.0 | 1.0 | 0.1333 | 0.1176 | 0.0 |
| expected_calibration_error | 0.1823 | 0.1903 | 0.1903 | 0.1903 | 0.681 | 0.6883 | -0.008 |
| brier_score | 0.0354 | 0.0725 | 0.0725 | 0.0725 | 0.5993 | 0.5989 | -0.0371 |

C2 v0.2 Top-1 95% cluster-bootstrap CI: `[1.0000, 1.0000]`

C2 v0.2 - v0.1 Top-1 delta 95% CI: `[0.0000, 0.0000]`

## Known C1 v0.2 challenge (60 cases)

| Metric | C2 v0.2 | C2 v0.1 | C1 v0.3 | C1 v0.2 | C1 v0.1 | C0 v0.3 | Δ v0.2-v0.1 |
|---|---:|---:|---:|---:|---:|---:|---:|
| top1_accuracy | 1.0 | 1.0 | 1.0 | 0.65 | 0.25 | 0.3 | 0.0 |
| top5_recall | 1.0 | 1.0 | 1.0 | 0.8 | 0.55 | 0.65 | 0.0 |
| mrr | 1.0 | 1.0 | 1.0 | 0.7 | 0.375 | 0.45 | 0.0 |
| macro_f1 | 1.0 | 1.0 | 1.0 | 0.5953 | 0.1524 | 0.2413 | 0.0 |
| unresolved_precision | 1.0 | 1.0 | 1.0 | 0.625 | 0.25 | 0.375 | 0.0 |
| unresolved_recall | 1.0 | 1.0 | 1.0 | 0.7143 | 0.2857 | 0.4286 | 0.0 |
| contradiction_rejection | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 0.0 |
| coverage | 0.65 | 0.65 | 0.65 | 0.6 | 0.6 | 0.6 | 0.0 |
| selective_accuracy | 1.0 | 1.0 | 1.0 | 0.6667 | 0.25 | 0.25 | 0.0 |
| expected_calibration_error | 0.1756 | 0.1624 | 0.163 | 0.299 | 0.5752 | 0.5467 | 0.0132 |
| brier_score | 0.0323 | 0.0505 | 0.0506 | 0.2723 | 0.5224 | 0.4932 | -0.0182 |

C2 v0.2 Top-1 95% cluster-bootstrap CI: `[1.0000, 1.0000]`

C2 v0.2 - v0.1 Top-1 delta 95% CI: `[0.0000, 0.0000]`

## Known C1 v0.3 challenge (60 cases)

| Metric | C2 v0.2 | C2 v0.1 | C1 v0.3 | C1 v0.2 | C1 v0.1 | C0 v0.3 | Δ v0.2-v0.1 |
|---|---:|---:|---:|---:|---:|---:|---:|
| top1_accuracy | 1.0 | 1.0 | 0.7 | 0.3 | 0.25 | 0.2 | 0.0 |
| top5_recall | 1.0 | 1.0 | 0.75 | 0.55 | 0.55 | 0.5 | 0.0 |
| mrr | 1.0 | 1.0 | 0.7125 | 0.375 | 0.35 | 0.3 | 0.0 |
| macro_f1 | 1.0 | 1.0 | 0.7969 | 0.3175 | 0.2175 | 0.2021 | 0.0 |
| unresolved_precision | 1.0 | 1.0 | 0.6 | 0.25 | 0.25 | 0.1429 | 0.0 |
| unresolved_recall | 1.0 | 1.0 | 0.5 | 0.3333 | 0.3333 | 0.1667 | 0.0 |
| contradiction_rejection | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 0.0 |
| coverage | 0.7 | 0.7 | 0.75 | 0.6 | 0.6 | 0.65 | 0.0 |
| selective_accuracy | 1.0 | 1.0 | 0.7333 | 0.3333 | 0.25 | 0.2308 | 0.0 |
| expected_calibration_error | 0.1851 | 0.2002 | 0.1288 | 0.5474 | 0.6484 | 0.6839 | -0.0151 |
| brier_score | 0.0357 | 0.0635 | 0.1769 | 0.5133 | 0.5642 | 0.6009 | -0.0278 |

C2 v0.2 Top-1 95% cluster-bootstrap CI: `[1.0000, 1.0000]`

C2 v0.2 - v0.1 Top-1 delta 95% CI: `[0.0000, 0.0000]`

## Development C2 v0.1 challenge (60 cases)

| Metric | C2 v0.2 | C2 v0.1 | C1 v0.3 | C1 v0.2 | C1 v0.1 | C0 v0.3 | Δ v0.2-v0.1 |
|---|---:|---:|---:|---:|---:|---:|---:|
| top1_accuracy | 1.0 | 0.8 | 0.35 | 0.3 | 0.2 | 0.25 | 0.2 |
| top5_recall | 1.0 | 0.95 | 0.55 | 0.55 | 0.5 | 0.55 | 0.05 |
| mrr | 1.0 | 0.875 | 0.4125 | 0.375 | 0.325 | 0.375 | 0.125 |
| macro_f1 | 1.0 | 0.7712 | 0.2868 | 0.2667 | 0.1254 | 0.1841 | 0.2288 |
| unresolved_precision | 1.0 | 0.8 | 0.4444 | 0.4286 | 0.2857 | 0.3333 | 0.2 |
| unresolved_recall | 1.0 | 1.0 | 0.5 | 0.375 | 0.25 | 0.25 | 0.0 |
| contradiction_rejection | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 0.0 |
| coverage | 0.6 | 0.5 | 0.55 | 0.65 | 0.65 | 0.7 | 0.1 |
| selective_accuracy | 1.0 | 0.8 | 0.2727 | 0.2308 | 0.1538 | 0.2143 | 0.2 |
| expected_calibration_error | 0.1964 | 0.2582 | 0.4444 | 0.6175 | 0.6534 | 0.6111 | -0.0618 |
| brier_score | 0.0412 | 0.2187 | 0.4438 | 0.543 | 0.5887 | 0.5398 | -0.1775 |

C2 v0.2 Top-1 95% cluster-bootstrap CI: `[1.0000, 1.0000]`

C2 v0.2 - v0.1 Top-1 delta 95% CI: `[0.0500, 0.4000]`

## Unseen C2 v0.2 challenge (60 cases)

| Metric | C2 v0.2 | C2 v0.1 | C1 v0.3 | C1 v0.2 | C1 v0.1 | C0 v0.3 | Δ v0.2-v0.1 |
|---|---:|---:|---:|---:|---:|---:|---:|
| top1_accuracy | 0.95 | 0.25 | 0.25 | 0.25 | 0.2 | 0.2 | 0.7 |
| top5_recall | 1.0 | 0.95 | 0.95 | 0.95 | 0.9 | 0.9 | 0.05 |
| mrr | 0.9625 | 0.5767 | 0.4767 | 0.4767 | 0.4267 | 0.4267 | 0.3858 |
| macro_f1 | 0.7882 | 0.2064 | 0.2444 | 0.2444 | 0.2222 | 0.2222 | 0.5818 |
| unresolved_precision | 1.0 | 0.4444 | 0.8 | 0.8 | 0.75 | 0.75 | 0.5556 |
| unresolved_recall | 1.0 | 0.8 | 0.8 | 0.8 | 0.6 | 0.6 | 0.2 |
| contradiction_rejection | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 0.0 |
| coverage | 0.75 | 0.55 | 0.75 | 0.75 | 0.8 | 0.8 | 0.2 |
| selective_accuracy | 0.9333 | 0.0909 | 0.0667 | 0.0667 | 0.0625 | 0.0625 | 0.8424 |
| expected_calibration_error | 0.1497 | 0.4807 | 0.7153 | 0.6503 | 0.7063 | 0.7037 | -0.331 |
| brier_score | 0.0738 | 0.4485 | 0.572 | 0.5297 | 0.5995 | 0.5961 | -0.3747 |

C2 v0.2 Top-1 95% cluster-bootstrap CI: `[0.8500, 1.0000]`

C2 v0.2 - v0.1 Top-1 delta 95% CI: `[0.5000, 0.8500]`

### Unseen C2 v0.2 challenge failures

- `revision_reclassified_colon`: expected `CAT`, predicted `ANIMAL`, mean confidence `0.8101`

## Ablation on C2 v0.1 development challenge

| Variant | Top-1 | MRR | ECE |
|---|---:|---:|---:|
| full | 1.0 | 1.0 | 0.1964 |
| no_structural_revision_boundaries | 0.95 | 0.9625 | 0.1472 |
| no_contrastive_corrections | 0.95 | 0.95 | 0.1444 |
| no_ordered_coreference | 0.95 | 0.9625 | 0.1477 |
| no_agentive_affordances | 0.95 | 1.0 | 0.153 |
| no_conservative_calibration | 1.0 | 1.0 | 0.2466 |
| no_typed_claim_graph | 1.0 | 1.0 | 0.1964 |

## Typed Claim Graph audit

Semantic groups audited: `171`; invariant failures: `{}`.

Node types: `{'CLAUSE': 243, 'CONCEPT': 1881, 'ENTITY': 191, 'EVENT': 243, 'EVIDENCE': 393, 'REFERENCE': 5, 'RELATION': 49, 'SOURCE': 207}`.

Edge relations: `{'ABOUT': 835, 'CONTAINS': 243, 'CONTRADICTS': 55, 'DESCRIBES': 243, 'DOES_NOT_GROUND': 20, 'GROUNDS': 29, 'NEXT_DISTINCT_TARGET': 16, 'REFERS_BACK_TO': 5, 'RESOLVES_TO': 5, 'SAME_TARGET_SEQUENCE': 56, 'SUPERSEDES': 25, 'SUPPORTS': 338, 'YIELDS': 447}`.

Operations: `{'INFER_AGENTIVE_AFFORDANCE': 7, 'ISOLATE': 243, 'ISOLATE_CONFLICT': 15, 'MARK_CONTRASTIVE_CORRECTION': 4, 'NEGATE': 55, 'NORMALIZE_IRREGULAR': 2, 'NORMALIZE_MORPHOLOGY': 11, 'POLARITY_COMPOSE': 3, 'RELATE': 42, 'RELATION_GATE': 10, 'RESOLVE_REFERENCE': 5, 'RETRACT': 4, 'SEGMENT_COMPOUND': 5, 'SPLIT_REVISION_BOUNDARY': 4, 'STATE_TRANSITION': 52, 'SUPERSEDE': 25, 'TARGET_SHIFT': 16}`.

Reference links: `5`; agentive relation items: `7`.

Graph sample full `{'node_count': 22, 'edge_count': 20}` / disabled `{'node_count': 0, 'edge_count': 0}`.

## Acceptance

- PASS - `engine_hash_matches_freeze_record`
- PASS - `concept_hash_matches_freeze_record`
- PASS - `regression_top1_at_least_0_98`
- PASS - `c1_v01_challenge_top1_at_least_0_98`
- PASS - `c1_v02_challenge_top1_at_least_0_98`
- PASS - `c1_v03_challenge_top1_at_least_0_98`
- PASS - `c2_v01_challenge_top1_at_least_0_98`
- PASS - `unseen_c2_v02_top1_at_least_0_85`
- PASS - `unseen_c2_v02_beats_frozen_v01`
- PASS - `unseen_c2_v02_ece_at_most_0_22`
- PASS - `all_accuracy_features_have_ablation_effect`
- PASS - `calibration_improves_development_ece`
- PASS - `claim_graph_invariants_hold`

Overall: **PASS**

## Interpretation

C2 v0.2は先行5評価セットをすべて解決し、新規未見セットでTop-1 0.95を達成した。同セットの凍結C2 v0.1は0.25であり、差は0.70だった。ECEは0.1497で目標0.22以下を満たした。

残る失敗は未登録の改訂役割語`reclassified`である。参照解決は順序を明示するformer/latter/first/secondに限定され、汎用的な代名詞・談話照応器ではない。agentive affordanceも閉じた動詞集合であり、各データセットは手作業の機能benchmarkである。
