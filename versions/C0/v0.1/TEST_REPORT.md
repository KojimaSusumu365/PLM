# PLM-C0 v0.1 Test Report

## Result

**PASS — 10/10 GREEN**

実行コマンド:

```bash
PYTHONPATH=. python -m unittest discover -s tests -v
```

詳細は `TEST_OUTPUT.txt` を参照してください。

## Covered cases

1. 犬 + 吠えるの直接復調
2. 複数言い換えからDOGへ合意
3. `犬ではなく猫` の否定処理
4. `動物が吠える` からDOGを捏造しない
5. financial bankの文脈解決
6. river bankの文脈解決
7. 未知ConceptをUNRESOLVEDにする
8. CAT支持によるDOGへの弱い兄弟負票
9. ANIMALからDOGへの階層的限定
10. VEHICLEの独立Concept選択

## Interpretation

このGREENはPLM全体の有効性を証明するものではありません。v0.1で定義した**三値証拠 + 重み付き多数決 + contradiction + hierarchy-aware narrowing**が、用意した最小ケースで仕様通り動いたことだけを意味します。
