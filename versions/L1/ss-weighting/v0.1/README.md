# SS記憶の重み付け・比較試験 v0.1

PLM-L1 v0.13を保存したまま作成した独立試験版。正式なv0.14や既存言語コアの置換ではない。

同じ教師・同じSS符号・同じ複素重み配列サイズで、均等加算、正の個別重み学習、符号付き補正学習を比較する。未知の依存候補を重みで削除せず、v0.13の候補保持・部分入力受理規約は元のコードをそのまま利用する。

## 実行

Windows / Python 3.12.14 / NumPy 2.3.5で検証。配布ディレクトリに移動し、出力先は未使用のディレクトリを指定する。

```powershell
python -m pip install -r requirements.txt
$env:OPENBLAS_NUM_THREADS='1'
$env:PYTHONIOENCODING='utf-8'
python -B -m unittest discover -s tests -v
python -B verify_release.py --out ../weight-check
python -B evaluate_weights.py --out ../weight-rerun
```

全試験のスコアは `results/SCORES.npz`、集計前の指標と条件は `results/EVALUATION.json`、計時は `results/PERFORMANCE.json`。結果digestから計時を除いて二回照合する。詳細は `REPORT.md`。

## 自分の記憶を試す

教師ファイルは `[{"context":{"field":"value", ...}, "label":"class"}, ...]`。全教師の項目名を揃え、2〜16ラベルを含める。同じ完全キーの重複は除去し、異なるラベルの重複は拒否する。照会ファイルはラベルなしの完全文脈の配列。

```powershell
python -B -m ss_weighting train --input teachers.json --method positive --dimension 128 --out ../weighted-model
python -B -m ss_weighting query --model ../weighted-model --input queries.json
```

`uniform` は均等加算、`positive` は正の個別重み、`residual` は他クラスへの負の補正も許す学習。保留を含むqueryは終了コード2。未登録キーにも相関が生じ得るので、最大スコアを無条件で採用しない。閾値0.5以上のラベルがちょうど一つだけの場合に部品として受理するが、安全保証ではない。

## 学習式と制約

各教師キーの位相積符号を行とするB、正解クラスのone-hot行列T、相関行列G=Re(B B*)/Dを用いる。

- uniform：H=T^T B。重複を除いた記憶を等しく加算。
- positive：クラスyの教師キー集合I_yについて、`||G[:,I_y]w-T[:,y]||² + 0.1||w-1||²`を最小化。wは0.25〜2、固定128回の射影勾配法。教師済みの他クラスを負例とするが、未観測キーを負例として教えない。
- residual：`||G A-T||² + 0.1||A-T||²`を線形方程式で最小化し、H=A^T B。全教師キーから各クラスへの符号付き寄与を許す。単なる正の重み付けより表現力が大きい。
- gain2：均等加算を一律2倍する診断用対照。正規化で均等加算へ完全に戻ることも確認する。

SS保存モデルにはHとメタデータだけを保存し、B・G・A・教師キー対応表は保存しない。学習時にはこれらの配列や通常の最適化処理を使う。全SS学習やSTDPではない。exact対照ではGが単位行列ならpositive/residualの解はTのままであることを単体テストで確認し、実行時は同じ教師の対応表を用いる。

固定閾値0.5は教師応答を1、他の教師クラス応答を0に近づける学習目標に対応させた。閾値調整による最適性能を比較したものではなく、最終データでの調整はしない。訓練損失の低下が未登録照会の安全性を保証するわけでもない。

## 試験の二つの範囲

記憶負荷試験は、4項目・各8値のキーから16／64／256件を保存し、未保存256キーを照会する。v0.13の「最大3項の依存規則」を広げたのではなく、独立した記憶バンクの負荷試験。保存済みキーの回復であり、未知規則・自然文への一般化ではない。

構造化回帰は元の16課題で、初期状態と元の均等モデルが選んだ一教師後を同じ教師条件で再学習する。候補管理・保留は元の `plm_l1_v013/core.py` を無改変で使用。新しい重み付きモデルとオンラインSessionの接続や、新たな能動教師効率の比較は実装しない。

座標欠落は観測マスクと観測数を明示する数値試験。4-bit相当は複素重みの実部・虚部を各15段階へ丸めるシミュレーションで、保存配列はcomplex128のまま。通信同期、P1/S1、量子化した実ファイル・専用回路の実装実績ではない。exactへ恣意的なSS雑音経路を加えず、SS内部の方式差と記号的対照を区別する。

全方式で `eligible_for_inference=false` を維持する。元のv0.13 ZIPは `vendor/` に無改変で同梱する。
