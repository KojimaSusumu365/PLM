# PLM-C0 v0.2 Test Report

## Result

**PASS — 16/16 GREEN**

実行コマンド:

```bash
python -m unittest discover -s tests -v
python evaluate.py
```

## 回帰テスト

v0.1 の10ケースをすべて維持し、v0.2 の version/diagnostics、データセット件数、指標範囲、baseline比較、contradiction rejection、minority evidence retention を6テスト追加しました。

## 固定データセット評価

| Metric | PLM-C0 v0.2 | Positive lexical baseline | Delta |
|---|---:|---:|---:|
| Top-1 accuracy | 1.0000 | 0.6944 | +0.3056 |
| Top-5 recall | 1.0000 | 0.9444 | +0.0556 |
| MRR | 0.9444 | 0.8750 | +0.0694 |
| UNRESOLVED precision | 1.0000 | 0.2857 | +0.7143 |
| UNRESOLVED recall | 1.0000 | 0.8000 | +0.2000 |
| Minority evidence retention | 1.0000 | 1.0000 | 0.0000 |
| Contradiction rejection | 1.0000 | 0.8000 | +0.2000 |

評価対象は同梱の手作業36ケースです。完全な Top-1 はこの閉じた機能データセット上の結果であり、未知データへの一般化を示しません。MRR が Top-1 より低いのは、4件の階層的限定ケースで raw score 1位の上位Conceptではなく、直接証拠のある下位Conceptを最終選択したためです。

詳細は `EVALUATION_REPORT.md` と `EVALUATION_RESULTS.json` を参照してください。
