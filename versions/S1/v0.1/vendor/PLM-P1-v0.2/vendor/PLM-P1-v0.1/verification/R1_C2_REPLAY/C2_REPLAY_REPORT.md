# PLM-C2 v0.4 評価レポート

Relationの正解照合、個体照応、訂正先の根拠、R1観察境界を評価した。
全データは同じ開発過程で作成した内部評価であり、外部独立評価ではない。holdoutは実行を保留した分割である。

## 分類とRelation意味評価

| 分割 | 件数 | v0.4分類 | v0.3分類 | v0.4検証済みP/R/F1 | v0.4全候補P/R/F1 |
|---|---:|---:|---:|---|---|
| development | 23 | 1.0 | 0.8261 | 1.0/1.0/1.0 | 0.5769/1.0/0.7317 |
| holdout | 32 | 0.9062 | 0.6875 | 1.0/0.913/0.9545 | 0.5833/0.913/0.7119 |

検証済みはrule_checkedの部分集合。全候補には採用不可・未対応の候補も含む。P/R/F1は別途注釈した主体・述語・対象・態・否定・訂正先・照応先との照合であり、形式検証とは別である。

## 既存評価の回帰

| データ | v0.4 Top-1 | v0.3 Top-1 |
|---|---:|---:|
| benchmark_v03.json | 1.0 | 1.0 |
| challenge_c1_v01.json | 1.0 | 1.0 |
| challenge_c1_v02.json | 1.0 | 1.0 |
| challenge_c1_v03.json | 1.0 | 1.0 |
| challenge_c2_v01.json | 1.0 | 1.0 |
| challenge_c2_v02.json | 1.0 | 1.0 |
| development_c2_v03.json | 1.0 | 1.0 |
| challenge_c2_v03.json | 1.0 | 0.9583 |

holdout Top-1の95% cluster-bootstrap CI: {"lower": 0.7812, "upper": 1.0, "method": "template-group cluster percentile bootstrap", "samples": 2000, "clusters": 32, "seed": 1701}

## holdoutの失敗

- test_passive_agent_manager: 正解 UNRESOLVED / 出力 RIVER_BANK / 確信度 0.9286
- test_disbursed: 正解 FINANCIAL_BANK / 出力 UNRESOLVED / 確信度 0.7778
- test_unregistered_predicate: 正解 DOG / 出力 ANIMAL / 確信度 0.5556
- Relation test_disbursed: FP=0, FN=1
- Relation test_unregistered_predicate: FP=0, FN=1

## 校正と保留

30件の専用校正データで単調な確信度変換を推定。分類・保留の正誤を目的とし、個体同定の正しさとは区別する。

| 分割 | 校正前ECE | 校正後ECE | 校正前Brier | 校正後Brier |
|---|---:|---:|---:|---:|
| development | 0.2217 | 0.1525 | 0.07 | 0.0352 |
| holdout | 0.1781 | 0.0782 | 0.1156 | 0.0901 |

閾値別の採用率と精度、信頼区間、校正区間ごとの件数はJSONを参照。校正の改善は全分布への保証ではない。

## R1境界・反事実的変形

- 意味を保つ態変換・接頭辞・無関係文、および否定反転: 9/9。
- R1はobserve_only。全候補に根拠・検証状態を付け、推論採用は常に無効。空入力は準備完了にしない。
- export時に再検証し、壊れたSchema・参照・グラフを拒否。意味が未検証の候補はquarantinedとして表示。

## 機能除去診断

| 除去機能 | 検証済みF1 | 個体制約違反数 |
|---|---:|---:|
| no_semantic_roles | 0.8 | 0 |
| no_instance_coreference | 0.75 | 4 |
| no_grounded_revisions | 0.9286 | 0 |

## 受入判定

- PASS: all_prior_label_accuracy_at_least_0_98
- PASS: development_label_accuracy_1
- PASS: development_checked_semantic_f1_at_least_0_98
- PASS: development_instance_constraints
- PASS: holdout_label_accuracy_at_least_0_85
- PASS: holdout_checked_precision_at_least_0_90
- PASS: holdout_checked_recall_at_least_0_75
- PASS: holdout_instance_constraints
- PASS: schema_and_graph_contracts
- PASS: inference_never_enabled
- PASS: metamorphic_pairs_pass
- PASS: calibration_input_disjoint
- PASS: calibrator_bound_to_calibration_data
- PASS: complete_runtime_freeze_matches
- PASS: first_holdout_run_reproduced
- PASS: frozen_v03_reference_preserved

全体: PASS

## 制約

英語の限定構文と小さなConcept辞書に依存する。校正データ30件・holdout32件は小規模で、構文・語彙も完全独立ではない。複雑な照応・省略・引用・未知述語・一般的な構文解析は未解決。R1の自動推論や本番開放は今回の成果に含まれない。
