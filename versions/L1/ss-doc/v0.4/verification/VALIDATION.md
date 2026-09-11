# v0.4 検証範囲

## 実施した検査と記録

- [TESTS.json](TESTS.json)：開発後・凍結前の62単体試験（継承32件、新規30件）。
- [DEVELOPMENT.json](DEVELOPMENT.json)：開発用8訂正場面で6方式、合計48照会。旧照合と記憶なしは保留、新しい四方式はそれぞれ8件成功。
- [SUMMARY.json](SUMMARY.json)：48条件の全主評価・対照評価を集計。
- [REPEATABILITY.json](REPEATABILITY.json)：二回の全実行結果のバイト一致。処理時間記録だけを除外。
- [RELEASE_VERIFY.json](RELEASE_VERIFY.json)：96保存記憶の読込、48条件の各先頭2件＝96照会の再計算、保存された全基準配列の再計算。
- [ISOLATED.json](ISOLATED.json)：二項目を抜いた二事象・三事象の数値入力から、別プロセスで推論。低負荷の固定した条件を選び、成功数と保留数を実測する。
- [PRESERVATION.json](PRESERVATION.json)：旧v0.3の303ファイルと旧ZIPの不変、継承59ファイルの一致、推論前後の係数不変。
- [DATA_AUDIT.json](DATA_AUDIT.json)：560出来事IDは一意。開発用との重複は0。評価集合間は、改訂後を含む粗い場面指標で1件の重複があり、厳密な完全分離の検査は不合格。詳細を以下に記す。
- [AUDIT.json](AUDIT.json)：出来事／役割間の入替え、各段階、未知文脈への生SS支持、費用の読み取り監査。
- [FINAL_TESTS.json](FINAL_TESTS.json)：配布前の62単体試験再実行。

二回の全評価と、選定96照会の再生検査を区別する。後者は第三回の全評価ではない。主評価1152照会は同じ48場面を複数条件で繰り返したもの。各5段階のチェックポイントは先頭2場面のみ、全条件合計480件で、意味補完だけを検査し、生成文書の主評価件数に加算しない。主評価の正しい完成と、最終文書の意味の正しさも別々に数える。

場面の粗い指標は、事象順と時間関係を除いて事象の役割／値を比較する。評価集合200の訂正対象 `r200/10` の第5段階と、評価集合201の背景 `r201/230` の第1・2段階に1場面の重複があった。初期場面同士、訂正対象場面同士、開発／評価間の重複は0。各データ集合の記憶は独立に初期化しており、集合を跨いだ教師の混入はないが、全改訂場面が完全非重複とは主張しない。評価後のデータ差替えは行わず、DATA_AUDITのpassed=falseを残す。他の再現・実行検証成功と混同しない。

## 教師と推論の分離

実行時は `ss_revision.runtime`、既存SS記憶の読み出し、部分意味の数値更新、既存生成器を使う。教師処理は `ss_revision.learning` と継承した `ss_retention.learning` に分離している。

隔離フォルダにはreader、training.py、learning.py、教師データ、評価器を置かず、保存SS係数・改訂番号・外部scope・二項目未観測の入力から実行する。インポート先が隔離フォルダ内であることも確認する。既存v0.2の数値パケット更新器 `ss_partial/update.py` は補完に必要なため含む。過去の教師情報はSS係数として学習済みであり、過去の情報すら一切ないという意味ではない。

通常メタデータは文脈ハッシュ、役割、改訂番号、保護指定、固定候補語彙を含む。SS係数のゼロ化で値を取り出せなくなること、推論による自己学習がないこと、古い確認を拒否しても記憶が変わらないことを試験する。外部確認の真偽認証や、無権限のプロセスによるメタデータ改ざんに対するセキュリティ保証ではない。

## 固定と再現

コード・データ生成・モデル・依存指定・評価計画を開発試験後に `evaluation/FREEZE.json` で固定。評価結果を見て受理閾値、符号次元、seedを変更しない。説明資料と読み取り監査は主評価後に作成し、配布時に全ファイルマニフェストで固定する。

READMEのあるフォルダから、存在しない配布外の出力先を指定して実行する。

```powershell
python -m pip install -r requirements.txt
$env:OPENBLAS_NUM_THREADS='1'
$env:PYTHONIOENCODING='utf-8'
python -B -m unittest discover -s tests -v
python -B evaluate.py --out ../ssdoc04-independent-rerun
python -B verify_release.py --out ../ssdoc04-independent-verification --repeat ../ssdoc04-independent-rerun
```

完成した配布フォルダ内でcollectやsummarizeを再実行しない。これらはリリース作成用の排他的出力スクリプトであり、既存の証拠JSONを上書きしない。再評価はevaluateとverify_releaseを配布外出力で使う。

同一環境でのバイト一致を確認する。異なるBLAS、NumPy、OSまで浮動小数点の一致を保証するものではない。[環境](ENVIRONMENT.json)、[固定計画](../evaluation/PROTOCOL.json)、[費用](BENCHMARK.json)を参照。

## ZIP検査

全ファイルマニフェストを作ってZIPを固定した後、実展開したコピーで62単体試験、96選定照会と全基準配列の再計算、96記憶の読込、二回目全結果との一致、2件の隔離推論、マニフェストの一致を検査する。ZIPのCRC、安全な展開先、展開前後の全ファイルハッシュも検査する。

結果はZIP外の `PLM-L1-SS-doc-v0.4-POSTZIP.json` と `PLM-L1-SS-doc-v0.4-VERIFICATION.md` に記録し、作成済みZIPは書き換えない。配布前の検証JSONでmanifest件数がnullなのは、最終マニフェスト作成前だったためである。

## 未検証の範囲

人間による自然さ評価、一般日本語、変更対象の自動発見、同一出来事の自動認識、複数項目の論理的依存学習、教師の真偽、観測されていない外界の変化、無制限の改訂・記憶容量、並列書込み、電源断時の保存原子性、P1/S1、SS-active全体統合は保証しない。生成採点器は別実装の制御文法であり、第三者による独立研究レビューではない。`eligible_for_inference=false`。
