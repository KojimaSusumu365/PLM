# PLM-L1 v0.10 — SS型の複数候補保持と誤確定抑制

読み方・書き方の候補を独立したSS/VSA型の位相記憶として保持し、**候補ごとの完全な意味・生成文が一致しなければ保留する**最小実装です。候補を区別する追加例によって再学習し、保留から正しい生成へ移る実験を含みます。

候補の列挙、検証損失の集計、候補ID管理、一致判定は通常のPython/NumPy処理です。全SS学習、SS独自の性能優位性、正解確率の保証を主張しません。`eligible_for_inference=false` を維持します。

## 内容

- `REPORT.md`：本評価の結果、失敗・保留・費用、到達点。
- `SPEC.md`：候補選択、上限、受理、再学習、信号契約。
- `evaluation/PROTOCOL.json`：本評価前に固定した条件。
- `results/EVALUATION.json`：全条件、各照会の予測、候補・相関に基づく判断、回答率と誤答率。
- `results/PERFORMANCE.json`：主評価中の実行時間・環境。時間値は固定結果digestから分離。
- `results/model`：標準の二事象モデル。
- `results/ambiguity-before` / `results/ambiguity-after`：曖昧な学習例だけのモデルと、区別する2例を追加したモデル。
- `verification/`：旧版検証、再現性、配布前の隔離検証など。
- `vendor/PLM-L1-v0.9.zip`：旧版を無改変で同梱。さらに旧v0.8〜v0.1とレビュー資料を含む。

## 起動

Python 3.12.14 / NumPy 2.3.5 / Windowsで検証。以下は展開した `PLM-L1-v0.10` で実行します。

```powershell
python -m pip install -r requirements.txt
$env:OPENBLAS_NUM_THREADS='1'
$env:PYTHONIOENCODING='utf-8'
python -B -m plm_l1_v010 read --model results/model --text '太郎が花子を助けた。その後、花子が健太を褒めた。' --out ../packet-v010.json
python -B -m plm_l1_v010 generate --model results/model --packet ../packet-v010.json --order reverse --goals object subject
```

期待する生成：`健太を花子が褒めた。その前に、太郎が花子を助けた。`

生成器へ渡すのは数値パケットと出力指定だけです。候補監査に別々の候補文が出る場合があっても、`status=abstain` のトップレベル `text` は `null` で、確定した文として採用しません。

## 再学習

```powershell
python -B -m plm_l1_v010 train --component-pairs data/component_train.json --selection-pairs data/single_development.json --temporal-pairs data/temporal_train.json --lexicon data/lexicon.json --selection-seed candidate-evaluation-0 --method ss_multi --out ../v010-trained
```

`selection-pairs` も意味ラベル付きの教師情報です。標準は432学習対＋192候補選択用検証対＋216時間学習対と初期語彙を使います。「432対だけで学習」とは数えません。追加例による更新はコーパスに例を追加して新しいディレクトリへ**オフライン再学習**します。運用時の自律学習・例の自動収集ではありません。

比較には `--method symbolic_multi`、`ss_single`、`v09_single` を指定できます。`ss_single` は同じ検証データと候補選択を使って第一候補だけを採用する対照です。`v09_single` はv0.9の訓練内完全回復規則を使う対照で、候補選択用検証ラベルを使いません。

## 検証

```powershell
python -B -m unittest discover -s tests -v
python -B verify_release.py --mode strict --out ../v010-check-strict
python -B verify_release.py --mode functional --out ../v010-check-functional
python -B evaluate.py --out ../v010-rerun
```

必ず未使用の出力先を指定します。既存モデルや配布物を上書きしません。検証出力は配布ディレクトリ外に置きます。

- `strict` は再学習指紋も厳密一致を要求。
- `functional` は配布物ハッシュを厳密確認したうえで、再学習のメタデータ・候補構成・係数許容差・離散的な読解/生成/保留の一致を別に検査。
- `--legacy` を加えると、旧ZIPを短い一時パスへ展開して旧版自身の検証も実行。旧版の全数値評価をやり直すコマンドではありません。
- 異なるモデル・追加学習後のモデルに、古いモデルのパケットを流用することはできません。モデル指紋の照合は厳密なままです。

## 限界

候補は1記憶あたり最大4つ。文章モデルでは各部品候補の組合せも数え、4つを超える場合は4つを診断用に保持しても確定を拒否します。無制限の仮説探索ではありません。

候補の一致は外部の意味的正しさを保証しません。別データでの受理閾値の調整も有限標本上の経験的なものです。相関値や候補の一致率を、そのまま正解確率とは呼びません。

Linuxでの実機実行は未実施。三事象以上、未知自然文、照応・省略、P1数値部分観測/S1チップ・同期接続、R1推論・Concept更新は今回開放しません。
