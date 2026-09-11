# PLM-C0 v0.3 Design Notes

## 固定した問い

**三値、文脈、階層の各機構は、正票だけの語彙投票に対して測定可能な寄与を持つか。また、局所ルールの限界はどこに現れるか。**

## Engine changes

`EngineConfig` で negation、context、hierarchy、sibling contradiction、overlap suppression、ASCII boundary を独立に無効化できます。full model と1機能ずつ除いたモデルを同一test splitで比較します。

ASCII語彙は前後が英数字・underscoreでない場合だけ一致させます。複数パターンが同じ文字範囲に重なる場合は、最長の表層一致だけを採用します。例えば `river bank` は `river` と曖昧語 `bank` を同時加点しません。

## Benchmark construction

72個の意味テンプレートに4種類の決定論的ラッパーを適用します。

- dev: 元の表層 72件
- test: 未使用のラッパー3種、216件
- 通常機能群: 60テンプレート
- stress群: 12テンプレート

意味内容はdev/testで共有するため、testを「外部」または「完全なblind test」とは呼びません。統計区間はラッパー単位ではなく72個の `template_group` をcluster bootstrapします。

## Added metrics

- Macro precision / recall / F1（`UNRESOLVED` を1クラスとして含む）
- coverage と、棄却しなかった例だけの selective accuracy
- confidence threshold別 coverage–accuracy
- Expected Calibration Error（10 bins）
- Brier score
- paired cluster bootstrap によるbaseline差の95%区間

## Ablation result summary

full Top-1 は `0.8333` でした。主要な除去結果は次のとおりです。

- no negation: `0.7361`
- no context: `0.7778`
- no hierarchy: `0.7222`
- no sibling contradiction: `0.8194`
- no ASCII boundaries: `0.8056`
- no overlap suppression: `0.8333`

このデータでは hierarchy、negation、context、ASCII boundary がTop-1に寄与しました。overlap suppressionは精度を変えませんでしたが、証拠の二重計上を減らします。

## Observed failure classes

stress test の12意味テンプレートはすべて失敗しました。

1. 後続の訂正を以前の記述より優先できない
2. 長距離・挿入句を含む否定を局所窓で認識できない
3. 日本語述語否定をConcept否定として処理できない
4. 同じ文の無関係な節からcontext triggerが漏れる
5. 別入力のcontextが曖昧語へ無条件に合流する
6. 否定されたcontext triggerの極性を扱えない
7. 複数候補を含む談話で単一Consensusを強制する

## Next decision

次に精度を伸ばす場合は、単純な語彙追加よりも evidence に `clause_id`, `scope`, `source_order`, `assertion_status` を持たせる必要があります。これはConcept投票の範囲を越え始めるため、PLM-C1の残差・訂正演算、またはPLM-R1のRelation導入として設計するのが自然です。
