# PLM-L1-SS-core v0.3

SS化境界の監査と、読解・生成の時間波形SSコアへの統合。

**限定二事象文の実証。まだ「ほぼ全SS」でも自由な日本語生成でもない。** 学習済み言語連想の照合、意味信号の復元、生成行動／次状態の照合を、共通のチップ逐次受信器で実行する。文の分割、特徴設計、意味辞書、行動解釈器などの通常処理は残る。

## 資料

- `REPORT.md`：結果と実際の文章例。
- `BOUNDARY_AUDIT.md`：SS化した範囲／していない範囲と検証方法。
- `SPECIFICATION.md`：演算、学習、保存形式、実証条件。
- `PROTOCOL.json`：本評価前に固定した評価計画。
- `verification/`：固定ファイル、旧版保存、テスト、隔離生成、ハッシュ検証。
- `results/`：全比較、故障、状態保持、接続、保存記憶からの生成と各波形トレース。

## 実行

Python 3.12系、NumPy 2.3.5で検証。展開ディレクトリを作業ディレクトリにする。

```powershell
$env:OPENBLAS_NUM_THREADS='1'
$env:PYTHONIOENCODING='utf-8'
python -B -m ss_core_v03 --text '太郎が花子を助けた。その後、もし次郎が美咲を褒めなかったら。' --order reverse --focus object
```

出力例：

> もし美咲を次郎が褒めなかったら。その前に、花子を太郎が助けた。

CLIは生成成功で終了コード0、保留で2を返す。`program_audit` は選ばれた行動と次状態信号の指紋、`cost` は読出し窓／tick数。外部P1/S1を経由する試験は別に評価スクリプト内で実行する。このCLIだけで外部伝送試験まで行ったと解釈しない。

保存済み `model/` と `programs/` が同梱されている。通常実行時に再学習はしない。`build_programs.py` は教師対応の転写学習用で、既存 `programs/` を上書きしない。再学習検証は検証スクリプトがメモリ上で行う。

## 再検証

```powershell
python -B -m unittest discover -s tests -v
python -B evaluate03.py --output C:/path/to/new-wave03-results
python -B verification/check03.py --output C:/path/to/new-wave03-verification --repeat C:/path/to/new-wave03-results
```

出力先はまだ存在しない新規ディレクトリを指定する。最終リリース内の結果や保存物を上書きしない。検証は元の前版がなくても実行可能。前版も隣にある場合だけ `--previous` を指定すると、前版全ファイルとZIPの不変性も調べる。

旧パッケージは比較・既存訂正機構・外部P1/S1接続のために同梱する。旧APIを直接呼べば旧配列照合へ戻る場合がある。今回の統合入口は `ss_core_v03.runtime.load/run_text`、保存訂正記憶の入口は `ss_core_v03.correction.generate_saved`。

## 変更しなかったもの

旧学習済み言語モデル、P1/S1実装、v0.2の更新検査方式・保留台帳。過去の共通破損、外部S1で残った保留条件、自由文法・未知語の問題が解決した版ではない。
