# PLM-C2 v0.1 — Typed Claim Graph

PLM-C2 v0.1は、C1のEvidence ledgerを型付きClaim Graphへ発展させた実証実装です。Source・Clause・Event・Entity・Concept・Evidence・Relationを個別ノードとして保持し、根拠・対象・時間・改訂関係を明示的な辺で接続します。標準ライブラリのみで動作します。

## C2の追加機構

- `claim_graph`: 7種類の型付きnodeと参照整合性を検査したedge
- decimalを壊さないピリオド文境界
- `subsequently`, `thereafter`, `following that` を時間的な別eventとして分離
- `originally → revised` をprovisional/corrective関係として処理
- 不規則lemma `bitten → bite`
- 閉じた複合語 `riverbank(s) → river`
- `river`への単純な直接票を、空間的bank-of関係がない場合に `RELATION_GATE`
- `event_links` に同一対象系列／別対象系列を記録

凍結したC1 v0.3、v0.2、v0.1、C0 v0.3を同梱しています。

## 実行

```bash
python generate_benchmark.py
python generate_c1_challenge.py
python generate_c1_v02_challenge.py
python generate_c1_v03_challenge.py
python generate_c2_v01_challenge.py
python evaluate.py
python demo.py
python -m unittest discover -s tests -v
```

## 結果

| Dataset | Cases | C2 v0.1 | C1 v0.3 | C1 v0.2 | C1 v0.1 | C0 v0.3 |
|---|---:|---:|---:|---:|---:|---:|
| Frozen regression test | 216 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 0.8333 |
| C1 v0.1 challenge | 60 | 1.0000 | 1.0000 | 1.0000 | 0.2000 | 0.1000 |
| C1 v0.2 challenge | 60 | 1.0000 | 1.0000 | 0.6500 | 0.2500 | 0.3000 |
| C1 v0.3 development challenge | 60 | 1.0000 | 0.7000 | 0.3000 | 0.2500 | 0.2000 |
| Unseen C2 v0.1 challenge | 60 | 0.8000 | 0.3500 | 0.3000 | 0.2000 | 0.2500 |

新規C2 challengeはengine完成後に20意味テンプレート×3表層を固定し、初回評価後にengine/Concept dataを変更していません。C2の未見ECEは `0.2582` です。

## 構成

- `plm_c2/`: C2 engine・評価suite
- `plm_c1/`, `plm_c1_v02/`, `plm_c1_v01/`, `plm_c0/`: 凍結比較実装
- `data/challenge_c2_v01.json`: C2 post-implementation challenge
- `EVALUATION_RESULTS.json`: 全ケース・比較・ablation・graph audit
- `DEMO_OUTPUT.txt`: graph要約を含む実行例

未見評価ではcolon内の改訂、`rather`訂正、スポンサー行為のaffordance、`latter`照応が未解決です。Claim Graphは明示構造ですが、汎用構文解析器や世界知識モデルではありません。
