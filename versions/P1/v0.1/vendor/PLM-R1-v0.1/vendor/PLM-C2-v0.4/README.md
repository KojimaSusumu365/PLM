# PLM-C2 v0.4 — Relation意味監査とR1境界

PLM-C2の分類結果に加え、内部のRelationの意味・根拠・個体同定を検証する実証実装です。Python 3.10以上、標準ライブラリのみで動作します。

最終分類が正しい場合でも内部Relationが誤っていることがあるため、分類精度とRelationの正解照合を別々に計測します。R1への出力は観察用に限定し、推論採用を自動で有効にしません。

## 今回の結果

| 検証 | 結果 |
|---|---|
| 全テスト | 186/186合格、skipなし |
| 既存8評価セット | 618/618正解（接頭辞違いなどの従属例を含む） |
| 開発診断 | 分類23/23、検証済みRelation15/15正解・抽出漏れなし |
| 固定後holdout | 分類29/32正解。凍結v0.3は22/32 |
| holdoutの検証済みRelation | 21/21正解、正解23件中2件が抽出漏れ（F1 0.9545） |
| 意味保全・否定反転の変形対 | 9/9合格 |
| holdout ECE | 校正前0.1781 → 校正後0.0782 |
| 受入判定 | 16/16合格、初回固定後評価の再現を確認 |

全Relation候補が正しいわけではありません。holdoutの全36候補中15件は意味監査で隔離され、残る21件が正解でした。高確信度の分類誤りも1件残っています。詳細は`AUDIT_FINDINGS.md`を参照してください。

## 主な変更

- `bank support structure`の名詞を金融行為として生成しない。
- 能動文と受動文を同じ行為者・対象へ正規化し、元の態と原文の位置も保持する。
- 同じDOGやCATでも複数の個体を識別し、単数代名詞が曖昧なら解決済みにしない。
- 日本語の「犬、いや、猫」は猫の訂正先を実際の犬の根拠へ結ぶ。
- 意味監査の結果を`rule_checked` / `quarantined`として記録する。rule_checkedは限定規則との整合を意味し、真実性や一般化性能の保証ではない。
- 分類・保留の確信度を専用データで校正する。個体照応の不確実性は別の状態として保持する。

## 使い方

```python
from plm_c2 import PLMC2Engine, export_r1_observations

result = PLMC2Engine().analyze(
    "Grants for a river restoration were awarded by the bank."
)
print(result["selections"]["place"]["selected"])
print(result["relation_frames"])
print(result["semantic_audit"])

observations = export_r1_observations(result)
assert observations["boundary"]["mode"] == "observe_only"
assert observations["boundary"]["inference_enabled"] is False
```

```bash
python -B verify_release.py
python -B evaluate.py
python -B demo.py --out DEMO_OUTPUT.txt --observations-out R1_OBSERVATIONS_EXAMPLE.json
```

`evaluate.py`は評価レポートとJSONを生成します。`verify_release.py`はテスト結果を生成します。実行時の作業ディレクトリはこのREADMEのあるディレクトリにしてください。

配布版はデータ・校正モデル・実装を凍結済みです。`freeze_runtime.py`は既存の凍結記録を上書きしません。新しい研究版を作る場合は別のディレクトリ・版で変更を行い、評価境界を記録してください。

## 評価資料

- `EVALUATION_REPORT.md`: 分類、Relation正解照合、保留評価の失敗、校正、受入判定
- `EVALUATION_RESULTS.json`: 全ケース、確信度閾値ごとの採用率・精度、信頼区間、機能除去診断
- `FIRST_EVALUATION.json`: 実装固定後の初回holdout実行結果
- `FREEZE_MANIFEST.json`: 全Pythonコード・Schema・データ・校正モデルのハッシュ
- `TEST_REPORT.md`, `TEST_OUTPUT.txt`: 旧版とv0.4のテスト結果
- `RELATION_SCHEMA.json`: Relation Frame schema v2
- `R1_BOUNDARY.md`: R1境界・互換性・消費側の制約
- `AUDIT_FINDINGS.md`: 成果の解釈、残る失敗、次の評価課題
- `R1_OBSERVATIONS_EXAMPLE.json`: 受動文から生成した観察用出力

## 評価の位置づけ

開発23件、校正30件、holdout32件、変形対9件を使用します。holdoutは初回実行を実装固定後まで保留した評価です。全セットは同一開発過程で作成され、外部コーパスでも独立した作成者の評価でもありません。単語・構文の共有もあります。

Relation評価の正解は、生成コードと別に記述した主体・述語・対象・態・否定・訂正先・照応先を照合します。全候補と、意味監査で確認できた部分集合の両方の精度・再現率を示します。未対応の候補を隔離することによる再現率低下も隠さず計測します。

## 互換性と限界

`plm_c2`はv0.4です。`plm_c2_v03`以下に旧実装を保存しています。旧テストは旧実装を、新テストはv0.4を検証します。既存データに対するv0.4の回帰評価も別途実行します。

Relation契約はv2、Claim Graphはv3です。旧`ENTITY`（談話の対象範囲）は`TARGET_SCOPE`へ改名し、`ENTITY_INSTANCE`と`MENTION`を追加しました。`subject`は行為者、`object_text`は対象句を表すため、受動文の文法上の主語とは異なります。

対象語彙・文法は限定的です。一般構文解析、長距離照応、複雑な省略、一般の固有名詞統合、引用内容の真偽、未知述語の推論は扱い切れません。R1本番開放の判定は今回の対象外で、観察結果を独立評価する段階に進める成果です。
