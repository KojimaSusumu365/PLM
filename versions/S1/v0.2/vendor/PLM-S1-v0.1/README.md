# PLM-S1 v0.1

明示的なチップ列の拡散・逆拡散と、パイロットによる同期を接続した最小実証です。Python/NumPyの現行構成を維持し、P1 v0.2全260ファイルを変更せず同梱しています。

```text
R1/C2観察 → 凍結P1符号器（2048複素成分）
          → 各成分を4チップへ拡散
          → 前後パイロット・ガードを含む8480チップ
          → 人工チャネル（整数遅延・位相・小CFO・欠落・雑音）
          → パイロット同期 → 逆拡散 → 凍結P1 v0.2で候補回復
```

この版で実装したSS復調は **人工的な離散複素ベースバンド** に限定します。実無線機・標準通信規格・独立意味評価の実証ではありません。数値的に回復しても `eligible_for_inference: false`、観察専用のままです。

## 結果を見る

未知評価前にREADMEと実装を固定します。確定結果は `results/RELEASE_DECISION.md` と `results/EVALUATION_REPORT.md`、実行検証は `verification/VERIFICATION_REPORT.md` を参照してください。初回結果は `FIRST_EVALUATION.json` に記録し、再実行で上書きしません。

比較は直接P1参照、非拡散の4回反復、実SS受信器、同期なし、真の補正を使う評価用oracleの5方式です。すべて同じチップ数・送信エネルギー・P1情報量で比較します。直接参照は空きチップを含むため、反復方式も対照に入れています。

「25%観測」は今回は**チップの25%**です。P1の2048成分の25%ではありません。複数チップの少なくとも1つが残れば成分を推定できるため、実際の成分カバー率を別に報告します。この効果はSSだけでなく非拡散反復にもあります。

## 実行例

Python 3.12 / NumPy 2.3.5で検証。新しい依存の追加や外部サービスの接続はしていません。以下は展開したPLM-S1-v0.1フォルダで実行します。`python` はご自身のPython実行ファイルに置き換えてください。

```powershell
$env:OPENBLAS_NUM_THREADS = '1'
python -B -m unittest discover -s tests -v
python -B -m plm_s1 decode --packet examples/RECEIVED_CHIP_PACKET.json --query examples/QUERY.json --catalogue examples/PUBLIC_CATALOGUE.json --expected-codebook examples/CODEBOOK.json --expected-link examples/LINK.json --out recovered.json
python -B verify_release.py --out-dir verification-repeat
```

`--expected-codebook` と `--expected-link` は受信側の固定情報として必須です。受信パケットや照会へ正解、真の遅延・位相・周波数を追加すると拒否します。通常の入力frame、R1 envelopeからのencodeにも対応します。

全S1数値評価だけを再現する場合:

```powershell
python -B evaluate.py --split evaluation --out-dir evaluation-repeat
```

全テスト・CLI・旧P1の数値部分回帰を実行し、S1数値結果は再計算せず保存ハッシュで確認する短い検証:

```powershell
python -B verify_release.py --smoke-only --out-dir smoke-repeat
```

全評価の再計算を省いた場合は検証報告にも明記します。数値受入が未達なら通常の検証コマンドはexit 1です。初回評価を見た後に閾値を変更して成功に書き換えることはしません。

## 同梱内容

- `NUMERICAL_SPEC.md`: チップ列、正規化、同期推定、比較の公平性と限界。
- `S1_INTERFACE.md`, `WIRE_CONTRACT.json`: 受信契約と観察専用境界。
- `evaluation/PROTOCOL.json`, `evaluation/SELECTION.md`: 事前の評価条件と開発判断。
- `examples/TX_CHIPS.json`: 8480個の明示的な送信チップ。
- `examples/RECEIVED_CHIP_PACKET.json`: 受信器に渡す、欠落・雑音・ずれを含む信号。
- `examples/DESPREAD_VALUES.json`: 逆拡散後のP1成分と観測マスク。
- `examples/EVALUATOR_CHANNEL_TRUTH.json`: 真値は評価者用の別ファイル。受信器には渡さない。
- `vendor/PLM-P1-v0.2/`: 以前の成果物を丸ごと無変更で保存。旧版の制約や結果も維持。

## 残る課題

二つのパイロットによる周波数推定には折り返し曖昧性があり、事前に定めた小さな周波数範囲の外では誤同期を受理し得ます。同期のstatusだけで成功とは扱わず、回復結果や評価者による誤差を別に確認します。

分数チップ遅延、サンプル時計ずれ、時間変動周波数、マルチパス、誤り訂正、RF入出力、パイロット認証、独立意味評価は未実装です。推論を開放する段階には進めていません。
