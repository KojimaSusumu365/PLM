# PLM-C2 v0.3 — Relation-ready Claim Graph

PLM-C2 v0.3は、v0.2の型付きClaim Graphを、次段階のPLM-R1実験で利用できるRelation Frame契約へ発展させた実証実装です。標準ライブラリだけで動作し、凍結したC2 v0.2/v0.1および全C1/C0比較実装を同梱します。

## v0.3の追加機構

- `RelationFrame`: subject・predicate・object・voice・polarity・modalityを共通形式で保持
- Claim Graph schema v2: `RELATION_FRAME` node、`FRAME_OF`、`MAPS_TO`、`SUPERSEDES_CLAUSE` edge
- `reclassified`、`relabeled`、`redesignated`等の改訂役割family
- `the earlier/later/previous one`、限定的な`it`/`they`、`前者`/`後者`/`それ`の照応
- 明示的な先行候補が1件のときだけ単数代名詞を解決するambiguity guard
- agentive relationを`grant`、`award`、`allocate`、`invest`、`donate`、`subsidize`、`back`、`support`へ拡張
- 関係推論に対する否定・仮定・受動態の一貫した適用制約
- `犬、いや、猫`等の日本語訂正scope伝播と全角colon改訂
- v0.2の未見下限を基準にしたrelation-aware confidence calibration

## 実行

```bash
python generate_benchmark.py
python generate_c1_challenge.py
python generate_c1_v02_challenge.py
python generate_c1_v03_challenge.py
python generate_c2_v01_challenge.py
python generate_c2_v02_challenge.py
python generate_c2_v03_dev.py
python generate_c2_v03_challenge.py
python evaluate.py
python demo.py --out DEMO_OUTPUT.txt
python -m unittest discover -s tests -v
```

## 評価結果

| Dataset | Cases | C2 v0.3 | C2 v0.2 | C2 v0.1 | C1 v0.3 | C0 v0.3 |
|---|---:|---:|---:|---:|---:|---:|
| Frozen regression test | 216 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 0.8333 |
| C1 v0.1 challenge | 60 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 0.1000 |
| C1 v0.2 challenge | 60 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 0.3000 |
| C1 v0.3 challenge | 60 | 1.0000 | 1.0000 | 1.0000 | 0.7000 | 0.2000 |
| C2 v0.1 challenge | 60 | 1.0000 | 1.0000 | 0.8000 | 0.3500 | 0.2500 |
| C2 v0.2 challenge | 60 | 1.0000 | 0.9500 | 0.2500 | 0.2500 | 0.2000 |
| C2 v0.3 development | 30 | 1.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| Unseen C2 v0.3 challenge | 72 | **0.9583** | 0.4167 | 0.3750 | 0.3333 | 0.2917 |

新規未見セットのTop-1 95% cluster-bootstrap CIは`[0.8750, 1.0000]`、C2 v0.2との差は`+0.5416`、ECEは`0.0998`です。

Relation監査では278意味群から144フレームを生成し、Claim Graph invariant違反とRelation契約違反はいずれも0件でした。受入基準15項目はすべて合格しています。

## 凍結プロトコル

- Engine SHA-256: `95dc8f75e9a5e727d674251056a92850c954995d04bb24d1d89d087fb542cb51`
- Concept data SHA-256: `740b467d5c1e4d1834c7663c8c1d47e147fa6e6cbf26059171e1a950e550575d`
- C2 v0.3 challenge SHA-256: `1147428babad6704dcd197557dcea81e62c69d53fd59e20594fbdc0515d84f26`

EngineとConcept dataを固定してから24意味テンプレート×3表層のchallengeを作成し、初回評価後に両者を変更していません。

## 構成

- `plm_c2/`: C2 v0.3 engine・評価suite
- `plm_c2_v02/`, `plm_c2_v01/`: 凍結C2比較実装
- `plm_c1/`, `plm_c1_v02/`, `plm_c1_v01/`, `plm_c0/`: 凍結C1/C0実装
- `RELATION_SCHEMA.json`: R1実験向けRelation Frame JSON Schema
- `data/development_c2_v03.json`: v0.3開発診断
- `data/challenge_c2_v03.json`: post-implementation未見challenge
- `EVALUATION_RESULTS.json`: 全ケース・比較・ablation・Relation/Graph audit
- `EVALUATION_REPORT.md`: 人間向け評価レポート

## 限界

未見評価で残った失敗は未登録の改訂動詞`reidentified`です。Relation Frameは安定した交換形式ですが、predicate分類は依然として限定的な形態意味集合に基づきます。評価は同一開発セッションで作成した手作業benchmarkであり、外部コーパスではありません。したがって、R1は本番移行ではなく実験版から開始するのが妥当です。
