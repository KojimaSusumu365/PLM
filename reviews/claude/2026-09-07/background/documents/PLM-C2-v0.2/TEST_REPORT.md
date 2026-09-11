# PLM-C2 v0.2 Test Report

## 結果

- 実行: `python -m unittest discover -s tests -v`
- テスト数: 114
- 成功: 114
- 失敗・エラー: 0
- 実行時間: 19.007秒

## 内訳

- C0 v0.3: 22
- C1 v0.1: 16
- C1 v0.2: 16
- C1 v0.3: 18
- C2 v0.1: 20
- C2 v0.2: 22

## C2 v0.2の検証範囲

- ordered referenceの選択、ablation、Claim Graph接続
- `rather`/`instead`訂正と比較構文negative control
- colon revision境界とablation
- agentive affordanceの肯定・否定・仮定・受動態
- confidence calibrationの範囲とECE改善
- 旧5評価セットの完全回帰
- 新規challengeの初回結果・failure集合・hash固定
- 13受入基準と全graph invariant

完全な実行ログは`TEST_OUTPUT.txt`に保存している。
