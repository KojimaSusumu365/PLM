# PLM-L1-SS-active-v0.1

共有誤差更新とSS照合に基づく、追加教師の能動選択。研究用の独立実験パッケージです。自然言語システムへの統合版ではなく、`eligible_for_inference=false` を維持します。

## 内容

学習済みのSS重畳記憶に対し、既習の候補文脈から「もう一度、外部教師に正解を尋ねる項目」を選び、回答1件ごとに共通残差で更新します。選択器は正解表を受け取りません。外部教師はこの人工実験では評価用正解から回答しますが、予測を教師に変換する自己学習は行いません。

- `random`：SSスコアに依存しない固定ハッシュ順。
- `ambiguity`：4符号の平均相関の上位2候補の差が小さい順。
- `disagreement`：4符号それぞれの最有力候補の不一致が大きい順。

全方式で同じ512次元相当の共有誤差型SS記憶、同じ教師予算、同じ受理規則を使用します。能動選択は全残候補の照合を必要とするため、無作為方式と計算量は同一ではありません。

詳細な結果・制約・次段階は [REPORT.md](REPORT.md) に記載します。

## 動作環境

検証環境は Windows 11、Python 3.12.14、NumPy 2.3.5。Linux等は未検証です。以下のコマンドは本フォルダを作業ディレクトリとします。書き込み先のファイル・フォルダは未作成の名前を指定してください。

```powershell
python -m pip install -r requirements.txt
$env:OPENBLAS_NUM_THREADS='1'
$env:PYTHONIOENCODING='utf-8'
python -B -m unittest discover -s tests -v
python -B verify_release.py --out ../verified-local
```

同封環境に合わせた依存関係指定です。上記インストールは利用者のPython環境を変更するため、必要に応じて仮想環境を使用してください。

## 教師1件による更新の例

```powershell
python -B -m ss_active ask --session results/s128-disagreement-b0 --out my-request.json
python -B -m ss_active teach --session results/s128-disagreement-b0 --request my-request.json --feedback examples/feedback.json --out my-updated-session
python -B -m ss_active query --model my-updated-session/learner/model --input examples/queries.json
```

この例の `examples/feedback.json` は同封の人工データに対する固定された外部教師例です。任意の新しい要求に使い回せません。更新後の指紋と予測は `examples/EXPECTED.json` と一致します。`query` の終了コード2は少なくとも1件の未受理を含む場合にも返ります。

実利用時には `ask` の要求を外部教師に渡し、その教師から以下の形式で回答を受けます。`request_id` は実際の要求に一致させ、`label` は教師が確認した `"0"`～`"3"` のいずれかとします。

```json
{
  "schema": "plm-ss-active-feedback-01",
  "request_id": "要求から取得した実際のID",
  "source": "external_teacher",
  "label": "0"
}
```

`source` は形式上の宣言であり、教師の本人性・正確性を認証する仕組みではありません。古い要求、選ばれていない要求への改変、`source=model_prediction` の回答は拒否します。

## 教師情報なしで候補を選択

```powershell
python -B -m ss_active select --model results/s128-disagreement-b0/learner/model --pool examples/pool.json --strategy disagreement --seed active-acq-0 --index 0
```

`select` はSSモデルとラベルなし候補だけで動きます。教師回答、評価正解、逐次学習器、セッション履歴は不要です。候補の各行は `id` と `context` のみで、IDは文脈のみから計算したSHA-256です。正解ラベル等の追加フィールド、重複文脈、不正なIDは拒否します。

## 再評価

```powershell
python -B evaluate.py --out ../rerun-results
```

192取得系列・172,032教師提示を再実行します。基礎学習16本を条件間で共有し、各取得系列に32件の追加教師と、予算0/4/16/32ごとの独立した後続学習分岐を含みます。`PERFORMANCE.json` は時間測定のため一致対象外です。他の結果ファイル・保存状態は本リリースでは二重実行で一致を検査します。

配布物の `evaluation/FREEZE.json` はソース・試験・条件・データの固定記録です。`RELEASE_MANIFEST.json` は配布ファイルの検査用です。検証・再評価の出力先を配布フォルダ内に作ると配布物のファイル集合が増えるため、その後のマニフェスト検査には元のZIPを別の空フォルダへ展開して使用してください。完全な検証には出力先を配布フォルダ外に指定するのが確実です。

## ファイル案内

|場所|内容|
|---|---|
|`ss_active/`|選択、要求・回答取引、取得状態保存、CLI|
|`ss_multicode/`|前版からバイト不変で引き継いだSS表現・学習コア4ファイル|
|`evaluation/`, `data/`|条件固定、人工ケース生成、評価定義、生成済みデータ|
|`evaluate.py`, `verify_release.py`, `tests/`|評価実行、隔離再検証、50件の単体試験|
|`results/`|全取得要求・教師応答・指標、1,920生スコア配列、代表50モデル・状態|
|`verification/SUMMARY.json`|全予算・全条件の集計、対応条件間の差分|
|`verification/REPEATABILITY.json`|二重実行の一致したファイルとハッシュ|
|`verification/BENCHMARK.json`|取得・更新・照会の実測時間と状態量|
|`verification/development/`|本評価とは別の開発用データによる結果|
|`verification/isolation/`|新機能の隔離再学習・教師なし実行検証ログ|
|`verification/previous/`|前版の検証器を再実行した結果|
|`verification/BASELINE.json`, `PRESERVATION.json`|旧成果物の変更前ハッシュと保存確認|
|`examples/`|要求・教師回答・照会・期待結果の1件実行例|
|`vendor/PLM-L1-SS-multicode-v0.1.zip`|前版配布ZIPそのもの。内包された過去資料も元のまま|

通常の候補リスト、取得済みID、JSON取引、ラベル集合、評価正解はSS重畳で表したものではありません。本成果は「SS記憶に基づいて外部教師の取得先を選ぶ」実証であり、制御を含むすべてがSS方式になったという意味ではありません。
