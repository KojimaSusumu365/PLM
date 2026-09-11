# v0.1既知失敗の診断（回帰試験）

v0.1の評価seedは既知データとして扱います。v0.2の未知データ性能には数えません。

| seed | 照会 | 元の結果 | 真値順位 | v0.2回帰結果 |
|---:|---|---|---:|---|
| 7101 | event-003 / subject | abstained / score_below_threshold | 1 | recovered（照合 一致） |
| 7102 | event-002 / object | abstained / ambiguous_candidates | 1 | recovered（照合 一致） |
| 7102 | absent-event-002 / object | false_accept / numerical_recovery_only | None | abstain（照合 一致） |
| 7103 | event-000 / object | abstained / score_below_threshold | 1 | recovered（照合 一致） |
| 7107 | event-003 / object | abstained / score_below_threshold | 1 | recovered（照合 一致） |

各照会の真値と最大競合候補について、観測マスク上のスコアを、元の役割別干渉とチャネル摂動へ分解しました。詳細は同名JSON。
保留時のtop_scoreを無条件に真値のスコアと解釈せず、96候補全部の順位を再計算しています。
状態情報を削除せず、その公開候補が張る部分空間を観測成分上で除きます。真の割当てや干渉の正解寄与は評価者の診断にだけ使い、復号器には渡していません。
