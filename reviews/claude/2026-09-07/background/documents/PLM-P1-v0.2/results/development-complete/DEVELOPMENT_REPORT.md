# PLM-P1 v0.2 数値評価

分割: development

人工構造の数値回復試験です。独立意味評価ではありません。旧評価seedは使わず、符号seedとチャネルseedを分離して交差させています。
全方式で同じ次元数・結合情報・送信エネルギー・候補辞書・公開カタログを使用。送信正規化の単一gainは全方式へ公開。
v01_fixedは旧復号器を同じ等エネルギー条件で再評価した比較です。v0.1当時の64問の結果と直接同じ母集団ではありません。

## 主語・目的語の比較

| 条件 | 方式 | 回復 | 誤回復 | 保留 | 負例誤受理 |
|---|---|---:|---:|---:|---:|
| higher_load | mixed_adaptive | 3/64 | 0 | 61 | 1/128 |
| higher_load | partitioned_fixed | 34/64 | 3 | 27 | 23/128 |
| higher_load | projected_adaptive | 0/64 | 0 | 64 | 0/128 |
| higher_load | projected_fixed | 0/64 | 0 | 64 | 0/128 |
| higher_load | v01_fixed | 18/64 | 11 | 35 | 40/128 |
| jitter_only | mixed_adaptive | 64/64 | 0 | 0 | 0/128 |
| jitter_only | partitioned_fixed | 64/64 | 0 | 0 | 0/128 |
| jitter_only | projected_adaptive | 64/64 | 0 | 0 | 0/128 |
| jitter_only | projected_fixed | 62/64 | 0 | 2 | 0/128 |
| jitter_only | v01_fixed | 62/64 | 0 | 2 | 0/128 |
| larger_dictionary | mixed_adaptive | 50/64 | 0 | 14 | 0/128 |
| larger_dictionary | partitioned_fixed | 64/64 | 0 | 0 | 0/128 |
| larger_dictionary | projected_adaptive | 64/64 | 0 | 0 | 0/128 |
| larger_dictionary | projected_fixed | 64/64 | 0 | 0 | 0/128 |
| larger_dictionary | v01_fixed | 63/64 | 0 | 1 | 1/128 |
| load_only | mixed_adaptive | 54/64 | 0 | 10 | 0/128 |
| load_only | partitioned_fixed | 62/64 | 0 | 2 | 0/128 |
| load_only | projected_adaptive | 64/64 | 0 | 0 | 0/128 |
| load_only | projected_fixed | 64/64 | 0 | 0 | 0/128 |
| load_only | v01_fixed | 58/64 | 0 | 6 | 0/128 |
| masked_noise | mixed_adaptive | 58/64 | 0 | 6 | 0/128 |
| masked_noise | partitioned_fixed | 64/64 | 0 | 0 | 0/128 |
| masked_noise | projected_adaptive | 64/64 | 0 | 0 | 0/128 |
| masked_noise | projected_fixed | 64/64 | 0 | 0 | 0/128 |
| masked_noise | v01_fixed | 64/64 | 0 | 0 | 1/128 |
| no_observation | mixed_adaptive | 0/64 | 0 | 64 | 0/128 |
| no_observation | partitioned_fixed | 0/64 | 0 | 64 | 0/128 |
| no_observation | projected_adaptive | 0/64 | 0 | 64 | 0/128 |
| no_observation | projected_fixed | 0/64 | 0 | 64 | 0/128 |
| no_observation | v01_fixed | 0/64 | 0 | 64 | 0/128 |
| nominal | mixed_adaptive | 64/64 | 0 | 0 | 0/128 |
| nominal | partitioned_fixed | 64/64 | 0 | 0 | 0/128 |
| nominal | projected_adaptive | 64/64 | 0 | 0 | 0/128 |
| nominal | projected_fixed | 64/64 | 0 | 0 | 0/128 |
| nominal | v01_fixed | 64/64 | 0 | 0 | 0/128 |
| overload | mixed_adaptive | 0/64 | 0 | 64 | 0/128 |
| overload | partitioned_fixed | 0/64 | 0 | 64 | 0/128 |
| overload | projected_adaptive | 0/64 | 0 | 64 | 0/128 |
| overload | projected_fixed | 0/64 | 0 | 64 | 0/128 |
| overload | v01_fixed | 0/64 | 47 | 17 | 87/128 |
| partial_only | mixed_adaptive | 58/64 | 0 | 6 | 0/128 |
| partial_only | partitioned_fixed | 64/64 | 0 | 0 | 0/128 |
| partial_only | projected_adaptive | 64/64 | 0 | 0 | 0/128 |
| partial_only | projected_fixed | 64/64 | 0 | 0 | 0/128 |
| partial_only | v01_fixed | 63/64 | 0 | 1 | 1/128 |
| small_dimension | mixed_adaptive | 6/64 | 0 | 58 | 0/128 |
| small_dimension | partitioned_fixed | 0/64 | 0 | 64 | 0/128 |
| small_dimension | projected_adaptive | 0/64 | 0 | 64 | 0/128 |
| small_dimension | projected_fixed | 0/64 | 0 | 64 | 0/128 |
| small_dimension | v01_fixed | 30/64 | 2 | 32 | 24/128 |
| unknown_nuisance | mixed_adaptive | 61/64 | 0 | 3 | 0/128 |
| unknown_nuisance | partitioned_fixed | 64/64 | 0 | 0 | 0/128 |
| unknown_nuisance | projected_adaptive | 64/64 | 0 | 0 | 0/128 |
| unknown_nuisance | projected_fixed | 64/64 | 0 | 0 | 0/128 |
| unknown_nuisance | v01_fixed | 63/64 | 0 | 1 | 0/128 |
| unreferenced_quarter_turn | mixed_adaptive | 0/64 | 0 | 64 | 0/128 |
| unreferenced_quarter_turn | partitioned_fixed | 0/64 | 0 | 64 | 0/128 |
| unreferenced_quarter_turn | projected_adaptive | 0/64 | 0 | 64 | 0/128 |
| unreferenced_quarter_turn | projected_fixed | 0/64 | 0 | 64 | 0/128 |
| unreferenced_quarter_turn | v01_fixed | 0/64 | 0 | 64 | 0/128 |

## 採用方式のseed別変動

同じ試行内の照会は独立ではありません。以下は観測された範囲で、母集団の信頼区間や無誤り保証ではありません。

| 条件 | 符号seed別回復率 min–max | 符号seed別誤受理率 min–max | チャネルseed別回復率 min–max |
|---|---:|---:|---:|
| higher_load | 0.00%–0.00% | 0.00%–0.00% | 0.00%–0.00% |
| jitter_only | 100.00%–100.00% | 0.00%–0.00% | 100.00%–100.00% |
| larger_dictionary | 100.00%–100.00% | 0.00%–0.00% | 100.00%–100.00% |
| load_only | 100.00%–100.00% | 0.00%–0.00% | 100.00%–100.00% |
| masked_noise | 100.00%–100.00% | 0.00%–0.00% | 100.00%–100.00% |
| no_observation | 0.00%–0.00% | 0.00%–0.00% | 0.00%–0.00% |
| nominal | 100.00%–100.00% | 0.00%–0.00% | 100.00%–100.00% |
| overload | 0.00%–0.00% | 0.00%–0.00% | 0.00%–0.00% |
| partial_only | 100.00%–100.00% | 0.00%–0.00% | 100.00%–100.00% |
| small_dimension | 0.00%–0.00% | 0.00%–0.00% | 0.00%–0.00% |
| unknown_nuisance | 100.00%–100.00% | 0.00%–0.00% | 100.00%–100.00% |
| unreferenced_quarter_turn | 0.00%–0.00% | 0.00%–0.00% | 0.00%–0.00% |

## 状態を含む別評価

7-slot回復: 112/112、誤回復0、保留0。出来事単位の全7-slot一致: 16/16。状態・述語の欠落真値負例誤受理: 0/80。
主語・目的語だけの高い回復率をRelation全体の完全回復と混同しないための別集計です。訂正target_clauseは別の連携テストで確認します。

## パイロット位相同期

2048成分中128をパイロットへ割当て（6.25%）、残り1920がデータ。25%観測時はデータ観測数がさらに減ります。全フレーム送信エネルギーは57344。
| 方式 | 回復 | 誤回復 | 保留 | 負例誤受理 |
|---|---:|---:|---:|---:|
| aligned_same_pilot_budget_reference | 64/64 | 0 | 0 | 0/128 |
| oracle_true_phase_reference | 64/64 | 0 | 0 | 0/128 |
| pilot_estimated | 64/64 | 0 | 0 | 0/128 |
| sync_disabled | 0/64 | 0 | 64 | 0/128 |

位相推定成功: 8/8。絶対位相誤差平均 0.01782535296809218 rad、最大 0.03393699338009348 rad。
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
