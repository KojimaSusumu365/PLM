# PLM-L1-SS-doc v0.2

未確定意味の保持と追加情報による局所訂正生成。二／三事象の短文書について、未確定の候補をSS信号に保持し、外部から確認を受けた項目だけを訂正して生成するPython実装です。

**これはその場の文書状態の訂正であり、訂正内容の長期学習ではありません。** 自然文の曖昧さの自動発見、自由な長文生成、SS-activeやP1/S1の統合は対象外です。

## まず動かす

Python 3.12とNumPy 2.3.5が必要です。Python本体は同梱しません。このREADMEのあるフォルダで実行します。

```powershell
python -m pip install -r requirements.txt
$env:OPENBLAS_NUM_THREADS='1'
$env:PYTHONIOENCODING='utf-8'
python -B examples/demo.py
```

デモでは次の二つを、外部で指定された読み候補として与えます。

> 太郎が花子を助けた。その後、花子が健太を褒めた。その後、健太が美咲を訪ねた。

> 太郎が花子を助けた。その後、由紀が健太を褒めた。その後、健太が美咲を訪ねた。

第二の事象の主体を「花子／由紀」の二候補で保持します。追加情報「由紀」を与える前は完成文を出しません。確認後に生成し、食い違う情報を受けた場合には再び矛盾として保留する一連の例です。

## 個別の操作

配布内のファイルを変更しないよう、出力先は未作成の外部パスに指定してください。

```powershell
python -B -m ss_partial inspect --model model --packet examples/pending.json
python -B -m ss_partial generate --model model --packet examples/pending.json
python -B -m ss_partial update --model model --packet examples/pending.json --message examples/teacher.json --out ../ssdoc02-corrected.json
python -B -m ss_partial generate --model model --packet ../ssdoc02-corrected.json --order reverse
```

inspectは確認対象を数値信号から復元して表示します。未確定なら終了コード2です。generateも未確定ならneeds_information・終了コード2となり、textを返しません。壊れた信号はabstain、不正・古い追加情報はrejectedです。

readは完全な制御文を一つ、または意味が一項目だけ異なる完全な制御文を二つ受け取ります。

```powershell
python -B -m ss_partial read --model model --texts '太郎が花子を助けた。その後、花子が健太を褒めた。' '太郎が花子を助けた。その後、由紀が健太を褒めた。' --out ../ssdoc02-new-pending.json
```

新しいパケットへの追加情報は、inspectが返すpacket_sha256とtargetを使って作ります。配布例のteacher.jsonを別のパケットに流用すると拒否します。digestは対象内容の整合検査で、教師認証や世界の真偽判定ではありません。

追加情報は `supply`、明示的な矛盾解決は `resolve`、既知値の明示的改訂は `revise` です。構造化観測を入力する `encode --observation ... --out ...`、観測全体を確認する `recover --packet ...` もあります。形式は [SPECIFICATION.md](SPECIFICATION.md) を参照してください。

## 試験と再現

```powershell
python -B -m unittest discover -s tests -v
python -B evaluate.py --out ../ssdoc02-rerun
python -B verify_release.py --out ../ssdoc02-verification --repeat ../ssdoc02-rerun
```

出力先は未作成のフォルダが必要です。評価に数分以上かかります。再現検査は、時間記録を除く全結果のバイト一致、144基準信号配列の再計算、保存モデル読込、readerと教師を持たない別プロセスでの生成を含みます。

主評価は二／三事象各4種類の出来事構成、計8構成から、各意味項目を一つずつ不確かにした336観測を作り、3符号で繰り返します。合計1008訂正例、訂正後2016生成要求です。1008種類の独立した自然文ではありません。主評価と開発、旧v0.1回帰、診断、偽の教師の検査は分けて保存します。

## 内容と限界

- `ss_partial/`：未確定状態のSS表現、検査、局所更新、生成接続、CLI。
- `ss_document/`、`plm_l1_v09/`：変更していない既存SS言語コア。
- `model/`：実行用の既存学習済み言語モデルと新しい符号設定。
- `data/`：既存教師対・語彙・回帰用制御文。
- `evaluation/`：固定評価条件、別実装の制御文法採点器、事前凍結記録。
- `results/`：全ケース、全生成文と採点、モデル、信号ハッシュと144基準配列。
- `verification/`：テスト、二重実行比較、隔離検査、費用・保全記録。
- `examples/`：実行可能なデモ、未確定・訂正・矛盾・解決後の数値パケット。

状態・候補数・事象構造・更新規則は手設計であり、未知状態の意味や確認手順を学習で発見したものではありません。人物6語、行為4語、限定された肯否・仮定・時間接続という既存の制御領域です。候補内の誤った追加情報を真実として確定してしまう限界があります。`eligible_for_inference=false`。

結果の解釈と到達範囲は [REPORT.md](REPORT.md)、配布前の検査は [VALIDATION.md](verification/VALIDATION.md) に記載します。
