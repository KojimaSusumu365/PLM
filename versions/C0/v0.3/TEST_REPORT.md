# PLM-C0 v0.3 Test Report

## Result

**PASS — 22/22 GREEN**

```bash
python -m unittest discover -s tests -v
python evaluate.py
```

## Coverage

- v0.1の10動作を回帰確認
- v0.3のversion/diagnostics
- ASCII単語境界とそのablation
- 最長一致による重複抑制
- `UNRESOLVED` confidence
- 288件、72 template group、dev/test分割
- データスキーマと重複ID拒否
- 拡張指標とbootstrap区間
- full modelのbaseline優位
- negation ablationの性能低下

## Evaluation result

test 216件で Top-1 `0.8333`、Macro-F1 `0.8894`。positive lexical baselineはそれぞれ `0.5833`、`0.7152` でした。paired cluster bootstrapによるTop-1差の95%区間は `[0.1250, 0.3889]` です。

ユニットテストのGREENは、実装と評価器が定義どおり動くことを示します。stress subsetの失敗はテスト失敗ではなく、モデル能力の既知の未達として `EVALUATION_REPORT.md` に記録されています。
