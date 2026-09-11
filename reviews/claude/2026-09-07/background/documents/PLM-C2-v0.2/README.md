# PLM-C2 v0.2 — Bounded Discourse Resolution

PLM-C2 v0.2は、v0.1の型付きClaim Graphに、限定的で監査可能な談話解決を追加した実証実装です。標準ライブラリだけで動作し、凍結したC2 v0.1および全C1/C0比較実装を同梱しています。

## v0.2の追加機構

- `former` / `latter` / `the first` / `the second` の順序付き照応解決
- `rather` / `instead` を独立した訂正接続詞として扱う節境界
- `rather than` / `instead of` を訂正と誤認しない境界条件
- colon後の`revised` / `amended` / `updated`等を改訂節として分離
- 金融機関を主語とする`sponsor` / `fund` / `finance` / `underwrite` / `lend`のagentive affordance
- 否定・仮定・受動態ではagentive affordanceを適用しない制約
- 凍結v0.1の経験的正解率へ縮約する保守的confidence calibration
- Claim Graphの`REFERENCE` node、`RESOLVES_TO`、`REFERS_BACK_TO` edge

## 実行

```bash
python generate_benchmark.py
python generate_c1_challenge.py
python generate_c1_v02_challenge.py
python generate_c1_v03_challenge.py
python generate_c2_v01_challenge.py
python generate_c2_v02_challenge.py
python evaluate.py
python demo.py --out DEMO_OUTPUT.txt
python -m unittest discover -s tests -v
```

## 評価結果

| Dataset | Cases | C2 v0.2 | C2 v0.1 | C1 v0.3 | C1 v0.2 | C1 v0.1 | C0 v0.3 |
|---|---:|---:|---:|---:|---:|---:|---:|
| Frozen regression test | 216 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 0.8333 |
| C1 v0.1 challenge | 60 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 0.2000 | 0.1000 |
| C1 v0.2 challenge | 60 | 1.0000 | 1.0000 | 1.0000 | 0.6500 | 0.2500 | 0.3000 |
| C1 v0.3 challenge | 60 | 1.0000 | 1.0000 | 0.7000 | 0.3000 | 0.2500 | 0.2000 |
| C2 v0.1 development challenge | 60 | 1.0000 | 0.8000 | 0.3500 | 0.3000 | 0.2000 | 0.2500 |
| Unseen C2 v0.2 challenge | 60 | **0.9500** | 0.2500 | 0.2500 | 0.2500 | 0.2000 | 0.2000 |

新規未見セットのC2 v0.2 Top-1 95% cluster-bootstrap CIは`[0.8500, 1.0000]`、C2 v0.1との差は`+0.7000`、ECEは`0.1497`です。受入基準13項目はすべて合格しました。

## 凍結プロトコル

- Engine SHA-256: `4ccc0aa39f2b551c7a392bab2a69948c45a3752575542bda2aa49d5583a59c50`
- Concept data SHA-256: `740b467d5c1e4d1834c7663c8c1d47e147fa6e6cbf26059171e1a950e550575d`
- C2 v0.2 challenge SHA-256: `0a35d31af985633987ae465e7c91c340be20cabcbe820431981b5de208804717`

EngineとConcept dataを固定してから20意味テンプレート×3表層の新規challengeを作成し、初回評価後に両者を変更していません。

## 構成

- `plm_c2/`: C2 v0.2 engine・評価suite
- `plm_c2_v01/`: 凍結C2 v0.1
- `plm_c1/`, `plm_c1_v02/`, `plm_c1_v01/`, `plm_c0/`: 凍結比較実装
- `data/challenge_c2_v02.json`: post-implementation challenge
- `EVALUATION_RESULTS.json`: 全ケース・比較・ablation・graph audit
- `EVALUATION_REPORT.md`: 人間向け評価レポート
- `DEMO_OUTPUT.txt`: 実行例

## 限界

未見評価で残った失敗は、未登録の改訂役割語`reclassified`です。照応解決とagentive affordanceはいずれも閉じた規則集合であり、汎用構文解析・談話解析・世界知識モデルではありません。評価セットは外部コーパスではなく、手作業の機能benchmarkです。
