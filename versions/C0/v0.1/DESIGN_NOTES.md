# PLM-C0 v0.1 Design Notes

## 固定した問い

**Concept多数決だけで、表層表現の違いを越えてConceptを選択できるか？**

v0.1ではLLM API、Transformer、埋め込み、Vector DBを使用しません。

## 暫定Score

\[
Score(C)=D(C)+0.8P(C)+B(C)-1.2N(C)-G(C)
\]

- `D`: direct support
- `P`: childからのpropagated support
- `B`: context boost
- `N`: contradiction
- `G`: generality penalty

## 重要な設計原則

- 上位Conceptが強すぎないように階層的限定を行う
- 明示否定は負票にする
- 兄弟Concept支持は弱い負票として扱う
- 証拠不足や曖昧性では `UNRESOLVED` を許す

## 主な失敗条件

- 上位Conceptばかり選ぶ
- 否定文で誤る
- generic文から具体Conceptを捏造する
- sibling contradictionが強すぎる
- 辞書拡大で全候補走査が重くなる

## v0.2で測るもの

Top-1 accuracy / Top-5 recall / MRR / UNRESOLVED precision / minority evidence retention / contradiction rejection / candidates evaluated
