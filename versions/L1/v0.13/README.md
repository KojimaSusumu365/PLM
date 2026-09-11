# PLM-L1 v0.13

未確定な依存関係の保持と追加教師の能動選択。

学習例に矛盾しない最大3特徴の依存候補を保持し、未観測の組合せを未確定のまま残す。候補の違いや未観測部分に基づいて追加教師を求め、回答を受け取った後に候補とSS記憶を再学習する。

これは独立した構造化記憶部品の実証。前版の日本語読解・生成器を置換するものではなく、全SS化・P1/S1接続・一般的な未知規則発見を実現したものでもない。

## 実行環境と検証

Windows / Python 3.12.14 / NumPy 2.3.5。配布フォルダ内で実行する。

```powershell
python -m pip install -r requirements.txt
$env:OPENBLAS_NUM_THREADS='1'
$env:PYTHONIOENCODING='utf-8'
python -B -m unittest discover -s tests -v
python -B verify_release.py --mode strict --out ../v013-check
python -B evaluate.py --out ../v013-rerun
```

出力先は配布物の外の未使用ディレクトリを指定する。ファイルを上書きしない。係数許容差と離散的機能の比較は `--mode functional` でも実行できるが、配布・モデルのハッシュ検証を緩めるモードではない。Linux実機は未検証。

## 保存済みモデルで、学習前後を比べる

```powershell
python -B -m plm_l1_v013 query --model results/hidden-b0/model --input examples/query.json
python -B -m plm_l1_v013 query --model results/hidden-b1/model --input examples/query.json
```

最初は学習不足による保留、後者は追加教師一件後の回答になる同じ入力。全16教師後の `hidden-b16/model` も同梱する。実際の例と期待出力は `examples/EXPECTED.json` を参照。保留・拒否・追加要求不能はCLI終了コード2で、`value=null`は否定ラベルではない。

## 追加教師を選び、一件だけ教える

```powershell
python -B -m plm_l1_v013 select --model results/hidden-b0/model --pool examples/pool.json --strategy active --seed acquisition-0 --out ../request.json
```

要求には選んだ文脈と診断値が入り、正解は入らない。教師が返すべきラベルを確認し、次の `LABEL_FROM_TEACHER` をそのラベルへ置き換える。

```powershell
python -B -m plm_l1_v013 teach --session results/hidden-b0 --request ../request.json --label LABEL_FROM_TEACHER --out ../after-one-teacher
```

この教材の最初の要求に対する教師回答例は `examples/EXPECTED.json` に分離してある。これはデモ用の人工教師回答で、選択器へ渡すファイルではない。実運用では利用者・教師が答えを与える。古い要求の使い回し、要求の改変、ラベル在庫外の答えは拒否する。

## 自分の教師対で開始する

初期教師は `{"context": {...}, "label": "..."}` の配列。未ラベルプールは `{"id": "...", "context": {...}}` の配列で、初期教師と重複しない完全な文脈を指定する。評価用データファイル全体は渡さない。

```powershell
python -B -m plm_l1_v013 start --train ../initial.json --pool ../unlabeled.json --retention all --backend ss --dimension 2048 --seed evaluation-0 --out ../session0
```

`--retention minimal`は早期に最小の依存へ絞る比較対照、`--strategy random`は教師選択の対照。`--backend exact`は同じ教師から作る通常の対応記憶との比較。既定は全整合候補の保持とSS照会。

## 内容

- `SPEC.md`：仮説範囲、SS記憶、保留・教師要求・再学習の契約。
- `REPORT.md`：正答・誤確定・保留、教師効率、容量・時間、残る限界。
- `plm_l1_v013/`：実装。予測器と学習／教師管理を分離。
- `data/`：開発／最終評価データ。教師役の回答と最終正解は評価側専用。
- `evaluation/PROTOCOL.json` / `SOURCE_FREEZE.json`：事前固定条件とハッシュ。
- `results/EVALUATION.json`：全取得過程、教師要求・回答、各予算時点の全評価結果。
- `results/PERFORMANCE.json`：環境と所要時間。結果digestから分離。
- `results/hidden-b0,b1,b4,b16`、`roles-b16`：セッションとモデル。
- `verification/`：新旧テスト、隔離再学習、再現性、集計・費用。
- `vendor/PLM-L1-v0.12.zip`：無改変の前版。旧版資料・コードも入れ子で保持。

SS記憶の相関値や選択スコアは確率ではない。候補の列挙・整合性検査・教師管理は通常処理であり、SSだけで全てを実装したという意味ではない。未知の依存が最大3特徴の仮説範囲を越える場合などには、誤りや学習停止が残り得る。既存文章系・数値のみの意味不足判定・P1/S1は未接続。`eligible_for_inference=false`を維持する。
