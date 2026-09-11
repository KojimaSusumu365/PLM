# 複数符号SS照合による干渉誤り・未登録誤受理の低減試験

独立試験版 `PLM-L1-SS-multicode-v0.1`。前版の逐次誤差訂正学習を基礎に、独立した複数符号・コピー符号・別の入力／答え照合信号を比較する。自然言語コアの正式な置換版ではない。既存版と共通履歴を変更しない。

結果と解釈は `REPORT.md`、実行可能な検証器は `verify_release.py`。

## 比較する記憶

| architecture | 構成 | 学習係数量 |
|---|---|---:|
| single128 | 128次元の読出し記憶×4ラベル | 8,192 bytes |
| single512 | 512次元の読出し記憶×4ラベル | 32,768 bytes |
| concat512 | 独立128次元×4ブロック、平均残差を共有 | 32,768 bytes |
| multi4 | 独立128次元×4系、各系の残差で更新 | 32,768 bytes |
| clone4 | 同一128次元符号のコピー×4系 | 32,768 bytes |
| checked | 独立128次元×3系と、512次元の入力×ラベル照合信号 | 32,768 bytes |
| exact | 完全キーと最新教師ラベルの対応表 | キー数に依存 |

係数はcomplex128。学習係数量が等しくても、符号キャッシュ・メタデータ・実行時間・演算数は等しくない。特にcheckedは追加の照合符号と相関演算を必要とする。exact以外に完全キー対応表を保持せず、全方式とも過去教師の再提示バッファは使わない。

`concat512` と `multi4` は同じ四系統の符号を使う。違いは更新時に全系共通の誤差を使うか、各系の誤差を使うか。concat512は、四ブロックを連結した512次元の通常の誤差訂正と数式上等価である。複数系で平均するだけでは、長い符号を超える新しい原理にならないことを確認する対照として含めた。

## 逐次更新

入力は `{"f0":"0","f1":"1","f2":"2","f3":"3"}` のような4項目の完全キー。各値は文字列0〜7、既知ラベルは文字列0〜3。項目／値の単位複素位相符号を掛け合わせてbを作る。

```text
s[k,y] = Re[conj(H[k,y]) dot b[k]] / D
target[y] = 教師ラベルなら1、他の既知ラベルなら0
H[k,y] += 0.5 * (target[y] - s[k,y]) * b[k]
```

concat512は上式のs[k,y]の代わりに四系統の平均相関を使う。

checkedの照合記憶Gはクラス別配列ではなく一本の512次元重畳信号。

```text
z[y] = 独立な入力符号 * 独立なラベル符号[y]
c[y] = Re[conj(G) dot z[y]] / 512
G += 0.5 * sum_y((target[y] - c[y]) * z[y])
```

同じ外部教師一件から、正解の入力／ラベル組に1、それ以外の既知ラベル組に0を与える。未登録キーを負例として記憶へ教えることはしない。符号化・積結合・重畳・相関に基づく照合だが、通常の誤り訂正符号の距離保証や正確な会員判定ではない。

## 回答と受理

各系の相関の平均から `tentative` を出す。上位差が1e-12以下なら未定。固定mean方式は平均相関0.5以上のラベルがちょうど一つの場合にだけ `accepted` を返す。

quorumは、各系で相関0.5以上のラベルが一つだけあり、それが平均の候補と同じ系が75%以上必要。unanimousは全系一致。pair_checkは照合記憶でも0.5以上のラベルが一つだけで、読出し候補と一致することが必要。これらの固定ゲートは候補を保留にするだけで、別のラベルに直す処理ではない。

本試験には開発データで決めた `calibrated` も含める。全方式に同じ開発データを与え、受理基準を本試験前に固定する。未登録という情報は、この受理基準の校正にのみ使う追加の検証用教師情報である。H/Gの更新には使わない。保存モデルの標準受理基準はcalibratedである。checkedのcalibratedが照合を使うかどうかも開発データで決まり、名称だけで照合を使っていると解釈しない。

相関は確率ではない。全出力は `eligible_for_inference=false`。真のラベル・未登録判定・開発評価器は予測器に含めない。

## 一件ずつ教える

Windows 11、Python 3.12.14、NumPy 2.3.5で検証。配布フォルダで実行する。出力は未使用の別名を指定する。

```powershell
python -m pip install -r requirements.txt
$env:OPENBLAS_NUM_THREADS='1'
$env:PYTHONIOENCODING='utf-8'
python -B -m ss_multicode start --architecture multi4 --out ../new-learner0
python -B -m ss_multicode question --learner ../new-learner0 --input examples/context.json --out ../new-request.json
```

教師回答は予測と別のJSONとし、作られた要求のIDを指定する。

```json
{"schema":"plm-ss-multicode-feedback-01","request_id":"要求のrequest_id","source":"external_teacher","label":"0"}
```

```powershell
python -B -m ss_multicode teach --learner ../new-learner0 --request ../new-request.json --feedback my-feedback.json --out ../new-learner1
```

`external_teacher` はAPI上の宣言であって、本人認証・正解保証ではない。モデルの予測を教師へ自動転用しない。不正形式、古い要求、未知ラベル、source=model_predictionを拒否する。元の学習状態を上書きせず、新しい学習状態へ保存する。

同梱の人工教師例で、保存済みchecked-Aから一件更新する場合：

```powershell
python -B -m ss_multicode teach --learner results/checked-A --request examples/request.json --feedback examples/feedback.json --out ../one-step
python -B -m ss_multicode query --model ../one-step/model --input examples/queries.json
```

`query` は学習器全体ではなく `model/` だけで実行する。保留を含むqueryと、不正なteachの終了コードは2。

## 再現

```powershell
python -B -m unittest discover -s tests -v
python -B verify_release.py --out ../multicode-check
python -B evaluate.py --out ../multicode-rerun
python -B calibrate.py --out ../multicode-development-rerun
```

最後のコマンドは開発校正を再現するもので、凍結済みの `evaluation/CALIBRATION.json` を上書きしない。配布済みのデータは `data/CASES.json`。生成器 `python -B -m evaluation.prepare` はデータファイルがない新規構築時専用であり、通常の再現時には実行しない。

## ファイルと未実施事項

全ソースは `ss_multicode/`・`evaluation/`・`tests/` および直下のスクリプト。`results/EVALUATION.json` は104過程の固定・校正済み方針の指標、`SCORES.npz` は全固定照会と各教師提示前後の生相関。`results/`には7構成×A後/C後/正解変更後の21保存学習器を含む。

`verification/`に開発の全候補比較、集計、各条件の対応比較、符号間の相関、時間・保存量測定、反復一致、既存版保全、分離検証を保存する。`vendor/`に前版の元ZIPをそのまま同梱する。

自然文・新語彙・部分観測・文脈を分割する記憶ルーティング・Resonatorの反復分解・脳/STDP・P1/S1同期との接続は本版で実装していない。未知の自然文への一般化ではなく、人工キーを記憶・更新・照合する限定試験である。
