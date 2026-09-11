# v0.3 検証記録と再現範囲

## 配布前に完了した検証

| 検査 | 結果 | 証拠 |
|---|---|---|
| 単体試験 | 32件成功 | [FINAL_TESTS.json](FINAL_TESTS.json) |
| 開発用の再照会 | 32件成功 | [DEVELOPMENT.json](DEVELOPMENT.json) |
| 既存完全文回帰 | 144/144正解 | [SUMMARY.json](SUMMARY.json) |
| 全評価二回 | 時間記録以外の207ファイルが完全一致 | [REPEATABILITY.json](REPEATABILITY.json) |
| 記憶の再読込・指紋 | 80状態成功 | [RELEASE_VERIFY.json](RELEASE_VERIFY.json) |
| 選定した主照会の再計算 | 40条件の先頭2件、80件一致 | [RELEASE_VERIFY.json](RELEASE_VERIFY.json) |
| 数値信号の再計算 | 保存された全66配列一致 | [RELEASE_VERIFY.json](RELEASE_VERIFY.json) |
| 隔離プロセス生成 | 二事象・三事象の2件成功 | [ISOLATED.json](ISOLATED.json) |
| 保護係数・失敗ケースの監査 | 背景による保護係数変更なし。誤完成1例、保護方式の保留各1例を記録 | [AUDIT.json](AUDIT.json) |
| 再訂正の他項目への影響 | 720件の意味補完のみを追加監査 | [REVISION_COLLATERAL.json](REVISION_COLLATERAL.json) |
| 旧版と推論時係数の不変性 | 成功 | [PRESERVATION.json](PRESERVATION.json) |
| 開発／評価分離と場面の非重複 | 成功 | [DATA_AUDIT.json](DATA_AUDIT.json) |

再計算80件は960主照会の抜取再生であり、第三回の全評価ではない。全960件を含む結果の再現性は、別途実行した二回の全評価の一致で確認した。追加の720件は設定変更なしの主評価後監査で、主評価の生成数へ加算しない。

## 情報の経路

長期記憶の保存ファイルは `state.json` と `weights.npz`。通常メタデータの各記憶領域にはkind、dimension、seed、登録キーハッシュ集合、更新回数、係数ハッシュがある。固定語彙もモデル設定に含むが、キーと正解を対応付けた教師辞書はない。

通常の登録台帳を保ったままSS係数をゼロ化すると正解を取り出せなくなることを単体試験で確認した。逆に係数を保ち台帳を外すと、正しい生SS支持があっても未登録として保留する。符号キャッシュを消しても回答は保持される。これらは、ラベルなし登録ゲートとSS係数の役割を区別する検査である。

推論の公開入口は `ss_retention.runtime` と `python -m ss_retention generate`。入力は既存言語モデル、保持記憶、episode ID、新しい数値パケット。原文・現在の教師値・正解意味配列を生成器へ渡さない。過去の確認は当然SS係数に学習済みである。

隔離検証用フォルダにはreader、training.py、新しいlearning.py、教師データ、評価器をコピーしない。新しいtarget未観測パケットからの生成であり、完成パケットの再表示ではない。インポート先が隔離フォルダ内であることを別プロセスで確認する。既存v0.2の `ss_partial/update.py` はSS記憶から支持された値を局所数値差分で補完するために含む。これは推論時の文書状態更新であり、長期保持係数の追加学習ではない。

## 保全と再現の手順

開発試験後、主評価前に `evaluation/FREEZE.json` を作成した。ソース、モデル、データ、設定、依存指定のハッシュ一致を全評価と再生時に確認する。説明文書・監査スクリプトは主評価後に作成可能とし、最終配布時の全ファイルマニフェストで固定する。

READMEのあるフォルダから実行する。出力先は存在しない配布外のフォルダを選ぶ。Python本体は同梱しない。

```powershell
python -m pip install -r requirements.txt
$env:OPENBLAS_NUM_THREADS='1'
$env:PYTHONIOENCODING='utf-8'
python -B -m unittest discover -s tests -v
python -B evaluate.py --out ../ssdoc03-independent-rerun
python -B verify_release.py --out ../ssdoc03-independent-verification --repeat ../ssdoc03-independent-rerun
python -B -m ss_retention generate --model model --memory examples/run/memory --episode demonstration-episode-03 --packet examples/run/fresh-packet.json --order reverse
```

`verify_release.py` は最終マニフェストがあれば全ファイルを検証する。bytecode等の追加ファイルも混ぜないよう `-B` を使う。既存の検証JSONは上書きしない。`verification/collect.py` や `audit.py` はリリース作成時に使った記録スクリプトで、完成済み配布フォルダ内での再実行用ではない。

浮動小数点のバイト一致は同じPython／NumPy／BLAS環境で確認したもの。異なるOSや依存バージョンまでの一致保証ではない。環境記録は[ENVIRONMENT.json](ENVIRONMENT.json)。符号数・閾値・係数容量・データseedは[固定計画](../evaluation/PROTOCOL.json)を参照。

## 配布ZIPの検査

配布前のファイル集合を `RELEASE_MANIFEST.json` に固定してZIPを作る。ZIPのCRC、安全な展開先、展開後全ファイルの一致を確認し、実展開したコピーから32単体試験、80照会と66信号の再計算、80記憶の読込、二回目全結果との比較、2件の隔離生成を行う。

その実施結果とZIPハッシュは、ZIPを後から変更しないようZIP外の `PLM-L1-SS-doc-v0.3-POSTZIP.json` に保存する。第三回の全評価を実施したと解釈しない。配布前記録の `manifest_files_checked=null` は、当時は最終マニフェスト作成前だったためである。ZIP展開後の記録には実際の検査件数を入れる。

## 検証していないもの

任意の日本語の自然さ・読解、同じ出来事の自動認識、外部教師の真偽、観測されていない事実変更、未知語、自由長文、複数未確定項目間の依存推論、学習された保護対象選択、実運用の教師コスト最適化、P1/S1またはSS-active全体の接続は検証していない。評価器は独立した制御文法実装で、人間の第三者評価ではない。
