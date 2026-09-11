# R1観察契約 v0.1

## 許可範囲

R1が行うのは取り込み、構造検証、保存、表示、人の意見の追記です。`inference_enabled=false`、各観察の `eligible_for_inference=false` を常に維持します。`applied=true` はC2内の処理履歴であり、R1で事実採用した意味ではありません。

| 区分 | R1の扱い |
|---|---|
| rule_checked / positive / asserted | C2が規則確認した観察。事実として採用しない |
| negative | 否定を維持し、肯定事実へ変換しない |
| hypothetical | 仮定を維持し、成立した事実としない |
| corrective / retracted / provisional | 状態と訂正先を残し、根拠のactive/superseded_byを保持 |
| quarantined / unchecked | 隔離・未確認として表示。採用可能な事実にしない |
| Relationが0件 | 文書単位のレビュー対象。関係の不存在を意味しない |
| レビューの賛同 | 記録者の意見。原観察の変更や推論許可ではない |

## 入力境界

C2 v0.4のenvelope schema_version=1のみ受け付けます。RelationFrameは同梱 `vendor/PLM-C2-v0.4/RELATION_SCHEMA.json` に従います。R1の型・ID・span・参照検証は `plm_r1/contract.py` が実行仕様です。汎用JSON Schemaエンジンではなく、同梱Schemaで使用するキーワードだけを実装しています。

envelopeの必須トップレベルキー: schema_version, producer_version, document_id, boundary, observations, mentions, entities, clauses, evidence。未知のトップレベル/フレームキー、推論許可、重複ID、根拠/個体/節の参照切れ、span原文不一致、訂正循環は拒否します。付随データの未知フィールドは原文脈保存のため維持します。

解析全体を伴わないenvelopeの `rule_checked` や元グラフは、送信者がそう報告したという扱いです。構造的に正しく意味だけ間違った文字列は取り込める場合があります。`transport_validated` を意味評価済みと読んではいけません。完全解析の取り込みもC2規則の再生であり、独立意味評価ではありません。

## ID・重複・履歴

- content document_id: C2仕様の入力文字列配列のSHA256。
- observation_id: `document_id:frame_id`。現版はproducerをC2 v0.4に固定。
- qualified entity: `document_id:entity_id`。別内容の同じENT番号を結合しない。
- external source: `(source_id, revision)` とdocument_idとの対応。内容コピーは別出典リンクになるが観察件数は増えない。
- envelope_hash/context_hash: キー順を正規化したJSONのSHA256。受信バイト列そのものの保存ではない。

同じ内容IDで異なるenvelopeは拒否。同じ出典・改訂に異なる内容も拒否。完全解析文脈の後付けは可、差し替えは不可。観察と出典リンクの取り込みはSQLiteトランザクションにまとめ、不成立の場合は途中登録しません。

レビューはevent_id単位で冪等。同じevent_idで違う意見は拒否し、新event_idで追記します。DBトリガーでもレビューの更新/削除と観察本体の更新/削除を拒否します。ただしDBを直接改造できる権限者への改ざん耐性・監査署名を保証するものではありません。

## エラー分類

`subject_role / object_role / predicate / polarity / modality / voice / coreference / revision_target / unknown_predicate / missing_relation / spurious_relation / span / classification / source_quality / other`

未抽出Relationの指摘は文書IDをレビュー対象にします。関係がある観察のIDだけに限定すると見落としが台帳から消えるためです。単なる未抽出を自動でmissing_relationと断定せず、原文に戻って人が判断します。

## 将来の開放

独立した意味評価、利用側の受入基準、エラー処理、新リリースの明示承認が必要です。今回は数値スコアやレビューに連動する自動開放処理を一切設けません。
