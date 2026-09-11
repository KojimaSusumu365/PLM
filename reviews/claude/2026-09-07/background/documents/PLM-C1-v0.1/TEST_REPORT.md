# PLM-C1 v0.1 Test Report

## Result

**PASS — 38/38 GREEN**

```bash
python -m unittest discover -s tests -v
python evaluate.py
```

22件のC0 v0.3回帰・評価テストと、16件のC1テストを実行しました。

C1テストはEvidence schema、長距離否定、日本語述語否定、同一入力・入力間訂正、残差ablation、節内context、入力間context遮断、否定context、金融affordance、別インスタンス棄却、ASCII/日本語境界、固定回帰結果、challenge固定性、suite ablationを確認します。

固定回帰testではC1 Top-1 `1.0000`、C0 `0.8333`。未調整challengeではC1 `0.2000`、C0 `0.1000` でした。challengeの失敗はテスト異常ではなく、モデル能力の測定結果です。
