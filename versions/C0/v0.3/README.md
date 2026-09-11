# PLM-C0 v0.3 — Concept三値多数決・頑健性評価版

PLM（Phase Language Machine）構想の Concept 層を、外部Pythonパッケージなしで検証する実装です。v0.3 は v0.2 の三値証拠、文脈投票、階層的限定を維持し、表層照合の堅牢化と分割評価、ablation、校正評価を追加します。

## v0.3 の追加点

- 英語語彙の単語境界判定（`dog` が `hotdog` に誤反応する問題を抑制）
- 最長一致優先による包含パターンの二重加点抑制
- 機能別 `EngineConfig` と ablation 評価
- 72意味テンプレート × 4表層ラッパー = 288ケース
- dev 72件 / test 216件の固定分割
- 訂正、長距離否定、文脈スコープを含むstress subset
- Macro precision / recall / F1
- coverage–accuracy curve
- ECE / Brier score による confidence calibration
- 意味テンプレート単位のcluster bootstrap 95%信頼区間
- データセットのスキーマ検証

## 実行

```bash
python generate_benchmark.py
python evaluate.py
python demo.py
python -m unittest discover -s tests -v
```

評価時のbootstrap反復数は変更できます。

```bash
python evaluate.py --bootstrap-samples 5000
```

## 実行済み test split 結果

| Metric | PLM-C0 v0.3 | Positive lexical baseline |
|---|---:|---:|
| Top-1 accuracy | 0.8333 | 0.5833 |
| Top-5 recall | 0.8889 | 0.8056 |
| MRR | 0.8083 | 0.7431 |
| Macro-F1 | 0.8894 | 0.7152 |
| UNRESOLVED precision | 0.9231 | 0.3333 |
| UNRESOLVED recall | 0.6000 | 0.4000 |
| Contradiction rejection | 0.7333 | 0.2667 |
| ECE（小さいほど良い） | 0.0874 | 0.2288 |

PLM Top-1 のcluster bootstrap 95%区間は `[0.7500, 0.9167]`、baselineとの差の95%区間は `[0.1250, 0.3889]` でした。

## 重要な解釈

test は異なる表層ラッパーを使いますが、dev と同じ72意味テンプレートを共有します。したがって、これは再現可能な機能・stress benchmarkであり、完全に独立した外部コーパスではありません。wrapperを独立標本として数えないよう、信頼区間は `template_group` 単位で再標本化しています。

stress subset では、訂正表現、長距離・不連続否定、無関係な文脈語、複数入力間の文脈混入に失敗しました。これらは `EVALUATION_REPORT.md` に集約してあります。

## 主なファイル

- `plm_c0/engine.py`: 三値Consensus本体とablation設定
- `plm_c0/evaluation.py`: 指標、校正、bootstrap、レポート
- `plm_c0/baseline.py`: 正票のみの語彙ベースライン
- `data/benchmark_v03.json`: 固定288ケース
- `generate_benchmark.py`: benchmark再生成
- `evaluate.py`: dev/test比較とablationの実行
- `EVALUATION_RESULTS.json`: ケース別を含む完全な機械可読結果

## スコープ外

談話構造、訂正の優先順位、構文解析、節ごとの文脈分離、学習器、Concept自動獲得、Role/Relation、実Phaseはまだ扱いません。これらは次段階の設計対象です。
