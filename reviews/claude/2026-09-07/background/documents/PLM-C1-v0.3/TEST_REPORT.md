# PLM-C1 v0.3 Test Report

## Result

**PASS — 72/72 GREEN**

```bash
python -m unittest discover -s tests -v
python evaluate.py
```

内訳はC0 v0.3が22件、凍結C1 v0.1が16件、凍結C1 v0.2が16件、C1 v0.3が18件です。

v0.3テストは、出力schema、子音+y複数形、過去・進行形、名詞の誤活用防止、談話改訂、英日retraction、event identity、allowlist複合語、open-set確信度、旧3データセット、凍結未見challenge、失敗群保存、feature ablation、calibration ablation、challenge hashを検証します。

| Check | Result |
|---|---:|
| Frozen regression Top-1 | 1.0000 |
| v0.1 challenge Top-1 | 1.0000 |
| v0.2 development challenge Top-1 | 1.0000 |
| Unseen v0.3 challenge Top-1 | 0.7000 |
| Unseen v0.3 ECE | 0.1288 |
| Unseen v0.2 baseline Top-1 | 0.3000 |
| Acceptance checks | 5/5 PASS |

新規challengeの6/20意味groupの失敗は、初回実行後に修正せず既知の能力限界として保持しています。
