# PLM-L1-SS-core v0.1

時間波形によるSS記憶の照合・誤差更新と意味保持生成。

既存SS重畳記憶を、頭尾パイロットを持つ有限の読出し窓で1tickずつ照合し、外部教師との差を次の書込み窓で1列ずつ反映する最小実証。2事象・指定2項目の不足意味を保存済みSS記憶から補い、2通りの短文書を生成する。

Python離散時間シミュレーションであり、実回路、汎用日本語生成、全層SS化、従来方式に対する精度優位を実証したものではない。パイロット正常な本文破損や誤った外部教師も通過し得る。全受信成功という当初基準の未達を含め、結果は `REPORT.md` を参照。

## 同梱物

- `ss_core/`: 今回の逐次照合・更新・冷間生成・CLI。
- `bridge/`, `ss_*`, `plm_l1_v09/`, `vendor/`, `model/`: 接続に必要な既存実装と学習済みモデル。元リリースからのコピーはハッシュ照合済み。
- `data/`, `evaluation/`, `evaluate.py`: 固定コーパス、条件、独立文法評価、全評価コード。
- `tests/`: 新規30テスト。
- `results/`: 全240照会の結果、更新記録、12組の保存記憶、数値差、受信保留、故障試験。
- `examples/`: 別プロセスで実行した教師受信→学習→保存→生成の2実例、内部波形NPZと途中積算ログ。
- `verification/`: テスト・再実行・隔離生成・元版保全・評価処理修正履歴。
- `SPECIFICATION.md`, `CORPUS.md`, `REPORT.md`: 仕様、データ設計、結果と限界。

過去全リリースの全資料を再収録したものではなく、今回を再現するコード・モデル・資料・結果を収録する。新規実装と継承実装はディレクトリで分けている。

## 実行環境

Python 3.11以降、NumPy 2.3.5。今回の実環境は検証記録を参照。ネットワークAPIやLLMサービスは使用しない。以下はZIPを展開したリリース直下で実行する。`python` は環境のPython実行ファイルに置き換えてよい。

```powershell
$env:OPENBLAS_NUM_THREADS='1'
$env:PYTHONIOENCODING='utf-8'
python -B -m unittest discover -s tests -v
python -B evaluate.py --out ../ss-core-repeat
python -B verify_release.py --out ../ss-core-verification --repeat ../ss-core-repeat
```

出力先は新規ディレクトリにする。既存結果を上書きしない。再評価先をリリース直下に作ると最終配布manifestのファイル集合が増えるため、manifest込みの検証ではリリース外の出力先を推奨する。

## 保存済み記憶から生成

教師ファイルは不要。以下は2事象の主体・対象を欠測にしたサンプル。

```powershell
python -B -m ss_core generate --model model --memory examples/demo-0/memory --scope examples/demo-0/scope.json --wire examples/demo-0/query-wire.json --message-id ss-core01/evaluation/focal/0/query --chunk 37
```

逆順・対象焦点を指定する場合は `--order reverse --goals object subject` を追加する。時間関係を含む欠測の例は `demo-4` と `evaluation/focal/4/query`。

## 外部教師から新規学習

```powershell
python -B -m ss_core learn --model model --scope examples/demo-0/scope.json --wire examples/demo-0/teacher-wire.json --message-id ss-core01/evaluation/focal/0/teacher --out new-memory --chunk 37
```

CLIの正常終了コードは0、受信・生成・更新の保留や拒否は2。入力された教師の真偽や送信者を認証する機能ではない。新しい文章を扱う場合も、現在は同梱語彙・文法・2事象2対象の制約内である。
