# PLM-C2 v0.4 → R1 観察境界

本リリースはRelationの生成・監査・観察出力までを提供します。R1の推論エンジン、学習、外部システムへの登録は行いません。

## 状態の意味

| 項目 | 意味 |
|---|---|
| schema_valid | 必須項目・型・参照先・原文spanが整合する |
| graph_valid | ID・端点・必要ノード型が整合する |
| rule_checked | この版の限定意味規則と元の根拠が整合する |
| quarantined | 未対応、引用、役割不一致などがあり、人による確認が必要 |
| observation_ready | Schema/Graphが妥当で、rule_checkedのフレームが1件以上ある |
| inference_ready | 常にfalse |
| eligible_for_inference | 常にfalse（各観察）または空配列（境界） |

`ready_for_r1_experiment`は既存キーとの互換名ですが、v0.4ではobservation_readyと同じです。これを本番稼働や自動推論の許可と解釈してはいけません。

否定された関係・仮定された関係は、意味が確認できれば観察対象になれます。ただし肯定された事実としては扱えず、positive_rule_checked_frame_idsには含めません。quarantinedも表示用には出力しますが、採用可能な事実ではありません。

## 出力API

`export_r1_observations(result)`は現在のresultを再検証し、独立したコピーを返します。Schemaやグラフに破損があればValueErrorです。意味上の不一致はquarantinedと理由を付けて返します。`mode="infer"`などは拒否します。

document_idは入力の内容ハッシュ、observation_idはそのハッシュとframe_idの組み合わせです。同一内容の再処理を識別できます。別文書に同一内容が存在する場合に出典の独立性を主張するIDではありません。外部システムは自分の文書IDを別に保持してください。

entity_idとmention_idは1つの解析結果内のIDです。別document_idの同じIDを同じ個体として結合してはいけません。個体のConcept候補と、関係から推定されたConceptも区別してください。

## 次の開放条件

関係種類・態・否定・訂正・照応ごとの独立した正解評価、消費側の統合テスト、採用基準と誤り時の処理を備えた新しいリリースが必要です。今回はそのために観察可能なデータと監査結果を提供する段階です。
