# PLM-R1 v0.1 検証結果

R1 92件 + C2 186件 = 278件のテストが合格。skipなし。

R1内部16例とC2 v0.4開発/holdout 55例の取り込みをテスト内で確認。サブケース数は独立試験数として水増ししていません。

受入チェック 10/10。C2評価JSON完全再現: True。依存ファイルは実行前後でバイト一致。

独立意味評価は未実施。実データ・別担当者の注釈がないためmetrics=null、status=pending_inputsを維持。テスト合格は意味精度や推論利用の許可ではありません。

詳細はVERIFICATION_RESULTS.jsonと各ログ。再実行: `python -B verify_release.py`。
