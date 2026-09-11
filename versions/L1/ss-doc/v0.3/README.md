# PLM-L1-SS-doc v0.3

訂正対応のSS記憶保持と再照会時の意味保持生成。外部で確認した対応をSS係数へ学習・保存し、新しく受け取った二／三事象の未確定観測を補って生成します。訂正済みパケットや完成文を保存して再表示する実証ではありません。

## 実行

Python 3.12／NumPy 2.3.5を使用します。Python本体は同梱しません。このREADMEのあるフォルダで実行してください。

```powershell
python -m pip install -r requirements.txt
$env:OPENBLAS_NUM_THREADS='1'
$env:PYTHONIOENCODING='utf-8'
python -B examples/demo.py
```

デモは「第二の出来事の主体は花子／由紀」という二つの明示的な読みを与え、由紀と確認してSS学習します。その後、別の出来事12件を背景学習し、記憶を保存・再読込します。主体の値を抜いた新しい観測から、由紀を補って文書を生成します。別IDの出来事には同じ答えを流用しません。

保存済みのデモ記憶と、訂正済みではない新しい未観測パケットから直接生成する例：

```powershell
python -B -m ss_retention generate --model model --memory examples/run/memory --episode demonstration-episode-03 --packet examples/run/fresh-packet.json --order reverse
```

この生成コマンドは現在の教師・原文・学習器を必要としません。ただし保存モデルと、外部で指定された正しい出来事IDが必要です。学習済み記憶自体には過去の教師対応がSS係数として含まれます。

## 新しい記憶を作る

```powershell
python -B -m ss_retention init --model model --method split_pair --out ../my-retention-empty
python -B -m ss_retention teach --model model --memory ../my-retention-empty --episode my-episode --packet ../my-pending.json --message ../my-confirmation.json --out ../my-retention-learned
python -B -m ss_retention generate --model model --memory ../my-retention-learned --episode my-episode --packet ../my-fresh-observation.json
```

パケット・外部確認はv0.2形式です。確認には対象パケットのハッシュ、target、value、supply／resolve／reviseを指定します。教えるときは対象外の項目が全てknownである必要があります。背景教師はteachに `--background` を付け、共有記憶だけを更新します。この保護指定は外部の方針で、自動学習されたものではありません。

出力先は未作成の配布フォルダ外のパスを指定してください。既存のモデル・パケットは上書きしません。`complete` は補完した数値パケットを `--out` へ書き、`generate` は生成文を返します。保留・拒否の生成は終了コード2です。

## 評価と検証

```powershell
python -B -m unittest discover -s tests -v
python -B evaluate.py --out ../ssdoc03-rerun
python -B verify_release.py --out ../ssdoc03-verification --repeat ../ssdoc03-rerun
```

主評価は2データ集合×2符号×2背景負荷×5方式＝40条件。各条件24件、合計960件の新しい再照会で、保存・再読込後の意味保持と生成を測ります。データ集合ごとの同じ24件を方式・負荷間で共有しており、960種類の独立した文書ではありません。

verify_releaseは二回目の全結果との一致、80件の選定済み再照会、全基準配列の再計算、保存された80記憶状態、教師・reader・学習器・評価器なしの別プロセス生成を検査します。全評価には数分以上かかります。生成された配布物内のファイルを変更するとマニフェスト検査で検出するため、`-B` を付けて配布外へ出力してください。

## 内容

- `ss_retention/`：新しいSS訂正記憶、外部確認学習、出来事ごとの照合、生成接続。
- `ss_partial/`、`ss_document/`、`plm_l1_v09/`：変更していない既存言語・部分観測コア。
- `model/`：既存の学習済みSS言語モデル。
- `data/`：再現・回帰用の既存教師対と語彙。
- `evaluation/`：固定計画、ケース生成、独立制御文法採点器、凍結記録。
- `results/`：教師列、全条件の生成・相関・採点、背景学習後と改訂後のSS記憶、基準信号。
- `verification/`：二重実行比較・単体試験・隔離生成・費用・旧版保全。
- `examples/`：デモと、推論だけを試せるSS記憶・新しい未観測パケット。

## 限界

これは外部IDとexactな非対象文脈に結び付いた訂正記憶です。似た自然文を同じ出来事と認識する能力、文法や曖昧さの学習、自由長文、未知語、P1/S1接続、SS-active全体の統合は実施していません。通常のラベルなし登録台帳とPython制御も使います。教師の誤りや、情報のない外界の変化を見抜くことはできません。`eligible_for_inference=false`。

詳細は [REPORT.md](REPORT.md)、境界と式は [SPECIFICATION.md](SPECIFICATION.md)、配布前検証は [VALIDATION.md](verification/VALIDATION.md) を参照してください。
