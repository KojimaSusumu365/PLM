# PLM-P1 v0.2 数値評価

分割: evaluation

人工構造の数値回復試験です。独立意味評価ではありません。旧評価seedは使わず、符号seedとチャネルseedを分離して交差させています。
全方式で同じ次元数・結合情報・送信エネルギー・候補辞書・公開カタログを使用。送信正規化の単一gainは全方式へ公開。
v01_fixedは旧復号器を同じ等エネルギー条件で再評価した比較です。v0.1当時の64問の結果と直接同じ母集団ではありません。

## 主語・目的語の比較

| 条件 | 方式 | 回復 | 誤回復 | 保留 | 負例誤受理 |
|---|---|---:|---:|---:|---:|
| higher_load | mixed_adaptive | 9/512 | 0 | 503 | 1/1024 |
| higher_load | partitioned_fixed | 284/512 | 18 | 210 | 168/1024 |
| higher_load | projected_adaptive | 0/512 | 0 | 512 | 0/1024 |
| higher_load | projected_fixed | 0/512 | 0 | 512 | 0/1024 |
| higher_load | v01_fixed | 144/512 | 72 | 296 | 286/1024 |
| jitter_only | mixed_adaptive | 512/512 | 0 | 0 | 0/1024 |
| jitter_only | partitioned_fixed | 511/512 | 0 | 1 | 0/1024 |
| jitter_only | projected_adaptive | 512/512 | 0 | 0 | 0/1024 |
| jitter_only | projected_fixed | 508/512 | 0 | 4 | 0/1024 |
| jitter_only | v01_fixed | 491/512 | 0 | 21 | 0/1024 |
| larger_dictionary | mixed_adaptive | 422/512 | 0 | 90 | 0/1024 |
| larger_dictionary | partitioned_fixed | 511/512 | 0 | 1 | 0/1024 |
| larger_dictionary | projected_adaptive | 512/512 | 0 | 0 | 0/1024 |
| larger_dictionary | projected_fixed | 512/512 | 0 | 0 | 0/1024 |
| larger_dictionary | v01_fixed | 492/512 | 0 | 20 | 6/1024 |
| load_only | mixed_adaptive | 484/512 | 0 | 28 | 0/1024 |
| load_only | partitioned_fixed | 512/512 | 0 | 0 | 0/1024 |
| load_only | projected_adaptive | 512/512 | 0 | 0 | 0/1024 |
| load_only | projected_fixed | 512/512 | 0 | 0 | 0/1024 |
| load_only | v01_fixed | 508/512 | 0 | 4 | 4/1024 |
| masked_noise | mixed_adaptive | 476/512 | 0 | 36 | 0/1024 |
| masked_noise | partitioned_fixed | 511/512 | 0 | 1 | 0/1024 |
| masked_noise | projected_adaptive | 512/512 | 0 | 0 | 1/1024 |
| masked_noise | projected_fixed | 512/512 | 0 | 0 | 0/1024 |
| masked_noise | v01_fixed | 503/512 | 0 | 9 | 3/1024 |
| no_observation | mixed_adaptive | 0/512 | 0 | 512 | 0/1024 |
| no_observation | partitioned_fixed | 0/512 | 0 | 512 | 0/1024 |
| no_observation | projected_adaptive | 0/512 | 0 | 512 | 0/1024 |
| no_observation | projected_fixed | 0/512 | 0 | 512 | 0/1024 |
| no_observation | v01_fixed | 0/512 | 0 | 512 | 0/1024 |
| nominal | mixed_adaptive | 512/512 | 0 | 0 | 0/1024 |
| nominal | partitioned_fixed | 512/512 | 0 | 0 | 0/1024 |
| nominal | projected_adaptive | 512/512 | 0 | 0 | 0/1024 |
| nominal | projected_fixed | 512/512 | 0 | 0 | 0/1024 |
| nominal | v01_fixed | 512/512 | 0 | 0 | 0/1024 |
| overload | mixed_adaptive | 0/512 | 0 | 512 | 0/1024 |
| overload | partitioned_fixed | 0/512 | 0 | 512 | 0/1024 |
| overload | projected_adaptive | 0/512 | 0 | 512 | 0/1024 |
| overload | projected_fixed | 0/512 | 0 | 512 | 0/1024 |
| overload | v01_fixed | 22/512 | 324 | 166 | 697/1024 |
| partial_only | mixed_adaptive | 476/512 | 0 | 36 | 0/1024 |
| partial_only | partitioned_fixed | 511/512 | 0 | 1 | 0/1024 |
| partial_only | projected_adaptive | 512/512 | 0 | 0 | 0/1024 |
| partial_only | projected_fixed | 512/512 | 0 | 0 | 0/1024 |
| partial_only | v01_fixed | 505/512 | 0 | 7 | 2/1024 |
| small_dimension | mixed_adaptive | 35/512 | 0 | 477 | 2/1024 |
| small_dimension | partitioned_fixed | 312/512 | 0 | 200 | 60/1024 |
| small_dimension | projected_adaptive | 0/512 | 0 | 512 | 0/1024 |
| small_dimension | projected_fixed | 0/512 | 0 | 512 | 0/1024 |
| small_dimension | v01_fixed | 237/512 | 23 | 252 | 181/1024 |
| unknown_nuisance | mixed_adaptive | 470/512 | 0 | 42 | 0/1024 |
| unknown_nuisance | partitioned_fixed | 511/512 | 0 | 1 | 0/1024 |
| unknown_nuisance | projected_adaptive | 511/512 | 0 | 1 | 0/1024 |
| unknown_nuisance | projected_fixed | 511/512 | 0 | 1 | 0/1024 |
| unknown_nuisance | v01_fixed | 503/512 | 0 | 9 | 3/1024 |
| unreferenced_quarter_turn | mixed_adaptive | 0/512 | 0 | 512 | 0/1024 |
| unreferenced_quarter_turn | partitioned_fixed | 0/512 | 0 | 512 | 0/1024 |
| unreferenced_quarter_turn | projected_adaptive | 0/512 | 0 | 512 | 0/1024 |
| unreferenced_quarter_turn | projected_fixed | 0/512 | 0 | 512 | 0/1024 |
| unreferenced_quarter_turn | v01_fixed | 0/512 | 0 | 512 | 0/1024 |

## 採用方式のseed別変動

同じ試行内の照会は独立ではありません。以下は観測された範囲で、母集団の信頼区間や無誤り保証ではありません。

| 条件 | 符号seed別回復率 min–max | 符号seed別誤受理率 min–max | チャネルseed別回復率 min–max |
|---|---:|---:|---:|
| higher_load | 0.00%–0.00% | 0.00%–0.00% | 0.00%–0.00% |
| jitter_only | 100.00%–100.00% | 0.00%–0.00% | 100.00%–100.00% |
| larger_dictionary | 100.00%–100.00% | 0.00%–0.00% | 100.00%–100.00% |
| load_only | 100.00%–100.00% | 0.00%–0.00% | 100.00%–100.00% |
| masked_noise | 100.00%–100.00% | 0.00%–1.56% | 100.00%–100.00% |
| no_observation | 0.00%–0.00% | 0.00%–0.00% | 0.00%–0.00% |
| nominal | 100.00%–100.00% | 0.00%–0.00% | 100.00%–100.00% |
| overload | 0.00%–0.00% | 0.00%–0.00% | 0.00%–0.00% |
| partial_only | 100.00%–100.00% | 0.00%–0.00% | 100.00%–100.00% |
| small_dimension | 0.00%–0.00% | 0.00%–0.00% | 0.00%–0.00% |
| unknown_nuisance | 96.88%–100.00% | 0.00%–0.00% | 99.22%–100.00% |
| unreferenced_quarter_turn | 0.00%–0.00% | 0.00%–0.00% | 0.00%–0.00% |

## 状態を含む別評価

7-slot回復: 448/448、誤回復0、保留0。出来事単位の全7-slot一致: 64/64。状態・述語の欠落真値負例誤受理: 0/320。
主語・目的語だけの高い回復率をRelation全体の完全回復と混同しないための別集計です。訂正target_clauseは別の連携テストで確認します。

## パイロット位相同期

2048成分中128をパイロットへ割当て（6.25%）、残り1920がデータ。25%観測時はデータ観測数がさらに減ります。全フレーム送信エネルギーは57344。
| 方式 | 回復 | 誤回復 | 保留 | 負例誤受理 |
|---|---:|---:|---:|---:|
| aligned_same_pilot_budget_reference | 512/512 | 0 | 0 | 0/1024 |
| oracle_true_phase_reference | 512/512 | 0 | 0 | 0/1024 |
| pilot_estimated | 512/512 | 0 | 0 | 0/1024 |
| sync_disabled | 0/512 | 0 | 512 | 0/1024 |

位相推定成功: 64/64。絶対位相誤差平均 0.02208158024092907 rad、最大 0.047407088159493904 rad。
oracleは真の回転角を使う評価用参照のみ。実際の推定経路には渡していません。aligned参照は同じパイロット予算で回転なしの別チャネル参照です。
位相角はチャネルseedに対応する4種類（開発は2種類）で、全角度・周波数ずれ・時刻ずれを網羅した試験ではありません。

## 受入判定

- nominal_all_recovered: PASS
- nominal_no_false_accepts: PASS
- masked_recovery_at_least_95pct: PASS
- masked_false_accept_at_most_2pct: PASS
- no_observation_always_abstains: PASS
- equal_exact_transmit_energy: PASS
- pilot_recovery_at_least_95pct: PASS
- pilot_false_accept_at_most_2pct: PASS
- all_pilot_trials_aligned: PASS
- pilot_max_phase_error_at_most_0p1rad: PASS
- no_state_inference_promotion: PASS

## 限界

判定alphaはガウス近似に基づく工学的設定で、回復スコアは確率ではありません。カタログ外の干渉、低次元、過負荷では保留・誤りが起こり得ます。
公開カタログは真のslot割当てではありませんが追加のモデル知識です。無事前知識での改善と主張しません。
SS拡散・逆拡散、遅延・周波数同期、物理時間軸、独立意味評価は未実装。推論は引き続き無効です。
