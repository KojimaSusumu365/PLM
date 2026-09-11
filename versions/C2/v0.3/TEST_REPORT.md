# PLM-C2 v0.3 Test Report

## 結果

- 実行: `python -m unittest discover -s tests -v`
- テスト数: 146
- 成功: 146
- 失敗・エラー: 0
- 実行時間: 23.288秒

## 内訳

- C0 v0.3: 22
- C1 v0.1: 16
- C1 v0.2: 16
- C1 v0.3: 18
- C2 v0.1: 20
- C2 v0.2: 22
- C2 v0.3: 32

## C2 v0.3の検証範囲

- Relation Frame必須fieldとJSON Schema
- Claim Graph schema v2、provenance edge、全invariant
- 改訂役割familyとablation
- 単数・複数・順序・日本語照応とambiguity guard
- 訂正節への代名詞Evidence再流入防止
- role affordanceの肯定・否定・仮定・受動態
- 日本語訂正scopeと全角colon revision
- relation-aware calibrationのECE改善
- 先行6評価セットの完全回帰
- 開発診断100%、新規未見challenge初回結果とhash固定
- 15受入基準とR1実験開始条件

完全な実行ログは`TEST_OUTPUT.txt`に保存している。
