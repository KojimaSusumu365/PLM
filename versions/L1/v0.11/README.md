# PLM-L1 v0.11

加算・結合型SS連想学習と部分観測の比較実証。

v0.10の言語系は変更せず、**独立した連想記憶モジュール**で表現方式×特徴選択×SS／記号的対照を比較する。新しい文章読解器・生成器、脳のシミュレータ、P1/S1接続済みシステムではない。

## 内容

- `REPORT.md`：成績、誤確定、保留、費用、採用判断。
- `SPEC.md`：表現・学習・選択・受理・部分観測の仕様。
- `plm_l1_v011/`：実行コード。NumPy以外の依存なし。
- `data/`：開発／本評価データ。完備化oracleは評価専用。
- `evaluation/PROTOCOL.json` / `SOURCE_FREEZE.json`：評価前に固定した条件とソース・データハッシュ。
- `results/EVALUATION.json`：各照会の予測と正答・誤答・保留、全候補の値、選択監査、同数回答の比較。
- `results/PERFORMANCE.json`：環境・所要時間。固定結果digestとは分離。
- `results/roles`、`ambiguity-before`、`ambiguity-after`：保存モデル。
- `verification/`：再現性、旧版回帰、隔離実行、集計。
- `vendor/PLM-L1-v0.10.zip`：無改変の旧版。旧L1版群のコード・資料も内包する。

## 実行

Python 3.12.14 / NumPy 2.3.5 / Windowsで検証。配布フォルダ内で実行する。

```powershell
python -m pip install -r requirements.txt
$env:OPENBLAS_NUM_THREADS='1'
$env:PYTHONIOENCODING='utf-8'
python -B -m unittest discover -s tests -v
python -B verify_release.py --mode strict --out ../v011-check
python -B evaluate.py --out ../v011-rerun
```

出力先は未使用のディレクトリ／ファイルを指定する。配布物を上書きしない。検証先は配布ディレクトリ外にする。環境間の係数許容差と離散的機能比較には `--mode functional` を用いる。ただし配布ファイルと数値パケットのモデル指紋はどちらのモードでも厳密照合する。

## 小さな照会

同梱の `examples/context.json` を利用できる。内容は次の構造化文脈であり、日本語の自由文ではない。

```json
{"first_name":"太郎","second_name":"花子","order":"object_first","style0":"0","style1":"0","style2":"0"}
```

```powershell
python -B -m plm_l1_v011 query --model results/roles --input examples/context.json
python -B -m plm_l1_v011 encode --model results/roles --input examples/context.json --out ../packet.json
python -B -m plm_l1_v011 observe --input ../packet.json --fraction 0.5 --seed mask-0 --out ../observed.json
python -B -m plm_l1_v011 decode --model results/roles --input ../observed.json
```

出力ラベルの正解は `subject:花子|object:太郎`。観測を減らした後に正解を確定できる保証はない。`status=abstain` / `value=null` は保留で、CLI終了コードは2。`encode`は明示入力を数値化するだけで、真実性を確認する操作ではない。

学習には `(context, label)` のJSON配列を三つ用意する。`data/evaluation.json` 全体を学習器へ渡さない。

```powershell
python -B -m plm_l1_v011 train --train ../train.json --selection ../selection.json --calibration ../calibration.json --representation hybrid3 --selector validation --dimension 2048 --seed evaluation-0 --out ../trained
```

`--representation`は `additive / product / hybrid3`、`--selector`は `off / validation`、`--backend`は `ss / exact`。exactは同じ項の明示的な記号カーネルであり、数値信号の部分観測パケットは使わない。

## 境界

初期の特徴項目、符号帳生成、クラス管理、候補選択・全候補一致、経験的閾値調整は通常処理。教師付きクラス平均のSS型記憶であり、全SS学習・特徴の自律発見とはしない。学習中の頻度は保持するが、クラスサイズで正規化するため事前確率を学習したわけではない。

部分的な意味情報で複数の正解が成立するとき、どれか一つへ偶然当たっても正答扱いしない。外部から与える観測マスクと、符号内部のゼロ／沈黙も区別する。`eligible_for_inference=false` を維持。v0.10の過剰保留、量子化・疎化・STDP・スパイク化、P1/S1通信統合、Linux実機検証は今回の範囲外。
