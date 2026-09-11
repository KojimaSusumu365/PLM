# PLM-C2 v0.3 Evaluation Report

C2 v0.2と全先行実装を凍結比較対象とした。v0.3 development setで機能診断後、engineとConcept dataをハッシュ固定して新規challengeを作成した。初回challenge実行後のengine/Concept-data調整は行っていない。

凍結engine SHA-256: `95dc8f75e9a5e727d674251056a92850c954995d04bb24d1d89d087fb542cb51`。

新規challenge SHA-256: `1147428babad6704dcd197557dcea81e62c69d53fd59e20594fbdc0515d84f26`。

## Frozen regression (216 test cases)

| Metric | C2 v0.3 | C2 v0.2 | C2 v0.1 | C1 v0.3 | C1 v0.2 | C1 v0.1 | C0 v0.3 | Lexical | Δ v0.3-v0.2 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| top1_accuracy | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 0.8333 | 0.5833 | 0.0 |
| top5_recall | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 0.8889 | 0.8056 | 0.0 |
| mrr | 0.9514 | 0.9514 | 0.9514 | 0.9514 | 0.9514 | 0.9514 | 0.8083 | 0.7431 | 0.0 |
| macro_f1 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 0.8894 | 0.7152 | 0.0 |
| unresolved_precision | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 0.9231 | 0.3333 | 0.0 |
| unresolved_recall | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 0.6 | 0.4 | 0.0 |
| contradiction_rejection | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 0.7333 | 0.2667 | 0.0 |
| coverage | 0.7222 | 0.7222 | 0.7222 | 0.7222 | 0.7222 | 0.7222 | 0.8194 | 0.6667 | 0.0 |
| selective_accuracy | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 0.8136 | 0.7083 | 0.0 |
| expected_calibration_error | 0.1409 | 0.1846 | 0.2016 | 0.2016 | 0.1655 | 0.1655 | 0.0874 | 0.2288 | -0.0437 |
| brier_score | 0.0199 | 0.0363 | 0.0802 | 0.0802 | 0.0567 | 0.0567 | 0.1537 | 0.2717 | -0.0164 |

C2 v0.3 Top-1 95% cluster-bootstrap CI: `[1.0000, 1.0000]`

C2 v0.3 - v0.2 Top-1 delta 95% CI: `[0.0000, 0.0000]`

## Known C1 v0.1 challenge (60 cases)

| Metric | C2 v0.3 | C2 v0.2 | C2 v0.1 | C1 v0.3 | C1 v0.2 | C1 v0.1 | C0 v0.3 | Δ v0.3-v0.2 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| top1_accuracy | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 0.2 | 0.1 | 0.0 |
| top5_recall | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 0.55 | 0.5 | 0.0 |
| mrr | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 0.325 | 0.25 | 0.0 |
| macro_f1 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 0.1718 | 0.1032 | 0.0 |
| unresolved_precision | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 0.4 | 0.0 | 0.0 |
| unresolved_recall | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 0.2222 | 0.0 | 0.0 |
| contradiction_rejection | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 0.0 | 0.0 | 0.0 |
| coverage | 0.55 | 0.55 | 0.55 | 0.55 | 0.55 | 0.75 | 0.85 | 0.0 |
| selective_accuracy | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 0.1333 | 0.1176 | 0.0 |
| expected_calibration_error | 0.1404 | 0.1823 | 0.1903 | 0.1903 | 0.1903 | 0.681 | 0.6883 | -0.0419 |
| brier_score | 0.0198 | 0.0354 | 0.0725 | 0.0725 | 0.0725 | 0.5993 | 0.5989 | -0.0156 |

C2 v0.3 Top-1 95% cluster-bootstrap CI: `[1.0000, 1.0000]`

C2 v0.3 - v0.2 Top-1 delta 95% CI: `[0.0000, 0.0000]`

## Known C1 v0.2 challenge (60 cases)

| Metric | C2 v0.3 | C2 v0.2 | C2 v0.1 | C1 v0.3 | C1 v0.2 | C1 v0.1 | C0 v0.3 | Δ v0.3-v0.2 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| top1_accuracy | 1.0 | 1.0 | 1.0 | 1.0 | 0.65 | 0.25 | 0.3 | 0.0 |
| top5_recall | 1.0 | 1.0 | 1.0 | 1.0 | 0.8 | 0.55 | 0.65 | 0.0 |
| mrr | 1.0 | 1.0 | 1.0 | 1.0 | 0.7 | 0.375 | 0.45 | 0.0 |
| macro_f1 | 1.0 | 1.0 | 1.0 | 1.0 | 0.5953 | 0.1524 | 0.2413 | 0.0 |
| unresolved_precision | 1.0 | 1.0 | 1.0 | 1.0 | 0.625 | 0.25 | 0.375 | 0.0 |
| unresolved_recall | 1.0 | 1.0 | 1.0 | 1.0 | 0.7143 | 0.2857 | 0.4286 | 0.0 |
| contradiction_rejection | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 0.0 |
| coverage | 0.65 | 0.65 | 0.65 | 0.65 | 0.6 | 0.6 | 0.6 | 0.0 |
| selective_accuracy | 1.0 | 1.0 | 1.0 | 1.0 | 0.6667 | 0.25 | 0.25 | 0.0 |
| expected_calibration_error | 0.1391 | 0.1756 | 0.1624 | 0.163 | 0.299 | 0.5752 | 0.5467 | -0.0365 |
| brier_score | 0.0194 | 0.0323 | 0.0505 | 0.0506 | 0.2723 | 0.5224 | 0.4932 | -0.0129 |

C2 v0.3 Top-1 95% cluster-bootstrap CI: `[1.0000, 1.0000]`

C2 v0.3 - v0.2 Top-1 delta 95% CI: `[0.0000, 0.0000]`

## Known C1 v0.3 challenge (60 cases)

| Metric | C2 v0.3 | C2 v0.2 | C2 v0.1 | C1 v0.3 | C1 v0.2 | C1 v0.1 | C0 v0.3 | Δ v0.3-v0.2 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| top1_accuracy | 1.0 | 1.0 | 1.0 | 0.7 | 0.3 | 0.25 | 0.2 | 0.0 |
| top5_recall | 1.0 | 1.0 | 1.0 | 0.75 | 0.55 | 0.55 | 0.5 | 0.0 |
| mrr | 1.0 | 1.0 | 1.0 | 0.7125 | 0.375 | 0.35 | 0.3 | 0.0 |
| macro_f1 | 1.0 | 1.0 | 1.0 | 0.7969 | 0.3175 | 0.2175 | 0.2021 | 0.0 |
| unresolved_precision | 1.0 | 1.0 | 1.0 | 0.6 | 0.25 | 0.25 | 0.1429 | 0.0 |
| unresolved_recall | 1.0 | 1.0 | 1.0 | 0.5 | 0.3333 | 0.3333 | 0.1667 | 0.0 |
| contradiction_rejection | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 0.0 |
| coverage | 0.7 | 0.7 | 0.7 | 0.75 | 0.6 | 0.6 | 0.65 | 0.0 |
| selective_accuracy | 1.0 | 1.0 | 1.0 | 0.7333 | 0.3333 | 0.25 | 0.2308 | 0.0 |
| expected_calibration_error | 0.141 | 0.1851 | 0.2002 | 0.1288 | 0.5474 | 0.6484 | 0.6839 | -0.0441 |
| brier_score | 0.0199 | 0.0357 | 0.0635 | 0.1769 | 0.5133 | 0.5642 | 0.6009 | -0.0158 |

C2 v0.3 Top-1 95% cluster-bootstrap CI: `[1.0000, 1.0000]`

C2 v0.3 - v0.2 Top-1 delta 95% CI: `[0.0000, 0.0000]`

## Known C2 v0.1 challenge (60 cases)

| Metric | C2 v0.3 | C2 v0.2 | C2 v0.1 | C1 v0.3 | C1 v0.2 | C1 v0.1 | C0 v0.3 | Δ v0.3-v0.2 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| top1_accuracy | 1.0 | 1.0 | 0.8 | 0.35 | 0.3 | 0.2 | 0.25 | 0.0 |
| top5_recall | 1.0 | 1.0 | 0.95 | 0.55 | 0.55 | 0.5 | 0.55 | 0.0 |
| mrr | 1.0 | 1.0 | 0.875 | 0.4125 | 0.375 | 0.325 | 0.375 | 0.0 |
| macro_f1 | 1.0 | 1.0 | 0.7712 | 0.2868 | 0.2667 | 0.1254 | 0.1841 | 0.0 |
| unresolved_precision | 1.0 | 1.0 | 0.8 | 0.4444 | 0.4286 | 0.2857 | 0.3333 | 0.0 |
| unresolved_recall | 1.0 | 1.0 | 1.0 | 0.5 | 0.375 | 0.25 | 0.25 | 0.0 |
| contradiction_rejection | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 0.0 |
| coverage | 0.6 | 0.6 | 0.5 | 0.55 | 0.65 | 0.65 | 0.7 | 0.0 |
| selective_accuracy | 1.0 | 1.0 | 0.8 | 0.2727 | 0.2308 | 0.1538 | 0.2143 | 0.0 |
| expected_calibration_error | 0.1433 | 0.1964 | 0.2582 | 0.4444 | 0.6175 | 0.6534 | 0.6111 | -0.0531 |
| brier_score | 0.0206 | 0.0412 | 0.2187 | 0.4438 | 0.543 | 0.5887 | 0.5398 | -0.0206 |

C2 v0.3 Top-1 95% cluster-bootstrap CI: `[1.0000, 1.0000]`

C2 v0.3 - v0.2 Top-1 delta 95% CI: `[0.0000, 0.0000]`

## Known C2 v0.2 challenge (60 cases)

| Metric | C2 v0.3 | C2 v0.2 | C2 v0.1 | C1 v0.3 | C1 v0.2 | C1 v0.1 | C0 v0.3 | Δ v0.3-v0.2 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| top1_accuracy | 1.0 | 0.95 | 0.25 | 0.25 | 0.25 | 0.2 | 0.2 | 0.05 |
| top5_recall | 1.0 | 1.0 | 0.95 | 0.95 | 0.95 | 0.9 | 0.9 | 0.0 |
| mrr | 1.0 | 0.9625 | 0.5767 | 0.4767 | 0.4767 | 0.4267 | 0.4267 | 0.0375 |
| macro_f1 | 1.0 | 0.7882 | 0.2064 | 0.2444 | 0.2444 | 0.2222 | 0.2222 | 0.2118 |
| unresolved_precision | 1.0 | 1.0 | 0.4444 | 0.8 | 0.8 | 0.75 | 0.75 | 0.0 |
| unresolved_recall | 1.0 | 1.0 | 0.8 | 0.8 | 0.8 | 0.6 | 0.6 | 0.0 |
| contradiction_rejection | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 0.0 |
| coverage | 0.75 | 0.75 | 0.55 | 0.75 | 0.75 | 0.8 | 0.8 | 0.0 |
| selective_accuracy | 1.0 | 0.9333 | 0.0909 | 0.0667 | 0.0667 | 0.0625 | 0.0625 | 0.0667 |
| expected_calibration_error | 0.1438 | 0.1497 | 0.4807 | 0.7153 | 0.6503 | 0.7063 | 0.7037 | -0.0059 |
| brier_score | 0.0208 | 0.0738 | 0.4485 | 0.572 | 0.5297 | 0.5995 | 0.5961 | -0.053 |

C2 v0.3 Top-1 95% cluster-bootstrap CI: `[1.0000, 1.0000]`

C2 v0.3 - v0.2 Top-1 delta 95% CI: `[0.0000, 0.1500]`

## C2 v0.3 development diagnostic (30 cases)

| Metric | C2 v0.3 | C2 v0.2 | C2 v0.1 | C1 v0.3 | C1 v0.2 | C1 v0.1 | C0 v0.3 | Δ v0.3-v0.2 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| top1_accuracy | 1.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 1.0 |
| top5_recall | 1.0 | 0.9 | 0.9 | 0.9 | 0.9 | 0.9 | 0.9 | 0.1 |
| mrr | 1.0 | 0.3833 | 0.3833 | 0.2833 | 0.2833 | 0.2833 | 0.2833 | 0.6167 |
| macro_f1 | 1.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 1.0 |
| unresolved_precision | 1.0 | 0.0 | 0.0 | None | None | None | None | 1.0 |
| unresolved_recall | 1.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 1.0 |
| contradiction_rejection | None | None | None | None | None | None | None | None |
| coverage | 0.9 | 0.8 | 0.8 | 1.0 | 1.0 | 1.0 | 1.0 | 0.1 |
| selective_accuracy | 1.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 1.0 |
| expected_calibration_error | 0.1399 | 0.7945 | 0.7181 | 0.8148 | 0.8148 | 0.8374 | 0.8374 | -0.6546 |
| brier_score | 0.0196 | 0.6333 | 0.5485 | 0.6675 | 0.6675 | 0.7089 | 0.7089 | -0.6137 |

C2 v0.3 Top-1 95% cluster-bootstrap CI: `[1.0000, 1.0000]`

C2 v0.3 - v0.2 Top-1 delta 95% CI: `[1.0000, 1.0000]`

## Unseen C2 v0.3 challenge (72 cases)

| Metric | C2 v0.3 | C2 v0.2 | C2 v0.1 | C1 v0.3 | C1 v0.2 | C1 v0.1 | C0 v0.3 | Δ v0.3-v0.2 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| top1_accuracy | 0.9583 | 0.4167 | 0.375 | 0.3333 | 0.3333 | 0.3333 | 0.2917 | 0.5416 |
| top5_recall | 1.0 | 0.9583 | 0.9583 | 0.9167 | 0.9167 | 0.875 | 0.875 | 0.0417 |
| mrr | 0.9688 | 0.6528 | 0.6215 | 0.5174 | 0.5174 | 0.5069 | 0.4757 | 0.316 |
| macro_f1 | 0.9587 | 0.3413 | 0.318 | 0.2735 | 0.2735 | 0.2587 | 0.2358 | 0.6174 |
| unresolved_precision | 1.0 | 0.5714 | 0.5714 | 1.0 | 1.0 | 1.0 | 1.0 | 0.4286 |
| unresolved_recall | 1.0 | 0.8 | 0.8 | 0.6 | 0.6 | 0.4 | 0.4 | 0.2 |
| contradiction_rejection | None | None | None | None | None | None | None | None |
| coverage | 0.7917 | 0.7083 | 0.7083 | 0.875 | 0.875 | 0.9167 | 0.9167 | 0.0834 |
| selective_accuracy | 0.9474 | 0.3529 | 0.2941 | 0.2381 | 0.2381 | 0.2727 | 0.2273 | 0.5945 |
| expected_calibration_error | 0.0998 | 0.3751 | 0.4288 | 0.5864 | 0.5593 | 0.5881 | 0.612 | -0.2753 |
| brier_score | 0.0499 | 0.3861 | 0.3917 | 0.4942 | 0.4766 | 0.5018 | 0.5233 | -0.3362 |

C2 v0.3 Top-1 95% cluster-bootstrap CI: `[0.8750, 1.0000]`

C2 v0.3 - v0.2 Top-1 delta 95% CI: `[0.3333, 0.7500]`

### Unseen C2 v0.3 challenge failures

- `revision_reidentified`: expected `CAT`, predicted `ANIMAL`, mean confidence `0.8580`

## Ablation on C2 v0.3 development diagnostic

| Variant | Top-1 | MRR | ECE |
|---|---:|---:|---:|
| full | 1.0 | 1.0 | 0.1399 |
| no_generalized_revision_roles | 0.7 | 0.775 | 0.1591 |
| no_extended_coreference | 0.7 | 0.7833 | 0.1585 |
| no_role_affordances | 0.7 | 0.9 | 0.1578 |
| no_japanese_correction_scope | 0.9 | 0.925 | 0.0403 |
| no_relation_frames | 1.0 | 1.0 | 0.1399 |
| no_relation_aware_calibration | 1.0 | 1.0 | 0.1798 |

## Relation contract and Claim Graph audit

Semantic groups audited: `278`; graph invariant failures: `{}`; contract failures: `0`.

Relation frames: `144`; types: `{'COREFERENCE': 15, 'FINANCIAL_AFFORDANCE': 38, 'REVISION': 45, 'SPATIAL_ASSOCIATION': 46}`; voices: `{'active': 81, 'n/a': 60, 'passive': 3}`.

Node types: `{'CLAUSE': 393, 'CONCEPT': 3058, 'ENTITY': 303, 'EVENT': 393, 'EVIDENCE': 644, 'REFERENCE': 15, 'RELATION': 84, 'RELATION_FRAME': 144, 'SOURCE': 338}`.

Edge relations: `{'ABOUT': 1372, 'CONTAINS': 393, 'CONTRADICTS': 90, 'DESCRIBES': 393, 'DOES_NOT_GROUND': 35, 'FRAME_OF': 99, 'GROUNDS': 49, 'MAPS_TO': 99, 'NEXT_DISTINCT_TARGET': 20, 'REFERS_BACK_TO': 30, 'RESOLVES_TO': 15, 'SAME_TARGET_SEQUENCE': 95, 'SUPERSEDES': 41, 'SUPERSEDES_CLAUSE': 45, 'SUPPORTS': 554, 'YIELDS': 887}`.

Operations: `{'INFER_AGENTIVE_AFFORDANCE': 7, 'INFER_ROLE_AFFORDANCE': 10, 'ISOLATE': 393, 'ISOLATE_CONFLICT': 17, 'MARK_CONTRASTIVE_CORRECTION': 11, 'NEGATE': 90, 'NORMALIZE_IRREGULAR': 2, 'NORMALIZE_MORPHOLOGY': 13, 'POLARITY_COMPOSE': 3, 'PROPAGATE_CORRECTION_SCOPE': 3, 'RELATE': 67, 'RELATION_GATE': 19, 'RESOLVE_DISCOURSE_REFERENCE': 10, 'RESOLVE_REFERENCE': 5, 'RETRACT': 4, 'SEGMENT_COMPOUND': 5, 'SPLIT_REVISION_BOUNDARY': 10, 'STATE_TRANSITION': 79, 'SUPERSEDE': 41, 'TARGET_SHIFT': 20}`.

Frame sample full `{'node_count': 24, 'edge_count': 34, 'frame_count': 2, 'r1_ready': True}` / disabled `{'node_count': 22, 'edge_count': 28, 'frame_count': 0, 'r1_ready': False}`.

## Acceptance

- PASS - `engine_hash_matches_freeze_record`
- PASS - `concept_hash_matches_freeze_record`
- PASS - `development_hash_matches_freeze_record`
- PASS - `all_prior_sets_top1_at_least_0_98`
- PASS - `development_top1_at_least_0_98`
- PASS - `unseen_c2_v03_top1_at_least_0_90`
- PASS - `unseen_c2_v03_beats_frozen_v02`
- PASS - `unseen_c2_v03_ece_at_most_0_15`
- PASS - `first_unseen_run_is_reproduced`
- PASS - `all_accuracy_features_have_ablation_effect`
- PASS - `relation_calibration_improves_development_ece`
- PASS - `relation_frame_ablation_removes_frames`
- PASS - `required_relation_frame_types_observed`
- PASS - `claim_graph_invariants_hold`
- PASS - `relation_contracts_are_r1_ready`

Overall: **PASS**

## Interpretation

C2 v0.3は先行6評価セットと開発診断をすべて解決し、新規未見セットでTop-1 0.9583を達成した。同セットの凍結C2 v0.2は0.4167で、差は0.5416だった。ECEは0.0998で目標0.15以下を満たした。

Relation Frame契約とClaim Graph schema v2は全監査ケースで整合し、R1実験開始条件を満たした。ただし、未見失敗`reidentified`が示すように改訂役割はまだ閉じた形態意味集合である。評価は同一開発セッションで作成した手作業benchmarkであり、外部コーパスではない。
