# PLM-C1 v0.3 — Normalization / Revision Roles / Event Identity

PLM-C1 v0.3は、v0.2で残った形態変化、談話改訂、対象切替、複合語、未知語時の過信を扱う実証実装です。v0.2の極性合成・談話状態・対象ID・関係Evidence・残差操作を維持し、標準ライブラリのみで動作します。

## v0.3の追加機構

- 品詞を限定した英語lemma照合：`puppies → puppy`, `barked → bark`, `vocalizing → vocalize`
- `retracted` 談話状態と明示的な `RETRACT` 操作
- provisional / corrective / retractionという談話役割による改訂処理
- 節単位のevent identityと `TARGET_SHIFT`
- allowlist方式の安全な複合語分解：`riverfront → river`
- Evidenceが一件もないdomainでの保守的なopen-set確信度
- 形態・複合語変換を `normalizations` として出力

凍結したv0.2、v0.1、C0 v0.3を同梱し、同一データで比較できます。

## 実行

```bash
python generate_benchmark.py
python generate_c1_challenge.py
python generate_c1_v02_challenge.py
python generate_c1_v03_challenge.py
python evaluate.py
python demo.py
python -m unittest discover -s tests -v
```

## 結果

| Dataset | Cases | C1 v0.3 | C1 v0.2 | C1 v0.1 | C0 v0.3 |
|---|---:|---:|---:|---:|---:|
| Frozen regression test | 216 | 1.0000 | 1.0000 | 1.0000 | 0.8333 |
| Known v0.1 challenge | 60 | 1.0000 | 1.0000 | 0.2000 | 0.1000 |
| Development v0.2 challenge | 60 | 1.0000 | 0.6500 | 0.2500 | 0.3000 |
| Unseen v0.3 challenge | 60 | 0.7000 | 0.3000 | 0.2500 | 0.2000 |

新規未見challengeでのECEはv0.2の `0.5474` からv0.3の `0.1288` へ低下しました。challengeはv0.3 engine完成後に20意味テンプレート×3表層を固定し、初回評価後にengine/Concept dataを調整していません。

## 構成

- `plm_c1/`: v0.3 engine・評価suite
- `plm_c1_v02/`, `plm_c1_v01/`, `plm_c0/`: 凍結比較実装
- `data/benchmark_v03.json`: 固定回帰benchmark
- `data/challenge_c1_v01.json`, `challenge_c1_v02.json`: 既知・開発診断
- `data/challenge_c1_v03.json`: v0.3 post-implementation challenge
- `EVALUATION_RESULTS.json`: 全ケース・比較・ablation結果

未見評価では、同一入力内のピリオド境界、未知の談話cue、`bitten`、閉じた複合語`riverbank`、非空間的な`river`言及が未解決です。各セットは手作業の機能benchmarkであり、外部コーパスではありません。
