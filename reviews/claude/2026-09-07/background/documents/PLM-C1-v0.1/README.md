# PLM-C1 v0.1 — Scoped Evidence / Residual Subtraction

PLM-C1 v0.1 は、PLM-C0のConcept三値多数決へ、節・入力・順序を持つEvidence ledgerと明示的な残差操作を追加した実証実装です。外部Pythonパッケージは使いません。

## 新しい表現

各Evidenceは従来の `concept`, `vote`, `weight` に加えて、次を保持します。

- `source_id`, `source_order`
- `clause_id`, `scope`
- `assertion_status`
- `active`, `effective_weight`
- `superseded_by`

実行結果にはEvidenceとともに、次の操作ログが含まれます。

- `NEGATE`: スコープ内の証拠を負票化
- `SUPERSEDE`: 訂正前の証拠を無効化し、残差重みを0へ落とす
- `ISOLATE`: 文脈boostを節内に限定
- `ISOLATE_CONFLICT`: 別インスタンスのConceptを単一選択へ混合せず棄却

## 実行

```bash
python generate_benchmark.py
python generate_c1_challenge.py
python evaluate.py
python demo.py
python -m unittest discover -s tests -v
```

## 固定v0.3回帰セットの結果

216件の固定test splitで評価しています。

| Metric | PLM-C1 v0.1 | PLM-C0 v0.3 |
|---|---:|---:|
| Top-1 | 1.0000 | 0.8333 |
| Top-5 | 1.0000 | 0.8889 |
| MRR | 0.9514 | 0.8083 |
| Macro-F1 | 1.0000 | 0.8894 |
| UNRESOLVED recall | 1.0000 | 0.6000 |
| Contradiction rejection | 1.0000 | 0.7333 |

C1-C0のpaired cluster bootstrap Top-1差は `+0.1667`、95%区間は `[0.0833, 0.2500]` でした。既知stress 12種類もすべて解決しています。

## Ablation

| Variant | Top-1 | Stress Top-1 |
|---|---:|---:|
| full | 1.0000 | 1.0000 |
| no scope | 0.9583 | 0.7500 |
| no correction | 0.9583 | 0.7500 |
| no residual | 0.9583 | 0.7500 |
| no negation | 0.8333 | 0.5833 |

固定回帰セットでは各機構の寄与を確認できました。

## Post-implementation challenge

過大評価を避けるため、実装後に別の20意味テンプレート×3表層、計60件を固定し、初回実行後はC1を調整していません。

| Metric | PLM-C1 v0.1 | PLM-C0 v0.3 |
|---|---:|---:|
| Top-1 | 0.2000 | 0.1000 |
| Top-5 | 0.5500 | 0.5000 |
| Macro-F1 | 0.1718 | 0.1032 |
| ECE | 0.6810 | 0.6883 |

未知の訂正マーカー、二重否定、reported denial、複数形、条件文、より広い談話境界では依然として失敗します。C1の既知ケースへの効果は確認できましたが、規則の一般化性能はまだ低い、というのがv0.1の結論です。

## 構成

- `plm_c1/`: C1 engine、評価suite
- `plm_c0/`: 凍結したC0 v0.3比較実装
- `data/benchmark_v03.json`: 既知の固定回帰セット
- `data/challenge_c1_v01.json`: 未調整challenge
- `data/concepts_c1.json`: C1専用Concept・文脈定義
- `EVALUATION_RESULTS.json`: ケース別を含む完全な結果

どちらのデータセットも手作業の機能benchmarkであり、外部コーパスではありません。
