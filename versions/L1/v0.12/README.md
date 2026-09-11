# PLM-L1 v0.12

学習済み記憶による意味的十分性判定と誤確定抑制。

v0.11の独立連想記憶に、**「残る情報だけで、この答えを確定してよいか」**を調べる拒否ゲートを追加する。新しい日本語読解・生成器ではなく、項目化された文脈のための部品。v0.10の言語系とv0.11の元コードは変更していない。

## 使い方

Windows / Python 3.12.14 / NumPy 2.3.5で検証。配布フォルダ内で実行する。

```powershell
python -m pip install -r requirements.txt
$env:OPENBLAS_NUM_THREADS='1'
$env:PYTHONIOENCODING='utf-8'
python -B -m unittest discover -s tests -v
python -B -m plm_l1_v012 query --model results/and2 --input examples/sufficient.json
python -B -m plm_l1_v012 query --model results/and2 --input examples/ambiguous.json
```

一つ目は残る情報で一意に決まる例、二つ目は補い方で答えが変わる例。`status=abstain`・`value=null`は保留でCLI終了コード2。入力は自然文ではなく、観測できた特徴名と値のJSON辞書。未知の項目や学習語彙にない値は拒否する。

既定は新方式 `completion`。比較用に `--policy baseline`（v0.11）、`observed_only`（必要な選択特徴が一つでも欠けると保留）、`consensus_only`（補完一致のみ、裏付け記憶を検査しない）も指定できる。比較モードを安全な既定の代わりとみなさない。

```powershell
python -B verify_release.py --mode strict --out ../v012-check
python -B evaluate.py --out ../v012-rerun
```

検証・再実行の出力先は配布物の外の未使用ディレクトリを指定する。係数許容差と離散的機能を検査するモードは `--mode functional`。ファイルハッシュと保存モデルの指紋はどちらでも厳密照合する。Linux実機は未検証。

## 学習

訓練・選択検証・calibrationは、各々 `{"context": {...}, "label": "..."}` のJSON配列で渡す。評価用データ全体や完備化表を渡さない。

```powershell
python -B -m plm_l1_v012 train --train ../train.json --selection ../selection.json --calibration ../calibration.json --representation hybrid3 --selector validation --backend ss --dimension 2048 --seed evaluation-0 --out ../new-model
```

v0.11と同じ基礎モデルを学習・調整した後、訓練例だけから候補ごとの「完全な選択キーとラベル」の裏付け記憶を作る。部分入力への正解教師や評価oracleから安全規則を教えてはいない。

## 配布内容

- `SPEC.md`：数式、補完、受理規約、通常処理とSS処理の境界。
- `REPORT.md`：全体結果、改善・損失・残る誤確定と費用。
- `plm_l1_v012/`：追加コード。`plm_l1_v011/`は無改変の基礎実装。
- `data/`：旧版回帰データ、新しい分割、開発データ。真の完備化表は評価専用。
- `evaluation/PROTOCOL.json` / `SOURCE_FREEZE.json`：本評価前の固定条件とハッシュ。
- `results/EVALUATION.json`：全照会、各ポリシーの値・保留理由・裏付け診断、会計、対照。
- `results/PERFORMANCE.json`：実行環境と所要時間。数値結果digestから分離。
- `results/and2`・`roles`・`ambiguity-before`・`ambiguity-after`：保存モデル。
- `verification/`：新旧テスト、隔離再学習、再現性、費用・集計。
- `vendor/PLM-L1-v0.11.zip`：無改変の前版。旧L1版群の資料・コードも入れ子で内包。

## 安全範囲

これは**学習した特徴依存と語彙範囲内での整合性検査**で、真実性の一般保証ではない。選択器が未知の依存関係を見落とした場合は、全候補・全補完が一致していても誤る。SS裏付け記憶にも有限次元の干渉がある。

補完列挙、学習語彙、候補管理、閾値、全体一致の制御は通常のPython。全SS学習やSS独自の優位性は主張しない。今回のゲートは観測特徴を明示的に受け取るため、原文・文脈なしの数値信号だけで意味欠落を判断できる実装ではない。既存v0.11の数値復号器だけを直接使うと、この新ゲートを通らない。P1/S1通信統合・量子化・疎化・R1推論開放は行わず、`eligible_for_inference=false`を維持する。
