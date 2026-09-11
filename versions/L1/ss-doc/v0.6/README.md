# PLM-L1-SS-doc v0.6

「後続学習下のSS意味保持と再確認先の選択学習」

SSの照合状態から再確認先を評価する、小さなSS価値記憶を追加しました。確認後に別の出来事を学習させ、回答履歴なしで以前の意味を保持して文章化できるかを評価します。

## 資料

- [結果・生成例・限界](REPORT.md)
- [実装と実験の仕様](SPECIFICATION.md)
- [コーパス構成](CORPUS.md)
- [検証範囲](verification/VALIDATION.md)
- [全条件の集計](verification/SUMMARY.json)

これは2～3事象、既存語彙・文型、文書ごとに外部指定された2訂正項目での実証です。質問文・文法の学習や自由長文生成ではありません。選択の評価値は確率ではなく、生成の受理条件を緩めません。

## 実行方法

展開したリリースフォルダで実行します。PythonとNumPyが必要です。[requirements.txt](requirements.txt) と [実測環境](verification/ENVIRONMENT.json) を参照してください。以下はPowerShellの例です。出力先は未使用名を指定し、元リリースの外へ作成します。

```powershell
$env:OPENBLAS_NUM_THREADS='1'
$env:PYTHONIOENCODING='utf-8'
python -B -m unittest discover -s tests -v
python -B examples/demo.py --out ../selection-demo
python -B -m ss_select choose --model model --memory ../selection-demo/before-memory --workset ../selection-demo/workset.json --selector data/selector_model
python -B -m ss_select confirm --model model --memory ../selection-demo/before-memory --workset ../selection-demo/workset.json --answer ../selection-demo/answer.json --out ../confirmed-memory
python -B -m ss_reconfirm start --model model --memory ../confirmed-memory --scope ../selection-demo/scope.json --packet ../selection-demo/fresh-packet.json --out ../fresh-session.json
python -B -m ss_reconfirm generate --model model --memory ../confirmed-memory --session ../fresh-session.json
```

この小例は元の記憶がすでに十分な「任意の保持確認」です。追加干渉への有効性を示す比較ではありません。実際の比較は全評価ログに分離しています。

`choose --policy rule`、`choose --policy random`も利用できます。複数回の選択では、確認した `[id,target]` の配列をJSONで外部管理し `--history` に指定します。乱数対照の順序は `--seed` と `--step` で固定します。確認履歴は値の辞書ではありません。CLIは対話状態や教師予算を自動管理するGUIではなく、個々の操作を提供します。

## 評価・学習の再現

```powershell
python -B train_selector.py --out ../selector-retrained
python -B evaluate.py --out ../evaluation-repeat
python -B verify_release.py --out ../verification-repeat --repeat ../evaluation-repeat --retrained ../selector-retrained
```

`train_selector.py`は学習用場面から576件の対比較教材を再構築してSS選択器を学習します。`evaluate.py`は固定済み選択器で全108条件を評価します。`verify_release.py`は全ファイル一致、選択・回答・後続学習の再実行、一部文書の再生成、最小ランタイムでの推論分離を検証します。時間測定ファイルだけは一致比較から除きます。

出力をリリース内に追加すると最終マニフェストとの一致検証に失敗するため、上の例のように別フォルダを使ってください。ファイルの上書きや既存結果の削除は行いません。

## 主な構成

`ss_select/`が新設の特徴化・SS価値記憶・順位選択・外部確認APIです。`ss_reconfirm/`以下はv0.5から保持した意味記憶と生成処理。`data/selector_model/`が学習済み選択器、`training_results/`がその学習教材・教師・結果、`results/`が全評価と保存SS記憶です。評価用の正解表を選択器や生成器へ読み込ませません。
