# PLM-L1-SS-doc v0.4

複数訂正のSS保持と連続改訂時の意味保持生成。外部で宣言した最大二つの訂正対象を、同じ文書の固定文脈から分離して照合する。確認された値はSS係数へ学習し、項目ごとの改訂番号で有効な照合先を選ぶ。外部ID・変更可能項目・改訂管理は設計した通常制御であり、それらまでSSが学習したわけではない。

## すぐ試す

このREADMEのあるフォルダから実行する。Python 3.12、NumPy 2.3.5で検証。Python本体は同梱しない。

```powershell
python -m pip install -r requirements.txt
$env:OPENBLAS_NUM_THREADS='1'
$env:PYTHONIOENCODING='utf-8'
python -B examples/demo.py
```

デモは三事象の第二事象について、主体と対象を交互に5回確認・改訂する。背景20件の確認を学習し、記憶を保存・再読込した後、二つの値を抜いた新しい数値パケットから文書を生成する。古い番号の確認は、現在のパケットへ結び直しても拒否する。

同梱した保存記憶から、学習処理なしで生成する：

```powershell
python -B -m ss_revision generate --model model --memory examples/run/memory --scope examples/run/scope.json --packet examples/run/fresh-packet.json --order reverse
```

入力は未観測パケットであり、完成パケットではない。現在の教師や原文は不要だが、過去の教師対応を学習したSS記憶と、外部指定した出来事ID・変更可能項目は必要。

## 新しい記憶と確認

```powershell
python -B -m ss_revision init --model model --method versioned_pair --out ../revision-empty
python -B -m ss_revision open --model model --memory ../revision-empty --scope ../scope.json --packet ../pending.json --out ../revision-opened
python -B -m ss_revision teach --model model --memory ../revision-opened --scope ../scope.json --packet ../pending.json --message ../confirmation.json --out ../revision-learned --packet-out ../updated.json
```

`scope.json` は `{"episode":"external-episode-id","mutable":["event:1/subject","event:1/object"]}` 形式。確認メッセージの作り方は[仕様書](SPECIFICATION.md)と[デモコード](examples/demo.py)にある。`open --background` で開いた文脈は共有記憶のみを学習する。同じ文脈の保護指定を途中で切り替えない。

出力先は未作成の配布外のパスを指定する。既存の記憶やパケットは上書きしない。生成の保留・棄権は終了コード2。無効な教師要求は例外として拒否し、保持係数を変更しない。ファイル保存途中の停電等に対する複数ファイルの完全なトランザクション保証はない。

## 再現

```powershell
python -B -m unittest discover -s tests -v
python -B evaluate.py --out ../ssdoc04-rerun
python -B verify_release.py --out ../ssdoc04-verification --repeat ../ssdoc04-rerun
```

全評価は48条件・1152照会・2304生成要求。同じ48訂正場面を方式・負荷・符号で繰り返す対応付き比較であり、1152種類の独立した自然文書ではない。処理は数分以上かかる。`-B` でbytecodeを残さず、結果を配布フォルダの外へ書く。

## 内容と限界

- `ss_revision/`：変更対象を除いた照合、改訂管理、SS保持への接続、数値入力からの生成。
- `ss_retention/`、`ss_partial/`、`ss_document/`、`plm_l1_v09/`、`model/`：変更していない既存SS記憶・言語コア・学習済みモデル。
- `evaluation/`、`tests/`：固定計画、データ生成、独立した制御文法採点、単体試験。
- `results/`：全教師列、全条件の実出力・採点・相関、背景学習前後の記憶、基準数値信号。
- `verification/`、`examples/`：検証記録、デモ、推論用の未観測入力。

言語モデルの文法係数は再学習していない。任意の自然文の同一出来事認識、変更対象の自動発見、未知語、自由長文、観測のない事実変更、教師の真偽判定、P1/S1接続、SS-active全体統合は未実施。過去版を消去・圧縮する機能もない。`eligible_for_inference=false`。

結果は[REPORT.md](REPORT.md)、詳細な検証範囲は[VALIDATION.md](verification/VALIDATION.md)を参照。
