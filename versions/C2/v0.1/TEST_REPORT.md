# PLM-C2 v0.1 Test Report

## Result

**PASS — 92/92 GREEN**

```bash
python -m unittest discover -s tests -v
python evaluate.py
```

内訳はC0 v0.3が22件、凍結C1 v0.1が16件、凍結C1 v0.2が16件、凍結C1 v0.3が18件、C2 v0.1が20件です。

C2テストはClaim Graph schema・参照整合性、decimal-safe文境界、時間的target遷移、改訂関係、不規則lemma、境界false positive、閉じた複合語、非空間relation gating、空間grounding、graph ablation、旧4セット、新規challenge、失敗群保存、全feature ablation、graph audit、challenge hashを検証します。

| Check | Result |
|---|---:|
| Frozen regression Top-1 | 1.0000 |
| C1 v0.1/v0.2/v0.3 challenge Top-1 | 1.0000 / 1.0000 / 1.0000 |
| Unseen C2 challenge Top-1 | 0.8000 |
| Unseen C1 v0.3 baseline Top-1 | 0.3500 |
| Unseen C2 ECE | 0.2582 |
| Claim Graph invariant failures | 0 |
| Acceptance checks | 9/9 PASS |

新規challengeの4/20意味groupの失敗は、初回実行後に修正せず能力限界として保持しています。
