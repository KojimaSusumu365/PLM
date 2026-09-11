# PLM-S1 v0.2 数値評価

分割: development。内部人工ベースバンド評価であり、独立意味評価ではありません。

## 回復比較

全方式8480チップ・総エネルギー57344、パイロット256チップを内数とします。旧版との比較は配置と受信器の両方が違います。配置だけを戻す比較は後述の同期評価です。

| 条件 | 方式 | 正例回復 | 誤回復 | 保留 | 負例誤受理 | 同期誤受理 |
|---|---|---:|---:|---:|---:|---:|
| alias_negative | v01_ss | 0/32 | 0 | 32 | 0/64 | 4 |
| alias_negative | v02_direct | 32/32 | 0 | 0 | 0/64 | 0 |
| alias_negative | v02_oracle | 32/32 | 0 | 0 | 0/64 | 0 |
| alias_negative | v02_repeat | 32/32 | 0 | 0 | 0/64 | 0 |
| alias_negative | v02_ss | 32/32 | 0 | 0 | 0/64 | 0 |
| alias_partial | v01_ss | 0/32 | 0 | 32 | 0/64 | 4 |
| alias_partial | v02_direct | 32/32 | 0 | 0 | 0/64 | 0 |
| alias_partial | v02_oracle | 32/32 | 0 | 0 | 0/64 | 0 |
| alias_partial | v02_repeat | 32/32 | 0 | 0 | 0/64 | 0 |
| alias_partial | v02_ss | 32/32 | 0 | 0 | 0/64 | 0 |
| alias_positive | v01_ss | 0/32 | 0 | 32 | 0/64 | 4 |
| alias_positive | v02_direct | 32/32 | 0 | 0 | 0/64 | 0 |
| alias_positive | v02_oracle | 32/32 | 0 | 0 | 0/64 | 0 |
| alias_positive | v02_repeat | 32/32 | 0 | 0 | 0/64 | 0 |
| alias_positive | v02_ss | 32/32 | 0 | 0 | 0/64 | 0 |
| legacy_combined | v01_ss | 32/32 | 0 | 0 | 0/64 | 0 |
| legacy_combined | v02_direct | 32/32 | 0 | 0 | 0/64 | 0 |
| legacy_combined | v02_oracle | 32/32 | 0 | 0 | 0/64 | 0 |
| legacy_combined | v02_repeat | 32/32 | 0 | 0 | 0/64 | 0 |
| legacy_combined | v02_ss | 32/32 | 0 | 0 | 0/64 | 0 |
| legacy_partial | v01_ss | 32/32 | 0 | 0 | 0/64 | 0 |
| legacy_partial | v02_direct | 32/32 | 0 | 0 | 0/64 | 0 |
| legacy_partial | v02_oracle | 32/32 | 0 | 0 | 0/64 | 0 |
| legacy_partial | v02_repeat | 32/32 | 0 | 0 | 0/64 | 0 |
| legacy_partial | v02_ss | 32/32 | 0 | 0 | 0/64 | 0 |
| no_observation | v01_ss | 0/32 | 0 | 32 | 0/64 | 0 |
| no_observation | v02_direct | 0/32 | 0 | 32 | 0/64 | 0 |
| no_observation | v02_oracle | 0/32 | 0 | 32 | 0/64 | 0 |
| no_observation | v02_repeat | 0/32 | 0 | 32 | 0/64 | 0 |
| no_observation | v02_ss | 0/32 | 0 | 32 | 0/64 | 0 |
| nominal | v01_ss | 32/32 | 0 | 0 | 0/64 | 0 |
| nominal | v02_direct | 32/32 | 0 | 0 | 0/64 | 0 |
| nominal | v02_oracle | 32/32 | 0 | 0 | 0/64 | 0 |
| nominal | v02_repeat | 32/32 | 0 | 0 | 0/64 | 0 |
| nominal | v02_ss | 32/32 | 0 | 0 | 0/64 | 0 |
| tone_interference | v01_ss | 0/32 | 0 | 32 | 0/64 | 2 |
| tone_interference | v02_direct | 32/32 | 0 | 0 | 0/64 | 0 |
| tone_interference | v02_oracle | 32/32 | 0 | 0 | 0/64 | 0 |
| tone_interference | v02_repeat | 32/32 | 0 | 0 | 0/64 | 0 |
| tone_interference | v02_ss | 32/32 | 0 | 0 | 0/64 | 0 |
| wide_cfo | v01_ss | 0/32 | 0 | 32 | 0/64 | 2 |
| wide_cfo | v02_direct | 32/32 | 0 | 0 | 0/64 | 0 |
| wide_cfo | v02_oracle | 32/32 | 0 | 0 | 0/64 | 0 |
| wide_cfo | v02_repeat | 32/32 | 0 | 0 | 0/64 | 0 |
| wide_cfo | v02_ss | 32/32 | 0 | 0 | 0/64 | 0 |
| wide_partial | v01_ss | 0/32 | 0 | 32 | 0/64 | 2 |
| wide_partial | v02_direct | 32/32 | 0 | 0 | 0/64 | 0 |
| wide_partial | v02_oracle | 32/32 | 0 | 0 | 0/64 | 0 |
| wide_partial | v02_repeat | 32/32 | 0 | 0 | 0/64 | 0 |
| wide_partial | v02_ss | 32/32 | 0 | 0 | 0/64 | 0 |

## 新受信器の数値精度

NMSEは回復成分だけで計算し、無出力は欠測です。25%チップ観測と25%P1成分観測は異なります。

| 条件 | 同期受理 | 最大CFO誤差 Hz | 最大位相誤差 rad | 成分カバー率 | 成分NMSE |
|---|---:|---:|---:|---:|---:|
| alias_negative | 4/4 | 0.004409555288461542 | 0.015314671828175114 | 100.00% | 0.002556146895479054 |
| alias_partial | 4/4 | 0.007583383413461542 | 0.033714866708111885 | 68.60% | 0.008340392127355033 |
| alias_positive | 4/4 | 0.002182241586538458 | 0.013246577680882693 | 100.00% | 0.002545358571095356 |
| legacy_combined | 4/4 | 0.004651397014991454 | 0.019199909009972344 | 100.00% | 0.0025667068958399597 |
| legacy_partial | 4/4 | 0.010266631389991454 | 0.04244854483576085 | 68.60% | 0.008353645628306244 |
| no_observation | 0/4 | None | None | 0.00% | None |
| nominal | 4/4 | 0.0 | 0.0 | 100.00% | 1.363223573602951e-32 |
| tone_interference | 4/4 | 0.020172076765502256 | 0.06506531967622076 | 100.00% | 0.004043639869018196 |
| wide_cfo | 4/4 | 0.0029892458030231772 | 0.013172438147502184 | 100.00% | 0.002556291051362152 |
| wide_partial | 4/4 | 0.006889526783667943 | 0.03281079223866205 | 68.60% | 0.008452377954572826 |

## 周波数掃引・負例・配置の比較

同期誤受理は、受理したのに真の整数遅延と違う、CFO誤差>0.025 Hz、または位相誤差>0.15 radのいずれか。真値は評価者専用で受信器には渡しません。

| 条件 | チップ観測率 | 方式 | 同期受理/試行 | 同期誤受理 |
|---|---:|---|---:|---:|
| all_pilots_missing | 25% | v01_edge2 | 0/4 | 0 |
| all_pilots_missing | 25% | v02_distributed | 0/4 | 0 |
| all_pilots_missing | 25% | v02_edge2_ablation | 0/4 | 0 |
| all_pilots_missing | 100% | v01_edge2 | 0/4 | 0 |
| all_pilots_missing | 100% | v02_distributed | 0/4 | 0 |
| all_pilots_missing | 100% | v02_edge2_ablation | 0/4 | 0 |
| conflicting_phases | 25% | v01_edge2 | 0/4 | 0 |
| conflicting_phases | 25% | v02_distributed | 0/4 | 0 |
| conflicting_phases | 25% | v02_edge2_ablation | 0/4 | 0 |
| conflicting_phases | 100% | v01_edge2 | 0/4 | 0 |
| conflicting_phases | 100% | v02_distributed | 0/4 | 0 |
| conflicting_phases | 100% | v02_edge2_ablation | 0/4 | 0 |
| equal_frequency_mixture | 25% | v01_edge2 | 4/4 | 0 |
| equal_frequency_mixture | 25% | v02_distributed | 0/4 | 0 |
| equal_frequency_mixture | 25% | v02_edge2_ablation | 0/4 | 0 |
| equal_frequency_mixture | 100% | v01_edge2 | 4/4 | 0 |
| equal_frequency_mixture | 100% | v02_distributed | 0/4 | 0 |
| equal_frequency_mixture | 100% | v02_edge2_ablation | 0/4 | 0 |
| frequency_-0.2 | 25% | v01_edge2 | 2/4 | 0 |
| frequency_-0.2 | 25% | v02_distributed | 4/4 | 0 |
| frequency_-0.2 | 25% | v02_edge2_ablation | 0/4 | 0 |
| frequency_-0.2 | 100% | v01_edge2 | 1/4 | 0 |
| frequency_-0.2 | 100% | v02_distributed | 4/4 | 0 |
| frequency_-0.2 | 100% | v02_edge2_ablation | 0/4 | 0 |
| frequency_-0.4807692307692308 | 25% | v01_edge2 | 0/4 | 0 |
| frequency_-0.4807692307692308 | 25% | v02_distributed | 4/4 | 0 |
| frequency_-0.4807692307692308 | 25% | v02_edge2_ablation | 0/4 | 0 |
| frequency_-0.4807692307692308 | 100% | v01_edge2 | 0/4 | 0 |
| frequency_-0.4807692307692308 | 100% | v02_distributed | 4/4 | 0 |
| frequency_-0.4807692307692308 | 100% | v02_edge2_ablation | 0/4 | 0 |
| frequency_-0.9615384615384616 | 25% | v01_edge2 | 4/4 | 4 |
| frequency_-0.9615384615384616 | 25% | v02_distributed | 4/4 | 0 |
| frequency_-0.9615384615384616 | 25% | v02_edge2_ablation | 0/4 | 0 |
| frequency_-0.9615384615384616 | 100% | v01_edge2 | 4/4 | 4 |
| frequency_-0.9615384615384616 | 100% | v02_distributed | 4/4 | 0 |
| frequency_-0.9615384615384616 | 100% | v02_edge2_ablation | 0/4 | 0 |
| frequency_-1.0615384615384615 | 25% | v01_edge2 | 4/4 | 4 |
| frequency_-1.0615384615384615 | 25% | v02_distributed | 4/4 | 0 |
| frequency_-1.0615384615384615 | 25% | v02_edge2_ablation | 0/4 | 0 |
| frequency_-1.0615384615384615 | 100% | v01_edge2 | 4/4 | 4 |
| frequency_-1.0615384615384615 | 100% | v02_distributed | 4/4 | 0 |
| frequency_-1.0615384615384615 | 100% | v02_edge2_ablation | 0/4 | 0 |
| frequency_-1.9 | 25% | v01_edge2 | 4/4 | 4 |
| frequency_-1.9 | 25% | v02_distributed | 4/4 | 0 |
| frequency_-1.9 | 25% | v02_edge2_ablation | 0/4 | 0 |
| frequency_-1.9 | 100% | v01_edge2 | 4/4 | 4 |
| frequency_-1.9 | 100% | v02_distributed | 4/4 | 0 |
| frequency_-1.9 | 100% | v02_edge2_ablation | 0/4 | 0 |
| frequency_-1.99 | 25% | v01_edge2 | 4/4 | 4 |
| frequency_-1.99 | 25% | v02_distributed | 4/4 | 0 |
| frequency_-1.99 | 25% | v02_edge2_ablation | 0/4 | 0 |
| frequency_-1.99 | 100% | v01_edge2 | 4/4 | 4 |
| frequency_-1.99 | 100% | v02_distributed | 4/4 | 0 |
| frequency_-1.99 | 100% | v02_edge2_ablation | 0/4 | 0 |
| frequency_-16 | 25% | v01_edge2 | 0/4 | 0 |
| frequency_-16 | 25% | v02_distributed | 0/4 | 0 |
| frequency_-16 | 25% | v02_edge2_ablation | 0/4 | 0 |
| frequency_-16 | 100% | v01_edge2 | 0/4 | 0 |
| frequency_-16 | 100% | v02_distributed | 0/4 | 0 |
| frequency_-16 | 100% | v02_edge2_ablation | 0/4 | 0 |
| frequency_-2 | 25% | v01_edge2 | 4/4 | 4 |
| frequency_-2 | 25% | v02_distributed | 2/4 | 0 |
| frequency_-2 | 25% | v02_edge2_ablation | 0/4 | 0 |
| frequency_-2 | 100% | v01_edge2 | 4/4 | 4 |
| frequency_-2 | 100% | v02_distributed | 2/4 | 0 |
| frequency_-2 | 100% | v02_edge2_ablation | 0/4 | 0 |
| frequency_-2.05 | 25% | v01_edge2 | 4/4 | 4 |
| frequency_-2.05 | 25% | v02_distributed | 0/4 | 0 |
| frequency_-2.05 | 25% | v02_edge2_ablation | 0/4 | 0 |
| frequency_-2.05 | 100% | v01_edge2 | 4/4 | 4 |
| frequency_-2.05 | 100% | v02_distributed | 0/4 | 0 |
| frequency_-2.05 | 100% | v02_edge2_ablation | 0/4 | 0 |
| frequency_-3 | 25% | v01_edge2 | 4/4 | 4 |
| frequency_-3 | 25% | v02_distributed | 0/4 | 0 |
| frequency_-3 | 25% | v02_edge2_ablation | 0/4 | 0 |
| frequency_-3 | 100% | v01_edge2 | 4/4 | 4 |
| frequency_-3 | 100% | v02_distributed | 0/4 | 0 |
| frequency_-3 | 100% | v02_edge2_ablation | 0/4 | 0 |
| frequency_-4.5 | 25% | v01_edge2 | 0/4 | 0 |
| frequency_-4.5 | 25% | v02_distributed | 0/4 | 0 |
| frequency_-4.5 | 25% | v02_edge2_ablation | 0/4 | 0 |
| frequency_-4.5 | 100% | v01_edge2 | 0/4 | 0 |
| frequency_-4.5 | 100% | v02_distributed | 0/4 | 0 |
| frequency_-4.5 | 100% | v02_edge2_ablation | 0/4 | 0 |
| frequency_-8 | 25% | v01_edge2 | 0/4 | 0 |
| frequency_-8 | 25% | v02_distributed | 0/4 | 0 |
| frequency_-8 | 25% | v02_edge2_ablation | 0/4 | 0 |
| frequency_-8 | 100% | v01_edge2 | 0/4 | 0 |
| frequency_-8 | 100% | v02_distributed | 0/4 | 0 |
| frequency_-8 | 100% | v02_edge2_ablation | 0/4 | 0 |
| frequency_0 | 25% | v01_edge2 | 4/4 | 0 |
| frequency_0 | 25% | v02_distributed | 4/4 | 0 |
| frequency_0 | 25% | v02_edge2_ablation | 0/4 | 0 |
| frequency_0 | 100% | v01_edge2 | 4/4 | 0 |
| frequency_0 | 100% | v02_distributed | 4/4 | 0 |
| frequency_0 | 100% | v02_edge2_ablation | 0/4 | 0 |
| frequency_0.2 | 25% | v01_edge2 | 0/4 | 0 |
| frequency_0.2 | 25% | v02_distributed | 4/4 | 0 |
| frequency_0.2 | 25% | v02_edge2_ablation | 0/4 | 0 |
| frequency_0.2 | 100% | v01_edge2 | 3/4 | 0 |
| frequency_0.2 | 100% | v02_distributed | 4/4 | 0 |
| frequency_0.2 | 100% | v02_edge2_ablation | 0/4 | 0 |
| frequency_0.4807692307692308 | 25% | v01_edge2 | 0/4 | 0 |
| frequency_0.4807692307692308 | 25% | v02_distributed | 4/4 | 0 |
| frequency_0.4807692307692308 | 25% | v02_edge2_ablation | 0/4 | 0 |
| frequency_0.4807692307692308 | 100% | v01_edge2 | 0/4 | 0 |
| frequency_0.4807692307692308 | 100% | v02_distributed | 4/4 | 0 |
| frequency_0.4807692307692308 | 100% | v02_edge2_ablation | 0/4 | 0 |
| frequency_0.9615384615384616 | 25% | v01_edge2 | 4/4 | 4 |
| frequency_0.9615384615384616 | 25% | v02_distributed | 4/4 | 0 |
| frequency_0.9615384615384616 | 25% | v02_edge2_ablation | 0/4 | 0 |
| frequency_0.9615384615384616 | 100% | v01_edge2 | 4/4 | 4 |
| frequency_0.9615384615384616 | 100% | v02_distributed | 4/4 | 0 |
| frequency_0.9615384615384616 | 100% | v02_edge2_ablation | 0/4 | 0 |
| frequency_1.0615384615384615 | 25% | v01_edge2 | 4/4 | 4 |
| frequency_1.0615384615384615 | 25% | v02_distributed | 4/4 | 0 |
| frequency_1.0615384615384615 | 25% | v02_edge2_ablation | 0/4 | 0 |
| frequency_1.0615384615384615 | 100% | v01_edge2 | 4/4 | 4 |
| frequency_1.0615384615384615 | 100% | v02_distributed | 4/4 | 0 |
| frequency_1.0615384615384615 | 100% | v02_edge2_ablation | 0/4 | 0 |
| frequency_1.9 | 25% | v01_edge2 | 4/4 | 4 |
| frequency_1.9 | 25% | v02_distributed | 4/4 | 0 |
| frequency_1.9 | 25% | v02_edge2_ablation | 0/4 | 0 |
| frequency_1.9 | 100% | v01_edge2 | 4/4 | 4 |
| frequency_1.9 | 100% | v02_distributed | 4/4 | 0 |
| frequency_1.9 | 100% | v02_edge2_ablation | 0/4 | 0 |
| frequency_1.99 | 25% | v01_edge2 | 4/4 | 4 |
| frequency_1.99 | 25% | v02_distributed | 4/4 | 0 |
| frequency_1.99 | 25% | v02_edge2_ablation | 0/4 | 0 |
| frequency_1.99 | 100% | v01_edge2 | 4/4 | 4 |
| frequency_1.99 | 100% | v02_distributed | 4/4 | 0 |
| frequency_1.99 | 100% | v02_edge2_ablation | 0/4 | 0 |
| frequency_16 | 25% | v01_edge2 | 0/4 | 0 |
| frequency_16 | 25% | v02_distributed | 0/4 | 0 |
| frequency_16 | 25% | v02_edge2_ablation | 0/4 | 0 |
| frequency_16 | 100% | v01_edge2 | 0/4 | 0 |
| frequency_16 | 100% | v02_distributed | 0/4 | 0 |
| frequency_16 | 100% | v02_edge2_ablation | 0/4 | 0 |
| frequency_2 | 25% | v01_edge2 | 4/4 | 4 |
| frequency_2 | 25% | v02_distributed | 3/4 | 0 |
| frequency_2 | 25% | v02_edge2_ablation | 0/4 | 0 |
| frequency_2 | 100% | v01_edge2 | 4/4 | 4 |
| frequency_2 | 100% | v02_distributed | 1/4 | 0 |
| frequency_2 | 100% | v02_edge2_ablation | 0/4 | 0 |
| frequency_2.05 | 25% | v01_edge2 | 4/4 | 4 |
| frequency_2.05 | 25% | v02_distributed | 0/4 | 0 |
| frequency_2.05 | 25% | v02_edge2_ablation | 0/4 | 0 |
| frequency_2.05 | 100% | v01_edge2 | 4/4 | 4 |
| frequency_2.05 | 100% | v02_distributed | 0/4 | 0 |
| frequency_2.05 | 100% | v02_edge2_ablation | 0/4 | 0 |
| frequency_3 | 25% | v01_edge2 | 4/4 | 4 |
| frequency_3 | 25% | v02_distributed | 0/4 | 0 |
| frequency_3 | 25% | v02_edge2_ablation | 0/4 | 0 |
| frequency_3 | 100% | v01_edge2 | 4/4 | 4 |
| frequency_3 | 100% | v02_distributed | 0/4 | 0 |
| frequency_3 | 100% | v02_edge2_ablation | 0/4 | 0 |
| frequency_4.5 | 25% | v01_edge2 | 0/4 | 0 |
| frequency_4.5 | 25% | v02_distributed | 0/4 | 0 |
| frequency_4.5 | 25% | v02_edge2_ablation | 0/4 | 0 |
| frequency_4.5 | 100% | v01_edge2 | 0/4 | 0 |
| frequency_4.5 | 100% | v02_distributed | 0/4 | 0 |
| frequency_4.5 | 100% | v02_edge2_ablation | 0/4 | 0 |
| frequency_8 | 25% | v01_edge2 | 0/4 | 0 |
| frequency_8 | 25% | v02_distributed | 0/4 | 0 |
| frequency_8 | 25% | v02_edge2_ablation | 0/4 | 0 |
| frequency_8 | 100% | v01_edge2 | 0/4 | 0 |
| frequency_8 | 100% | v02_distributed | 0/4 | 0 |
| frequency_8 | 100% | v02_edge2_ablation | 0/4 | 0 |
| frequency_8000.1 | 25% | v01_edge2 | 4/4 | 4 |
| frequency_8000.1 | 25% | v02_distributed | 4/4 | 4 |
| frequency_8000.1 | 25% | v02_edge2_ablation | 0/4 | 0 |
| frequency_8000.1 | 100% | v01_edge2 | 4/4 | 4 |
| frequency_8000.1 | 100% | v02_distributed | 4/4 | 4 |
| frequency_8000.1 | 100% | v02_edge2_ablation | 0/4 | 0 |
| no_observation | 25% | v01_edge2 | 0/4 | 0 |
| no_observation | 25% | v02_distributed | 0/4 | 0 |
| no_observation | 25% | v02_edge2_ablation | 0/4 | 0 |
| no_observation | 100% | v01_edge2 | 0/4 | 0 |
| no_observation | 100% | v02_distributed | 0/4 | 0 |
| no_observation | 100% | v02_edge2_ablation | 0/4 | 0 |
| noise_only | 25% | v01_edge2 | 0/4 | 0 |
| noise_only | 25% | v02_distributed | 0/4 | 0 |
| noise_only | 25% | v02_edge2_ablation | 0/4 | 0 |
| noise_only | 100% | v01_edge2 | 0/4 | 0 |
| noise_only | 100% | v02_distributed | 0/4 | 0 |
| noise_only | 100% | v02_edge2_ablation | 0/4 | 0 |
| observed_zero | 25% | v01_edge2 | 0/4 | 0 |
| observed_zero | 25% | v02_distributed | 0/4 | 0 |
| observed_zero | 25% | v02_edge2_ablation | 0/4 | 0 |
| observed_zero | 100% | v01_edge2 | 0/4 | 0 |
| observed_zero | 100% | v02_distributed | 0/4 | 0 |
| observed_zero | 100% | v02_edge2_ablation | 0/4 | 0 |
| one_block_missing | 25% | v01_edge2 | 0/4 | 0 |
| one_block_missing | 25% | v02_distributed | 0/4 | 0 |
| one_block_missing | 25% | v02_edge2_ablation | 0/4 | 0 |
| one_block_missing | 100% | v01_edge2 | 0/4 | 0 |
| one_block_missing | 100% | v02_distributed | 0/4 | 0 |
| one_block_missing | 100% | v02_edge2_ablation | 0/4 | 0 |
| outside_delay | 25% | v01_edge2 | 0/4 | 0 |
| outside_delay | 25% | v02_distributed | 0/4 | 0 |
| outside_delay | 25% | v02_edge2_ablation | 0/4 | 0 |
| outside_delay | 100% | v01_edge2 | 0/4 | 0 |
| outside_delay | 100% | v02_distributed | 0/4 | 0 |
| outside_delay | 100% | v02_edge2_ablation | 0/4 | 0 |
| pilot_only | 25% | v01_edge2 | 4/4 | 0 |
| pilot_only | 25% | v02_distributed | 4/4 | 0 |
| pilot_only | 25% | v02_edge2_ablation | 0/4 | 0 |
| pilot_only | 100% | v01_edge2 | 4/4 | 0 |
| pilot_only | 100% | v02_distributed | 4/4 | 0 |
| pilot_only | 100% | v02_edge2_ablation | 0/4 | 0 |
| wrong_pilots | 25% | v01_edge2 | 0/4 | 0 |
| wrong_pilots | 25% | v02_distributed | 0/4 | 0 |
| wrong_pilots | 25% | v02_edge2_ablation | 0/4 | 0 |
| wrong_pilots | 100% | v01_edge2 | 0/4 | 0 |
| wrong_pilots | 100% | v02_distributed | 0/4 | 0 |
| wrong_pilots | 100% | v02_edge2_ablation | 0/4 | 0 |

## 状態の別評価

7-slot完全回復 8/8。{'positive_queries': 56, 'correct': 56, 'wrong': 0, 'abstained': 0, 'recovery_rate': 1.0, 'accepted_accuracy': 1.0, 'negative_queries': 40, 'false_accepts': 0, 'false_accept_rate': 0.0}。target_clauseとR1の5種類の連携は単体・連携テストで検証。

## 受入

事前定義チェック 46/46。

- nominal_recovery: PASS
- nominal_false_accept: PASS
- nominal_acquisition: PASS
- nominal_wrong_lock: PASS
- legacy_combined_recovery: PASS
- legacy_combined_false_accept: PASS
- legacy_combined_acquisition: PASS
- legacy_combined_wrong_lock: PASS
- legacy_partial_recovery: PASS
- legacy_partial_false_accept: PASS
- legacy_partial_acquisition: PASS
- legacy_partial_wrong_lock: PASS
- alias_positive_recovery: PASS
- alias_positive_false_accept: PASS
- alias_positive_acquisition: PASS
- alias_positive_wrong_lock: PASS
- alias_negative_recovery: PASS
- alias_negative_false_accept: PASS
- alias_negative_acquisition: PASS
- alias_negative_wrong_lock: PASS
- alias_partial_recovery: PASS
- alias_partial_false_accept: PASS
- alias_partial_acquisition: PASS
- alias_partial_wrong_lock: PASS
- wide_cfo_recovery: PASS
- wide_cfo_false_accept: PASS
- wide_cfo_acquisition: PASS
- wide_cfo_wrong_lock: PASS
- wide_partial_recovery: PASS
- wide_partial_false_accept: PASS
- wide_partial_acquisition: PASS
- wide_partial_wrong_lock: PASS
- sweep_1.0_interior_acquisition: PASS
- sweep_1.0_interior_boundary_wrong_lock: PASS
- sweep_1.0_guard_rejection: PASS
- sweep_1.0_negative_rejection: PASS
- sweep_0.25_interior_acquisition: PASS
- sweep_0.25_interior_boundary_wrong_lock: PASS
- sweep_0.25_guard_rejection: PASS
- sweep_0.25_negative_rejection: PASS
- equal_energy_chip_budget: PASS
- no_observation_abstain: PASS
- inference_disabled: PASS
- state_recovery: PASS
- state_no_false_accept: PASS
- state_inference_disabled: PASS

## 限界

受入周波数は±2 Hz、探索は±4 Hz。境界±2 Hz付近の雑音による保留を別記します。全周波数・全入力で誤同期しない保証はありません。
Fs+0.1 Hzは離散サンプリングにより0.1 Hzと識別できません。有効パイロットだけでも同期を受理でき、これは送信者・ペイロードの認証ではありません。上表に失敗側も保存します。
照会やseed交差内には相関があり、照会数を独立標本数とした信頼区間ではありません。白色雑音下のSS固有の無料利得、RF実機、独立意味評価、推論開放は主張しません。
