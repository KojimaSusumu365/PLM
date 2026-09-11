# PLM-L1–P1/S1 接続 v0.1

意味信号のチップ化・同期復調と意味保持生成の接続実証です。Python/NumPy上の離散複素ベースバンドを扱い、RF実機は使用しません。

L1の数値意味信号をP1の単位複素位相符号で結合し、4フレームに分割してS1で拡散します。受信側は公開パイロットから同期し、逆拡散・位相結合解除・部分相関回復を行います。その信号から外部教師の値を読み取り、SS記憶を更新します。別の欠測照会を受信し、保存・再読込したSS記憶で補完して文章を生成します。

## 資料

- [結果・生成例・限界](REPORT.md)
- [接続仕様](SPECIFICATION.md)
- [コーパスと評価設計](CORPUS.md)
- [検証範囲](verification/VALIDATION.md)
- [固定した評価条件](evaluation/PROTOCOL.json)
- [全条件集計](results/SUMMARY.json)
- [数値受入判断](results/DECISION.json)

## 実行

リリースフォルダで実行します。Python 3.12 / NumPy 2.3.5を使用しました。生成先は未使用の名前を指定し、リリースの外へ置いてください。

```powershell
$env:OPENBLAS_NUM_THREADS='1'
$env:PYTHONIOENCODING='utf-8'
python -B -m unittest discover -s tests -v
python -B examples/demo.py --out ../bridge-demo
```

デモは固定した2事象・3事象の2例について、文章読解、数値符号化、教師信号の受信・学習、別プロセスでの欠測照会と生成を行います。送信チップ、受信チップ、チャネル真値、SS記憶、生成結果を分離して保存します。

受信した数値信号からの個別操作例です。

```powershell
python -B -m bridge receive --model model --wire ../bridge-demo/case0/query-received.json --message-id evaluation/0/query
python -B -m bridge generate --model model --memory ../bridge-demo/case0/memory --scope ../bridge-demo/case0/scope.json --wire ../bridge-demo/case0/query-received.json --message-id evaluation/0/query --order reverse
```

教師として受け入れることを明示して学習する操作です。教師信号の正しい形式・数値回復は確認しますが、送信者や内容の真偽は認証しません。

```powershell
python -B -m bridge learn --model model --scope ../bridge-demo/case0/scope.json --wire ../bridge-demo/case0/teacher-received.json --message-id evaluation/0/teacher --out ../new-teacher-memory
```

送信器のPython APIは `bridge.carrier.encode(model, numeric_packet, message_id)` です。受信器に元文章・正解意味・真の位相や周波数を渡す引数はありません。`repeat` 対照を受ける場合は `--mode repeat` を明示します。CLIの終了値2は保留・拒否を含み、成功扱いにはしません。

## 評価の再現

```powershell
python -B evaluate.py --out ../bridge-evaluation-repeat
python -B verify_release.py --out ../bridge-verification-repeat --repeat ../bridge-evaluation-repeat
```

全388条件を再評価します。検証器は保存記憶全件、集計、コーパスを照合し、条件・方式・事象数ごとの代表44条件を教師受信から再実行します。教師・評価資料を置かない別フォルダでの2照会も含みます。既存結果への上書きはしません。

## 到達範囲

既存語彙・文型、2～3事象、文書ごとの指定2項目を保持する最小実証です。旧P1の役割別干渉除去受信器へL1をそのまま渡した実装ではなく、L1用の部分相関アダプターを追加しています。S1の拡散・同期・逆拡散は既存実装を無変更で使用します。

L1の記憶・生成内部の全演算を時間波形上で動かしたわけではありません。v0.6の再確認先選択器、自由長文、新語・文法学習、実機通信、認証、分数チップ遅延・時計ずれは今回の対象外です。
