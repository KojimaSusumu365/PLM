# PLM-C1 v0.2 — Polarity Composition / Discourse State

PLM-C1 v0.2は、v0.1のscoped Evidence ledgerと残差除去を維持しながら、極性合成、談話状態、限定的な形態正規化、対象ID、明示的な関係Evidenceを追加した実証実装です。標準ライブラリのみで動作します。

## v0.2の要点

- `polarity_depth`: 否定辞の奇偶で正負を合成し、二重否定・reported denialを処理
- `discourse_state`: `provisional` / `corrective` / `hypothetical` / `asserted`
- `target_id`: 異なる対象インスタンスのEvidenceを分離
- `relations`: 曖昧語と文脈triggerの接続・極性・適用可否を記録
- 限定的な英語複数形照合とASCII/日本語混在境界
- 凍結したv0.1実装を `plm_c1_v01/` に同梱し、同一条件で比較

既存の `NEGATE`, `SUPERSEDE`, `ISOLATE`, `ISOLATE_CONFLICT` に加え、`POLARITY_COMPOSE`, `STATE_TRANSITION`, `RELATE` の操作ログを返します。

## 実行

```bash
python generate_benchmark.py
python generate_c1_challenge.py
python generate_c1_v02_challenge.py
python evaluate.py
python demo.py
python -m unittest discover -s tests -v
```

## 結果

| Dataset | Cases | C1 v0.2 Top-1 | C1 v0.1 | C0 v0.3 |
|---|---:|---:|---:|---:|
| Frozen v0.3 regression test | 216 | 1.0000 | 1.0000 | 0.8333 |
| Known v0.1 challenge | 60 | 1.0000 | 0.2000 | 0.1000 |
| Unseen v0.2 challenge | 60 | 0.6500 | 0.2500 | 0.3000 |

既存challengeでのECEはv0.1の `0.6810` からv0.2の `0.1903` へ低下しました。新規challengeはv0.2 engine完成後に20意味テンプレート×3表層を固定し、初回評価後にengine/Concept dataを調整していません。

## 構成

- `plm_c1/`: v0.2 engine・評価suite
- `plm_c1_v01/`: 凍結したv0.1比較実装
- `plm_c0/`: 凍結したC0 v0.3比較実装
- `data/benchmark_v03.json`: 固定回帰benchmark
- `data/challenge_c1_v01.json`: v0.1 post-implementation challenge
- `data/challenge_c1_v02.json`: v0.2 post-implementation challenge
- `EVALUATION_RESULTS.json`: ケース別を含む完全な評価結果

新規未見セットでは、未知の談話・対象切替マーカー、不規則複数形・過去形、複合語内部の関係語が未解決です。すべて手作業の機能benchmarkであり、外部コーパスや実世界性能の代替ではありません。
