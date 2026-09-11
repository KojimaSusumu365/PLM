# PLM-C0 v0.1 — Concept三値多数決・最小実証機

PLM（Phase Language Machine）構想の最初の実装です。文章生成は行わず、**異なる表現からConcept候補を抽出し、\(-1,0,+1\) の三値証拠を重み付き多数決し、Concept階層を使って適切な粒度まで限定できるか**だけを検証します。

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

## 三値

- `+1`: Conceptを支持
- `0`: 無関係・投票なし（v0.1では暗黙の0）
- `-1`: Conceptに矛盾

## 「引き算」

通常のベクトル減算 `X1-X2` ではありません。v0.1では、

1. **Contradiction subtraction** — 明示否定や兄弟Concept支持を負票として減算
2. **Hierarchical narrowing** — 上位Conceptを維持しながら、直接証拠のある下位Conceptへ限定

として最小実装しています。

## 実行

```bash
python demo.py
python -m unittest discover -s tests -v
```

外部Pythonパッケージは不要です。

## v0.1の範囲外

Concept自動獲得、WordNet大規模化、Concept HV、SS/PN系列、実Phase、Role/Relation、文法生成、学習器、埋め込み、神経回路シミュレーション、省電力ASIC等はまだ入れていません。これらを最初から混ぜず、Concept三値多数決の寄与を独立に測ります。

## 次段階

- **v0.2**: データセット評価、Top-1/Top-5/MRR、minority evidence、baseline比較
- **PLM-C1**: 残差除去の明示演算
- **PLM-R1**: Agent/Patient/Relation
- **PLM-P1**: 高次元準直交コード、部分相関、Phase
