# PLM-L1 v0.9 — レビュー是正とSS型特徴選択の最小実証

SS/VSA型の位相記憶を**特徴集合の採否判定にも使う**最小実装です。v0.8の二事象・時間関係の読み書きを維持し、一事象の特徴選択をID3から新しいSS型選択器へ切り替えました。

これは制御文法・初期語彙・設計済み特徴に基づく教師ありの小規模実証です。全SS学習、自然言語一般の理解、SS独自の性能優位性を意味しません。`eligible_for_inference=false` を維持します。

## 読む順序

1. `REPORT.md` — 実測結果、失敗例、判定、次の課題。
2. `SPEC.md` — SSで行う演算と、通常処理・設計として残る部分。
3. `REVIEW_CORRECTIONS.md` — レビュー指摘への対応と未解決点。
4. `results/EVALUATION.json` — 全条件の数値結果・候補マスクの成績。
5. `results/PERFORMANCE.json` — 実行時間と環境依存の所有メモリ測定。
6. `verification/` — 同一性、回帰、隔離CLI、再実行に関する証跡。

## 起動

Python 3.12.14 / NumPy 2.3.5 / Windowsで検証しています。以下は展開した `PLM-L1-v0.9` ディレクトリで実行します。Pythonコマンドが別名の場合は読み替えてください。

```powershell
python -m pip install -r requirements.txt
$env:OPENBLAS_NUM_THREADS='1'
$env:PYTHONIOENCODING='utf-8'
python -B -m plm_l1_v09 read --model results/model --text '太郎が花子を助けた。その後、花子が健太を褒めた。' --out ../packet-v09.json
python -B -m plm_l1_v09 generate --model results/model --packet ../packet-v09.json --order reverse --goals object subject
```

出力例：`健太を花子が褒めた。その前に、太郎が花子を助けた。`
提示順を反転し、出来事の先後を保持します。生成器へ渡すのは数値パケットと出力順指定であり、原文ではありません。出力ファイルが既にある場合は上書きせず停止します。

## 再学習・検証

```powershell
python -B -m plm_l1_v09 train --component-pairs data/component_train.json --temporal-pairs data/temporal_train.json --lexicon data/lexicon.json --seed temporal-evaluation-0 --selection-seed selection-evaluation-0 --selector ss --out ../v09-trained
python -B -m unittest discover -s tests -v
python -B verify_release.py --mode strict --out ../v09-check-strict
python -B verify_release.py --mode functional --out ../v09-check-functional
python -B evaluate.py --out ../v09-rerun
```

すべて新規の出力先を指定してください。配布物内への検証出力は完全性検査を壊すため、`verify_release.py` は配布物外の出力先を要求します。

- `strict`：配布ファイルのハッシュ、再学習モデルの厳密指紋、機能を確認。
- `functional`：配布ファイルのハッシュは厳密に確認。再学習はメタデータ・ブロックヘッダ一致、係数の `atol=rtol=1e-12`、読解・生成・保留の完全一致で別に判定。ハッシュを丸めて代用しません。
- 両モードとも保存モデルとパケットの指紋照合は厳密なままです。異なるモデルのパケットは流用できません。
- `--legacy` を加えると、同梱v0.8 ZIPを短い一時パスに実展開し、旧441テストと旧CLI検証も実行します。旧版は凍結されたままなので、旧版固有の環境依存の厳密指紋検査も残っています。Linuxでは新しい `functional` 検証と旧版 `--legacy` 検証を区別してください。

`evaluate.py` は新しい合成依存課題と既存言語課題を再評価します。v0.8の全低次元・通信雑音試験を再実行するコマンドではありません。SS選択の比較は `--selector symbolic / id3 / full` に切替可能です。

## 内容

`plm_l1_v09/selection.py` が新選択器、`component/` が一事象の学習・位相記憶・読み書き、直下の `training.py / runtime.py / codec.py` が二事象の時間関係層です。`thresholds.py` は現行版の共通閾値、`portability.py` は評価用の機能互換比較です。`evaluation/` は学習器・運用時処理から参照しない採点器です。

旧版は `vendor/PLM-L1-v0.8.zip` にそのまま保存しました。そこにv0.1〜v0.7のコード・資料・結果も含まれます。Windowsのパス長制約を避けるため、v0.9の実行時に深い旧版ディレクトリを入れ子展開する構成にはしていません。

## 今回開放しない機能

三事象以上、照応・省略、未知自然文、因果・一般時間論理、記憶負荷の偏り対策、学習からの特徴そのものの発見、P1の数値部分観測、S1のチップ列・パイロット同期との接続、R1推論・Concept更新は対象外です。

Linuxでの実機検証は未実施です。別ディレクトリでの隔離試験や微小係数摂動の試験を、異なるOSでの実行実績とは呼びません。
