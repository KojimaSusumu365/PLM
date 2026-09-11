# PLM-L1-SS-active-v0.2

探索を併用した追加教師選択と訂正保持。研究用の独立実験パッケージです。`eligible_for_inference=false` を維持します。

## 本版で追加したもの

共有誤差型SS記憶の表現・更新は前版のままです。教師を求める制御に、次を追加しました。

- 探索：4回に1回、今回の取得期間ではまだ尋ねていない候補をハッシュによる無作為順で選択。
- 再確認：4回に1回の専用枠で、前回の教師から64更新以上が経過し、平均相関の上位2候補の差が0.15以上低下した項目を再度尋ねる。
- 予算管理：再確認も教師1件として数え、同じ項目は最大2回。今回の時系列では再確認は最大4件／系列。
- 途中学習：追加教師16件の後に別のD群を学習し、その状態からさらに16件の追加教師を取得。最後にE群を学習して保持を評価。

再確認の選択器は、過去の教師ラベルや真の誤りを受け取りません。通常の文脈リストと、各項目の取得回数・最後の取得ステップ・教師直後の相関差というラベルなしの台帳を使います。これは真の再発を検出できる保証ではありません。

5条件を比較します。

|方式名|探索|再確認|
|---|---|---|
|`random_once`|全件を無作為順|なし|
|`ambiguity_once`|なし、曖昧さ優先|なし|
|`mixed_once`|あり、残りは曖昧さ優先|なし|
|`ambiguity_revisit`|なし、曖昧さ優先|あり|
|`mixed_revisit`|あり、残りは曖昧さ優先|あり|

今回の数値結果、費用、限界は [REPORT.md](REPORT.md) を参照してください。v0.1とはデータと学習の時系列が異なるため、最終正解数をそのまま版間比較しないでください。

## 環境と検証

検証環境：Windows 11、Python 3.12.14、NumPy 2.3.5。Linux等は未検証。以下はこのフォルダを作業ディレクトリとしたコマンドです。出力先には未作成の名前を使用してください。

```powershell
python -m pip install -r requirements.txt
$env:OPENBLAS_NUM_THREADS='1'
$env:PYTHONIOENCODING='utf-8'
python -B -m unittest discover -s tests -v
python -B verify_release.py --out ../active2-verified
```

依存関係のインストールには、必要に応じて仮想環境を使用してください。検証器は出力先を新規作成します。マニフェスト検査を壊さないよう、出力先は配布フォルダ外に指定してください。

## 実際に選択された再確認を1件実行

```powershell
python -B -m ss_active ask --session examples/before-revisit --out ../my-active2-request.json
python -B -m ss_active teach --session examples/before-revisit --request ../my-active2-request.json --feedback examples/feedback.json --out ../my-active2-updated
python -B -m ss_active query --model ../my-active2-updated/learner/model --input examples/queries.json
```

`examples/before-revisit` は本評価で再確認が実際に選ばれた直前の状態です。`examples/feedback.json` は、その人工ケースについての外部教師例です。更新後の指紋・予測は `examples/EXPECTED.json` に記録しています。任意の要求にこの回答を使い回すことはできません。予測が未受理を含む場合、`query` は終了コード2を返します。

外部教師の回答形式は次のとおりです。

```json
{
  "schema": "plm-ss-active2-feedback",
  "request_id": "実際の要求ID",
  "source": "external_teacher",
  "label": "0"
}
```

ラベルは教師が確認した `"0"`～`"3"` のいずれかとします。`source` は宣言であって本人性・正確性の認証ではありません。古い要求、改変された要求、`source=model_prediction` の擬似教師は拒否します。

## 教師なしで候補を選択

```powershell
python -B -m ss_active export --session examples/before-revisit --out ../my-active2-selection-state.json
python -B -m ss_active select --model examples/before-revisit/learner/model --state ../my-active2-selection-state.json
```

ここで必要なのはモデルとラベルなし選択状態です。`learning.py`、`session.py`、評価データ、教師回答は選択時には不要です。ただし、前回の支持と経過を使うため、v0.1の単なる候補リストだけでは足りず、取得台帳が追加で必要です。状態は呼び出し側が正しく維持する前提であり、任意の台帳入力の真正性を認証するものではありません。

## 新しい取得セッションを始める

```powershell
python -B -m ss_active start --learner results/base-s128 --pool examples/pool.json --config examples/config.json --strategy mixed_revisit --seed active2-acq-0 --out ../my-active2-session
```

`pool` は既習の完全な人工文脈のリストです。各行は `id` と `context` のみ。IDは文脈から計算したSHA-256で、教師ラベル等の追加フィールドや重複文脈を拒否します。文脈は `f0`～`f3` の4項目、値は文字列 `"0"`～`"7"` です。

途中に候補外の教師を提示するには、`background-ask --session ... --input ... --out ...` と `background-teach --session ... --request ... --feedback ... --out ...` を使用します。入力文脈JSONはリストではなく文脈1件です。候補内の文脈をこの経路で無料で教えることはできません。背景教師は別に数え、SS学習のステップと再確認の経過に反映します。

## 本評価の再実行

```powershell
python -B evaluate.py --out ../active2-rerun
```

320取得系列、157,696教師提示を実行します。本配布では同じ条件で2回実行し、`PERFORMANCE.json` を除く260結果ファイル・保存状態の一致を確認します。時間は環境で変動します。

開発用80系列は本評価と別のシードです。4候補から設定を選ぶ規則を事前に固定し、開発結果から設定を選択した後に本評価用の凍結を行います。`evaluation/SELECTED.json` に全候補の開発評価値を残します。既存配布物に対してデータ生成・設定選択・集計スクリプトを再実行すると既存出力を上書きせず拒否します。これらは初回作成用で、通常の再検証は `verify_release.py` を使います。

## ファイル案内

|場所|内容|
|---|---|
|`ss_multicode/`|前版からバイト不変のSS表現・共有誤差更新コア4ファイル|
|`ss_active/base_selection.py`|前版からバイト不変の文脈ID・候補検査・相関診断の補助コード|
|`ss_active/selection.py`, `session.py`, `__main__.py`|探索・再確認、教師取引、背景学習、保存、CLI|
|`evaluation/PROTOCOL.json`|比較条件・開発選定規則・限界の事前定義|
|`evaluation/DEVELOPMENT_INPUTS.json`, `FREEZE.json`, `SELECTED.json`|開発前ロック、本評価前凍結、開発からの設定選定|
|`data/CASES.json`, `evaluation/cases.py`|生成済みの人工ケースと再生成コード|
|`evaluate.py`, `evaluation/metrics.py`|取得・途中学習・最終保持の評価|
|`results/`|全要求・教師応答・指標、生相関配列、代表66モデル・状態|
|`tests/`, `verify_release.py`|62単体試験、再計算・隔離再学習・教師なし実行検証|
|`verification/SUMMARY.json`|全条件・全測定時点の集計、対応比較、教師なし対照|
|`verification/BENCHMARK.json`|同じ条件での選択・回答・背景学習の実測時間と状態量|
|`verification/development/`, `previous/`, `isolation/`|開発評価、前版再検証、新版隔離検証の証拠|
|`verification/REPEATABILITY.json`, `PRESERVATION.json`|二重実行一致、旧成果物の保全確認|
|`examples/`|実際の再確認から作った実行例と期待結果|
|`vendor/PLM-L1-SS-active-v0.1.zip`|前版ZIPそのもの。さらに前の資料も元の内包構造のまま保存|

自然文の読解・生成、部分観測、依存関係探索、P1/S1との接続は本版の対象外です。SS記憶以外の候補管理・台帳・教師取引・評価は通常のPython/JSONであり、制御を含むすべてをSS信号で実装したという意味ではありません。
