# PLM-S1 v0.1 数値評価

分割: evaluation

人工ベースバンドのチップ列での最小実証です。独立意味評価・実無線機・通信規格への適合試験ではありません。

全方式で8480チップ、総送信エネルギー57344、同じP1 2048成分・4出来事・28結合・96候補。パイロット256チップ、ガード32チップを内数とします。
direct_pilotは各成分を1つのチップに載せ残りを空ける直接参照です。repeat_pilotは同じ成分を4回反復する非拡散対照で、同一時間・消失分散の比較としてより強い対照です。
ss_pilotが実際の受信経路。ss_sync_disabledは補正なし、ss_oracleは評価者だけが真の遅延・位相・周波数を使う参照です。

## 主語・目的語の回復

| 条件 | 方式 | 回復 | 誤回復 | 保留 | 負例誤受理 |
|---|---|---:|---:|---:|---:|
| aliased_cfo | direct_pilot | 0/256 | 0 | 256 | 0/512 |
| aliased_cfo | repeat_pilot | 0/256 | 0 | 256 | 0/512 |
| aliased_cfo | ss_oracle | 256/256 | 0 | 0 | 0/512 |
| aliased_cfo | ss_pilot | 0/256 | 0 | 256 | 0/512 |
| aliased_cfo | ss_sync_disabled | 0/256 | 0 | 256 | 0/512 |
| combined | direct_pilot | 256/256 | 0 | 0 | 0/512 |
| combined | repeat_pilot | 256/256 | 0 | 0 | 0/512 |
| combined | ss_oracle | 256/256 | 0 | 0 | 0/512 |
| combined | ss_pilot | 256/256 | 0 | 0 | 0/512 |
| combined | ss_sync_disabled | 0/256 | 0 | 256 | 0/512 |
| integer_delay | direct_pilot | 256/256 | 0 | 0 | 0/512 |
| integer_delay | repeat_pilot | 256/256 | 0 | 0 | 0/512 |
| integer_delay | ss_oracle | 256/256 | 0 | 0 | 0/512 |
| integer_delay | ss_pilot | 256/256 | 0 | 0 | 0/512 |
| integer_delay | ss_sync_disabled | 0/256 | 0 | 256 | 0/512 |
| missing_pilots | direct_pilot | 0/256 | 0 | 256 | 0/512 |
| missing_pilots | repeat_pilot | 0/256 | 0 | 256 | 0/512 |
| missing_pilots | ss_oracle | 256/256 | 0 | 0 | 0/512 |
| missing_pilots | ss_pilot | 0/256 | 0 | 256 | 0/512 |
| missing_pilots | ss_sync_disabled | 0/256 | 0 | 256 | 0/512 |
| no_observation | direct_pilot | 0/256 | 0 | 256 | 0/512 |
| no_observation | repeat_pilot | 0/256 | 0 | 256 | 0/512 |
| no_observation | ss_oracle | 0/256 | 0 | 256 | 0/512 |
| no_observation | ss_pilot | 0/256 | 0 | 256 | 0/512 |
| no_observation | ss_sync_disabled | 0/256 | 0 | 256 | 0/512 |
| nominal | direct_pilot | 256/256 | 0 | 0 | 0/512 |
| nominal | repeat_pilot | 256/256 | 0 | 0 | 0/512 |
| nominal | ss_oracle | 256/256 | 0 | 0 | 0/512 |
| nominal | ss_pilot | 256/256 | 0 | 0 | 0/512 |
| nominal | ss_sync_disabled | 256/256 | 0 | 0 | 0/512 |
| out_of_delay | direct_pilot | 0/256 | 0 | 256 | 0/512 |
| out_of_delay | repeat_pilot | 0/256 | 0 | 256 | 0/512 |
| out_of_delay | ss_oracle | 256/256 | 0 | 0 | 0/512 |
| out_of_delay | ss_pilot | 0/256 | 0 | 256 | 0/512 |
| out_of_delay | ss_sync_disabled | 0/256 | 0 | 256 | 0/512 |
| partial_combined | direct_pilot | 256/256 | 0 | 0 | 0/512 |
| partial_combined | repeat_pilot | 256/256 | 0 | 0 | 0/512 |
| partial_combined | ss_oracle | 256/256 | 0 | 0 | 0/512 |
| partial_combined | ss_pilot | 256/256 | 0 | 0 | 0/512 |
| partial_combined | ss_sync_disabled | 0/256 | 0 | 256 | 1/512 |
| phase_only | direct_pilot | 256/256 | 0 | 0 | 0/512 |
| phase_only | repeat_pilot | 256/256 | 0 | 0 | 0/512 |
| phase_only | ss_oracle | 256/256 | 0 | 0 | 0/512 |
| phase_only | ss_pilot | 256/256 | 0 | 0 | 0/512 |
| phase_only | ss_sync_disabled | 64/256 | 0 | 192 | 0/512 |
| small_cfo | direct_pilot | 256/256 | 0 | 0 | 0/512 |
| small_cfo | repeat_pilot | 256/256 | 0 | 0 | 0/512 |
| small_cfo | ss_oracle | 256/256 | 0 | 0 | 0/512 |
| small_cfo | ss_pilot | 256/256 | 0 | 0 | 0/512 |
| small_cfo | ss_sync_disabled | 256/256 | 0 | 0 | 0/512 |
| sparse_observation | direct_pilot | 0/256 | 0 | 256 | 0/512 |
| sparse_observation | repeat_pilot | 0/256 | 0 | 256 | 0/512 |
| sparse_observation | ss_oracle | 0/256 | 0 | 256 | 0/512 |
| sparse_observation | ss_pilot | 0/256 | 0 | 256 | 0/512 |
| sparse_observation | ss_sync_disabled | 0/256 | 0 | 256 | 0/512 |
| tone_interference | direct_pilot | 256/256 | 0 | 0 | 0/512 |
| tone_interference | repeat_pilot | 256/256 | 0 | 0 | 0/512 |
| tone_interference | ss_oracle | 256/256 | 0 | 0 | 0/512 |
| tone_interference | ss_pilot | 256/256 | 0 | 0 | 0/512 |
| tone_interference | ss_sync_disabled | 0/256 | 0 | 256 | 0/512 |

## 実受信器の同期と成分回復

NMSEは回復できた成分だけで計算します。出力なしは0誤差とはせず欠測。比較時は成分カバー率も確認してください。

| 条件 | 同期受理/試行 | 正しい整数遅延 | 最大周波数誤差 Hz | 最大位相誤差 rad | 平均成分カバー率 | 平均NMSE |
|---|---:|---:|---:|---:|---:|---:|
| aliased_cfo | 32/32 | 32 | 0.9647654254384616 | 0.08101311495852315 | 100.00% | 2.044063715813894 |
| combined | 32/32 | 32 | 0.004357810519199895 | 0.020410601041476854 | 100.00% | 0.0025875036528370306 |
| integer_delay | 32/32 | 32 | 0.0033821809 | 0.0174923795 | 100.00% | 0.0023518572699538767 |
| missing_pilots | 0/32 | 0 | None | None | 0.00% | None |
| no_observation | 0/32 | 0 | None | None | 0.00% | None |
| nominal | 32/32 | 32 | 0.0 | 0.0 | 100.00% | 1.0434363923585371e-32 |
| out_of_delay | 0/32 | 0 | None | None | 0.00% | None |
| partial_combined | 32/32 | 32 | 0.006495271380800111 | 0.03370457638998303 | 68.99% | 0.008217383272075433 |
| phase_only | 32/32 | 32 | 0.003259091 | 0.011603669358523083 | 100.00% | 0.0023316707101638905 |
| small_cfo | 32/32 | 32 | 0.002729966361228936 | 0.0118678738 | 100.00% | 0.002333478295897061 |
| sparse_observation | 0/32 | 0 | None | None | 0.00% | None |
| tone_interference | 32/32 | 32 | 0.02452686924731895 | 0.08300659968998314 | 100.00% | 0.0040128752962561385 |

## 同一予算での干渉比較

| 条件 | 方式 | 平均成分カバー率 | 平均NMSE |
|---|---|---:|---:|
| combined | direct_pilot | 100.00% | 0.003216887720403595 |
| combined | repeat_pilot | 100.00% | 0.002577872572864377 |
| combined | ss_pilot | 100.00% | 0.0025875036528370306 |
| partial_combined | direct_pilot | 24.28% | 0.0032934932291789317 |
| partial_combined | repeat_pilot | 68.99% | 0.008213556113965667 |
| partial_combined | ss_pilot | 68.99% | 0.008217383272075433 |
| tone_interference | direct_pilot | 100.00% | 0.08727368640617332 |
| tone_interference | repeat_pilot | 100.00% | 0.3356746687650786 |
| tone_interference | ss_pilot | 100.00% | 0.0040128752962561385 |

拡散により同一エネルギーでAWGN性能が自動的に上がるとは主張しません。toneは受信側DC干渉の限定例であり、任意の狭帯域・広帯域干渉への保証ではありません。

## seed別の観測範囲

同一試行内や交差したseed間には相関があります。以下は信頼区間ではなく、実測グループの最小・最大です。

| 条件 | 符号seed別回復率 | チャネルseed別回復率 |
|---|---:|---:|
| aliased_cfo | 0.00%–0.00% | 0.00%–0.00% |
| combined | 100.00%–100.00% | 100.00%–100.00% |
| integer_delay | 100.00%–100.00% | 100.00%–100.00% |
| missing_pilots | 0.00%–0.00% | 0.00%–0.00% |
| no_observation | 0.00%–0.00% | 0.00%–0.00% |
| nominal | 100.00%–100.00% | 100.00%–100.00% |
| out_of_delay | 0.00%–0.00% | 0.00%–0.00% |
| partial_combined | 100.00%–100.00% | 100.00%–100.00% |
| phase_only | 100.00%–100.00% | 100.00%–100.00% |
| small_cfo | 100.00%–100.00% | 100.00%–100.00% |
| sparse_observation | 0.00%–0.00% | 0.00%–0.00% |
| tone_interference | 100.00%–100.00% | 100.00%–100.00% |

## 状態を含む別評価

7-slot全体の完全回復: 32/32。slot集計: {'positive_queries': 224, 'correct': 224, 'wrong': 0, 'abstained': 0, 'recovery_rate': 1.0, 'accepted_accuracy': 1.0, 'negative_queries': 160, 'false_accepts': 0, 'false_accept_rate': 0.0}。訂正target_clauseは別の連携テストで確認します。

## 受入

事前定義した受入チェック: 40/40。

- nominal_recovery: PASS
- nominal_false_accept: PASS
- nominal_pilot_alignment: PASS
- nominal_integer_delay: PASS
- nominal_cfo_error: PASS
- nominal_phase_error: PASS
- phase_only_recovery: PASS
- phase_only_false_accept: PASS
- phase_only_pilot_alignment: PASS
- phase_only_integer_delay: PASS
- phase_only_cfo_error: PASS
- phase_only_phase_error: PASS
- integer_delay_recovery: PASS
- integer_delay_false_accept: PASS
- integer_delay_pilot_alignment: PASS
- integer_delay_integer_delay: PASS
- integer_delay_cfo_error: PASS
- integer_delay_phase_error: PASS
- small_cfo_recovery: PASS
- small_cfo_false_accept: PASS
- small_cfo_pilot_alignment: PASS
- small_cfo_integer_delay: PASS
- small_cfo_cfo_error: PASS
- small_cfo_phase_error: PASS
- combined_recovery: PASS
- combined_false_accept: PASS
- combined_pilot_alignment: PASS
- combined_integer_delay: PASS
- combined_cfo_error: PASS
- combined_phase_error: PASS
- partial_combined_recovery: PASS
- partial_combined_false_accept: PASS
- partial_combined_pilot_alignment: PASS
- partial_combined_integer_delay: PASS
- partial_combined_cfo_error: PASS
- partial_combined_phase_error: PASS
- equal_energy_and_chip_budget: PASS
- missing_pilots_and_zero_observation_abstain: PASS
- inference_stays_disabled: PASS
- state_inference_stays_disabled: PASS

## 限界

位相・周波数・遅延の真値はtrial_auditsの評価者用記録にだけ保持し、実際の受信器へ渡しません。公開された小さな周波数範囲の事前条件は使います。
二つの離れたパイロットによる周波数推定には折り返し曖昧性があります。範囲外では同期受理が正しい同期を保証しません。aliased_cfoを隠さず報告します。
分数チップ遅延、サンプル時計ずれ、時間変動周波数、マルチパス、FEC、RF回路、パイロット認証は未実装。SHA256は認証ではありません。
P1の公開候補カタログと近似的な判定規則はそのままです。相関・復調成功は意味の真偽ではなく、推論許可は常にfalseです。
