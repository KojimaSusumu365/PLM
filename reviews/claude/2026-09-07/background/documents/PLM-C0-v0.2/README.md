# PLM-C0 v0.2 — Concept三値多数決・評価版

PLM（Phase Language Machine）構想の Concept 層だけを切り出した、外部依存なしの実証実装です。v0.1 の三値証拠・重み付き多数決・階層的限定を維持し、v0.2 では固定データセットと再現可能な評価系を追加しました。

## v0.2 の追加点

- 36ケースの日本語・英語混在データセット
- Top-1 accuracy / Top-5 recall / MRR
- `UNRESOLVED` precision / recall
- minority evidence retention
- contradiction rejection
- 候補Concept数・照合パターン数の計測
- 正票だけを数える lexical baseline との比較
- ケース別・タグ別の結果を JSON と Markdown に保存

## パイプライン

```text
Surface expressions
  ↓
Lexical / contextual evidence
  ↓
Ternary vote {-1, 0, +1}
  ↓
Weighted consensus
  ↓
Ancestor propagation / sibling contradiction
  ↓
Hierarchy-aware narrowing
  ↓
Concept or UNRESOLVED
```

## 実行

標準ライブラリだけを使います。

```bash
python demo.py
python evaluate.py
python -m unittest discover -s tests -v
```

独自データセットも指定できます。

```bash
python evaluate.py --dataset path/to/cases.json --json-out result.json --report-out report.md
```

## データセット形式

各ケースは `id`, `inputs`, `domain`, `expected`, `tags` を持ちます。否定ケースでは、選択してはいけない Concept を `forbidden` に列挙できます。`inputs` は文字列または文字列配列です。

```json
{
  "id": "dog_not_cat_ja",
  "inputs": "犬ではなく猫だった",
  "domain": "entity",
  "expected": "CAT",
  "forbidden": ["DOG"],
  "tags": ["negation", "contradiction", "ja"]
}
```

## 指標の定義

- Top-1 は最終選択を採点し、正解が `UNRESOLVED` のケースも含めます。
- Top-5 / MRR は、正解Conceptに正の観測信号がある場合だけ順位として数えます。ゼロ点の未観測候補はヒットにしません。
- `UNRESOLVED` は、期待値も `UNRESOLVED` で実際に棄却したときだけ正解です。
- minority evidence retention は `minority_evidence` タグのケースで正解Conceptを Top-5 に保持できた割合です。
- contradiction rejection は、`forbidden` Concept を最終選択しなかった割合です。
- candidates evaluated は対象domainで実際に採点したConcept数です。

## ベースライン

`PositiveLexicalBaseline` は同じ辞書を使いますが、否定、文脈、階層、兄弟矛盾を使いません。同点は恣意的に決めず `UNRESOLVED` にします。これにより、三値処理と階層処理の寄与を比較できます。

## スコープ

この評価は同梱の小規模・手作業データセットに対する機能検証です。PLM全体の有効性、一般化性能、統計的有意性を主張するものではありません。Concept自動獲得、Role/Relation、実Phase、学習器、埋め込み、神経回路シミュレーションは引き続き範囲外です。
