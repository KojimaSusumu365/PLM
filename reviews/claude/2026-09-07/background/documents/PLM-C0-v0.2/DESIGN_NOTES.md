# PLM-C0 v0.2 Design Notes

## 固定した問い

**Concept三値多数決は、正票だけの語彙投票よりも否定・曖昧性・階層的限定を一貫して扱えるか？**

v0.2 でも LLM API、Transformer、埋め込み、Vector DB は使用しません。

## Score

\[
Score(C)=D(C)+0.8P(C)+B(C)-1.2N(C)-G(C)
\]

- `D`: direct support
- `P`: child からの propagated support
- `B`: context boost
- `N`: contradiction
- `G`: generality penalty

## 評価設計

データセットを実装コードから分離し、同一ケースを `PLMC0Engine` と `PositiveLexicalBaseline` に入力します。集計値だけでなくケース別結果を保存し、失敗を追跡できる形にします。

Top-5 と MRR では、正解Conceptがランキング表に載っているだけではヒットにしません。直接支持、伝播支持、文脈支持、または正の最終スコアが必要です。これは全Conceptを常時採点する実装でゼロ点候補が見かけ上ヒットするのを防ぎます。

`UNRESOLVED` は通常Conceptとは別の棄却結果として評価します。期待値が `UNRESOLVED` の場合、実際に棄却したときだけ rank 1 とします。

## Minority evidence

`minority_evidence` は、複数の曖昧・一般的な表現に対して、少数の文脈手掛かりまたは具体的手掛かりが含まれるケースです。v0.2 の retention は、その正解Conceptを Top-5 の観測済み候補として失わなかった割合です。最終選択の正否は Top-1 で別に測ります。

## Efficiency proxy

現実装は辞書とConceptを全走査します。そのため以下を明示的に記録します。

- target domain の採点候補数
- 入力ごとの照合パターン数
- 抽出された evidence item 数

これは実時間ベンチマークではなく、辞書拡張時の計算量を追跡するための決定論的 proxy です。

## 既知の制約

- データセットは36件の手作業ケースで、学習・検証分割はない
- 同じ辞書から評価文を設計しており、外部妥当性はない
- 否定検出は局所ルールで、長距離依存や複雑な日本語否定は扱わない
- minority retention の Top-5 は小さなConcept集合では飽和しやすい
- 全候補・全パターン走査なので大規模化にはインデックスが必要

## 次段階候補

- train/dev/test を分けた外部データセット
- macro-F1 と confidence calibration
- hard-negative と長距離否定
- 候補生成インデックスによる全走査の削減
- PLM-C1 の明示的な残差除去演算
