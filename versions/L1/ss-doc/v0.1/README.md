# PLM-L1-SS-doc v0.1：SS型短文書生成の接続実証

二文・三文の限定された文書を読み、意味を一つのSS数値信号に保持して、提示順や文内語順を変えて生成するPython実装です。

**三文の読み書きまで接続しました。ただし、自由な日本語の長文生成器ではありません。** 三事象への構造拡張は手設計で、読み方・語彙・書き方・接続表現は既存v0.9から再学習したSS記憶を使います。最近のSS-activeの能動教師選択は今回は接続していません。

詳細は [REPORT.md](REPORT.md)、SS部分と通常処理の境界は [SPECIFICATION.md](SPECIFICATION.md) を参照してください。

## まず動かす

Python 3.12 / NumPy 2.3.5が必要です。Python本体は同梱しません。このREADMEのあるフォルダで実行してください。

```powershell
python -m pip install -r requirements.txt
$env:OPENBLAS_NUM_THREADS='1'
$env:PYTHONIOENCODING='utf-8'
python -B examples/demo.py
```

入力：

> 太郎が花子を助けた。その後、花子が健太を褒めた。その後、健太が由紀を訪ねた。

実際の生成例：

> 健太が由紀を訪ねた。その前に、花子が健太を褒めた。その前に、太郎が花子を助けた。

同じ出来事を逆の順で書き、明示された二本の前後関係を保持します。生成器に渡すのはSSパケットで、原文や入力の意味JSONではありません。

別の対応範囲内の文書も指定できます。

```powershell
python -B examples/demo.py --text '太郎が花子を助けた。その前に、花子が健太を褒めた。' --order reverse
```

## 読解と生成を別々に実行

```powershell
python -B -m ss_document read --model results/models/s0-c0 --text '太郎が花子を助けた。その後、花子が健太を褒めた。その後、健太が由紀を訪ねた。' --out ../my-ssdoc-packet.json
python -B -m ss_document generate --model results/models/s0-c0 --packet ../my-ssdoc-packet.json --order reverse
python -B -m ss_document recover --model results/models/s0-c0 --packet ../my-ssdoc-packet.json
```

`generate` はreaderや教師データがなくても動きます。`recover` は数値信号から復元した意味を表示する検査用コマンドで、表示した意味を生成器へ別途渡す必要はありません。

文内の語順は必要に応じて指定します。`subject` は主体先行、`object` は対象先行です。

```powershell
python -B -m ss_document generate --model results/models/s0-c0 --packet examples/packet-2.json --order reverse --goals object subject object
```

goalsの数は出来事数と一致させます。省略すれば、SS信号から復元した出来事数に合わせて主体先行で生成します。`examples/EXAMPLES.json` に三つの入力・生成例と検査用の意味を保存しています。

## 対応範囲

- 二文または三文。一文や四文以上は文書全体を保留。
- 人物：太郎、花子、次郎、美咲、健太、由紀。
- 行為：助ける、褒める、訪ねる、見つめるの限定された過去形。
- 肯定／否定、対応する「もし〜たら／なかったら」の限定表現。
- 文間：「その後、」「その前に、」または接続表現なし。
- 文内語順：主体先行／対象先行。文書の提示順：そのまま／逆順。

接続表現は直前の文との関係です。第一・第三文の関係を推測したり、原因や結果を作り足したりしません。代名詞・省略・新しい語彙・「だから」など未対応の表現では保留します。部分的に書けた文を完成品として返さず、文書全体を保留します。保留時のCLI終了コードは2です。

## 再学習・試験

```powershell
python -B -m ss_document train --component-pairs data/component_train.json --temporal-pairs data/temporal_train.json --lexicon data/lexicon.json --out ../ssdoc-refit
python -B -m unittest discover -s tests -v
python -B verify_release.py --out ../ssdoc-verify
python -B evaluate.py --out ../ssdoc-rerun
```

出力先は未作成で、配布フォルダの外に指定してください。既存パケット・モデルを上書きしません。配布物は最終マニフェストで検査するため、配布内への結果出力やキャッシュ生成は避け、`-B` を付けて実行します。

主評価は144種類の入力×3文書符号、各入力6通りの書き直し＝2592要求。文書信号は8192次元です。別に意味からの直接生成432要求、診断用252入力、旧二事象864件の回帰、未対応文・信号破損・局所編集を検査します。繰返しを含む数であり、2592種類の独立した文章を学習・評価したという意味ではありません。

## 内容

- `ss_document/`：新しい文書信号、二／三事象の接続、読解、生成、CLI。
- `plm_l1_v09/`：旧SS言語コアのソースをバイト不変で同梱。
- `data/`：既存の学習対・初期語彙・旧回帰データ。
- `evaluation/`：独立実装の制御文法採点器、ケース生成、固定評価条件と凍結記録。ランタイムは参照しません。
- `results/`：全入力、24モデル、生成全文、全採点、1266数値信号配列。
- `verification/`：再実行一致、旧版保全、隔離学習・生成、単体試験、診断結果。
- `examples/`：一コマンドデモと三つの数値パケット。

SS-active v0.3の教師対応照合、P1部分観測、S1チップ列・パイロット同期、自由な文書計画は未統合です。全成果物は `eligible_for_inference=false`。本版に必要なコードとデータは同梱し、過去のZIP全体は再帰同梱していません。
