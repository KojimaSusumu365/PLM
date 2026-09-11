# PLM-L1-SS-doc v0.5

「SS記憶の不確実性に応じた再確認と誤生成抑制」

v0.4の複数訂正記憶に、SS照合の根拠が足りない場合や入力と矛盾する場合に再確認を求める対話状態を追加した、限定短文書の実証実装です。推測した値を教師として学習することはありません。外部回答がなければ生成を保留します。

## まず読む資料

- [実測結果と限界](REPORT.md)
- [設計・SS演算・制御境界](SPECIFICATION.md)
- [検証範囲](verification/VALIDATION.md)
- [機械可読集計](verification/SUMMARY.json)
- [実際の質問・回答・生成例](examples/run/DEMO.json)

## 実行

PythonとNumPyが必要です。検証環境の実際のバージョンは [ENVIRONMENT.json](verification/ENVIRONMENT.json)、固定依存は [requirements.txt](requirements.txt) に記録しています。以下は展開したリリースフォルダをカレントディレクトリにしたPowerShellの例です。`python`はご自身のPythonに置き換えられます。

```powershell
$env:OPENBLAS_NUM_THREADS='1'
$env:PYTHONIOENCODING='utf-8'
python -B -m unittest discover -s tests -v
python -B examples/demo.py --out ../my-demo
python -B -m ss_reconfirm plan --model model --memory ../my-demo/before-memory --session ../my-demo/before-session.json
python -B -m ss_reconfirm confirm --model model --memory ../my-demo/before-memory --session ../my-demo/before-session.json --answer ../my-demo/answer.json --out ../my-confirmed.json --memory-out ../my-confirmed-memory
python -B -m ss_reconfirm generate --model model --memory ../my-confirmed-memory --session ../my-confirmed.json
```

`plan`が再確認を要求すると終了コードは2です。これは想定動作です。`confirm`はSS記憶と新しい対話状態を保存します。既存出力は上書きしません。すべての出力先に未使用名を指定してください。

教師の答えを含まない新しい照会を、保存したSS記憶から実行する例：

```powershell
python -B -m ss_reconfirm start --model model --memory ../my-confirmed-memory --scope ../my-demo/scope.json --packet ../my-demo/cold-packet.json --out ../my-cold.json
python -B -m ss_reconfirm generate --model model --memory ../my-confirmed-memory --session ../my-cold.json
```

`cold-packet.json`では訂正対象2項目が未観測です。新しいセッションには確認済み履歴がありません。元の入力本文や教師表を再照会に渡す必要もありません。ただし、残りの意味情報、出来事ID、訂正対象の指定は必要です。

## 全評価の再実行

```powershell
python -B evaluate.py --out ../my-results
python -B verify_release.py --out ../my-verification --repeat ../my-results
```

評価は全72条件を最初から実行します。`verify_release.py`は同梱結果と再実行結果の全ファイルを比較し、保存記憶の検証と一部照会の再実行を行います。実行時間ファイルだけは一致比較から除きます。ユーザー出力をリリース内に追加すると最終マニフェスト検証に失敗するため、上記の例ではリリースの外側へ出力しています。

## 収録内容

`ss_reconfirm/`が新しい対話制御、`ss_revision/`が改訂アドレスとSS記憶、`ss_retention/`が複数符号SS照合・誤差更新です。`ss_partial/`、`ss_document/`、`plm_l1_v09/`、`model/`は既存の数値意味信号と言語モデルです。`data/`には固定データと旧失敗例、`results/`には全条件ログ・保存記憶・数値参照信号、`verification/`には監査証跡を含めています。

これは自由作文モデルではありません。2～3事象、既存語彙・文型、外部指定された最大2訂正項目の範囲です。質問の優先順位・文面・改訂管理は通常のプログラム制御であり、全部をSSだけで学習したものではありません。`eligible_for_inference: false`は評価・管理用の既存スキーマ標識であり、外部文書や評価記録を教師・実行指示として自動投入してよいという意味ではありません。
