# PLM-C1 v0.2 Test Report

## Result

**PASS — 54/54 GREEN**

```bash
python -m unittest discover -s tests -v
python evaluate.py
```

内訳はC0 v0.3回帰・評価22件、凍結C1 v0.1互換16件、C1 v0.2機能・評価16件です。

v0.2テストでは、出力schema、英語二重・三重否定、日本語二重否定、reported denial、談話訂正、複数形、仮定・否定・非空間relationの遮断、relation ablation、target分離、固定回帰、既存challenge、新規未見challenge、ablation suiteを確認しました。

| Check | Result |
|---|---:|
| Frozen regression Top-1 | 1.0000 |
| Known v0.1 challenge Top-1 | 1.0000 |
| Known challenge ECE | 0.1903 |
| Unseen v0.2 challenge Top-1 | 0.6500 |
| Unseen v0.1 baseline Top-1 | 0.2500 |
| Acceptance checks | 4/4 PASS |

新規challengeの7/20意味groupの失敗は、テスト異常ではなく凍結後評価で測定された既知の能力限界です。
