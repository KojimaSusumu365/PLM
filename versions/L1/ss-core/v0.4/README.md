# PLM-L1-SS-core v0.4

SS意味ワーキングメモリによる役割参照・局所更新・生成の直結。

読解後の意味を2本の重畳信号に保持し、事象×役割の信号で参照し、指定箇所をチップ加算で訂正し、値信号から生成へ接続する限定実証です。対象の経路には意味辞書への復元を置きません。旧読解器、汎用制御、入出力境界まで全てSS化したわけではありません。

## 内容

- `REPORT.md`：実測結果、文章例、到達点と制約。
- `SPECIFICATION.md`：表現、演算、記憶、更新、生成の詳細。
- `BOUNDARY_AUDIT.md`：SS化した箇所と残る通常処理。
- `CORPUS.md` / `PROTOCOL.json`：評価範囲・事前固定条件。
- `ss_core_v04/`：今回の新しい実装。
- `ss_core_v03/` / `ss_core_v02/` / `ss_core/` 等：互換性と回帰試験のための既存実装。
- `model/` / `programs/`：既存の学習済み読解記憶・生成プログラム。
- `bundle04/`：新しい数値符号束・SS接続重み・オフライン教師報告。
- `tests/`：既存75試験と新規20試験。
- `evaluation/`：独立採点器、固定コーパス作成、評価、再現検証。
- `results/run1/` / `results/run2/`：全個票、受信窓ログ、保存WM、結果要約。
- `verification/`：ソース固定、旧版不変、隔離動作、再現性、全ファイル指紋。

同梱する旧ライブラリは今回の達成範囲を増やすためではなく、依存関係・回帰試験・監査を再現するために残しています。文書に記載する新WMの結果と旧bridgeの回帰試験を区別してください。

v0.4は新しい経路の検証用追加実装です。旧訂正ストアの永続的な訂正待ち管理、複数対象の一括トランザクション、書込みACK等の全契約を置換する完成版ではありません。旧実装の95試験中の該当試験が通ることを、新WMがそれら全機能を備える証明とは扱いません。

## 実行

Python 3.12.14 / NumPy 2.3.5 で確認。ネットワークや外部LLM/APIを使わず動作します。PowerShellで展開先を作業ディレクトリにして実行します。

```powershell
$env:OPENBLAS_NUM_THREADS = '1'
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONDONTWRITEBYTECODE = '1'
python -B -m ss_core_v04 --text '太郎が花子を助けた。その後、もし次郎が美咲を褒めなかったら。' --order reverse --focus object
```

局所訂正を同じリクエストで生成へつなぐ例：

```powershell
python -B -m ss_core_v04 --text '太郎が花子を助けた。その後、もし次郎が美咲を褒めなかったら。' --update 'event:1/subject' 'entity:花子'
```

`--update` は外部教師の明示的指定です。訂正自然文を自動解釈する機能ではありません。受理できない場合は `held`、文章なし、終了コード2になります。

## 検証・再実行

```powershell
python -B -m unittest discover -s tests -v
python -B -m evaluation.verify04 verify
python -B -m evaluation.verify04 check-manifest
python -B -m evaluation.reproduce04 --output verification/LOCAL-REPRODUCTION.json
```

最後のコマンドは、同梱run1/run2の一致、符号束の再学習再現、読解/評価データなしの隔離生成を確認し、新規検証ファイルを作成します。実行後は追加ファイルにより元の梱包manifestの完全一致検査は失敗するため、manifestは再現検証より先に実行してください。出力先は既存ファイルを上書きできません。

訂正済みWMの隔離生成だけを再確認する場合：

```powershell
python -B -c "from pathlib import Path; from evaluation.reproduce04 import cold; print(cold(Path('verification/COLD_UPDATED_INPUT')))"
```

`EXPECTED.json` は隔離プロセスの外側で出力比較にのみ用い、隔離配置にはコピーしません。訂正済みWMのこの追加確認は `event:1/subject` の1ケースであり、全12訂正を別プロセスにした成績ではありません。

評価を新規に全実行する場合：

```powershell
python -B -m evaluation.experiment04 --output results/local-run1
python -B -m evaluation.experiment04 --output results/local-run2
python -B -m evaluation.reproduce04 --run1 results/local-run1 --run2 results/local-run2 --output verification/LOCAL-NEW-RUNS.json
```

同梱結果と同じ事例単位の並列配置で2回実行する場合：

```powershell
python -B -m evaluation.parallel04 --output results/local-parallel --workers 8
python -B -m evaluation.reproduce04 --run1 results/local-parallel/run1 --run2 results/local-parallel/run2 --output verification/LOCAL-PARALLEL.json
```

並列版は各事例ごとに受信器を作り、独立したプロセスへ割り当てます。波形の時間窓内部を間引いたり、一括内積に切り替えたりはしません。`shards/` に個々の元ログを保存し、集計ファイルはそれを統合します。逐次版と並列版ではパイロットnonceの範囲が違うため、異なる実行配置間で窓ログの指紋一致を要求しないでください。

1回は80生成に加え、12訂正×訂正直後/再ロード後の生成、4種類の未確定解決、10条件の障害/位相試験を含みます。全照合をPythonでチップごとに受信するため時間がかかります。

`build04.py` は束がない新しい作業コピーでのみ使用します。通常は束を上書きせず、`evaluation.reproduce04` の一時ディレクトリによる再構築検査を使ってください。旧版の不変検査 `evaluation.verify04 preserve` は、隣に元v0.3フォルダとZIPがある開発配置でのみ実行できます。

## API境界

`Core.generate(wm, order_signal, goal_signals)` は数値信号を受け取ります。`WorkingMemory.update(address_signal, teacher_signal)` は更新状態を必ず確認してください。訂正を受理できないのに古い文章を出さない用途には `Core.revise_and_generate` を使用します。

`boundary.teacher` / `boundary.controls` は人間が指定するラベルを符号に変換する入力境界、`boundary.observe` は評価専用の診断復号器です。Coreはこれらをimportせず、`IO.json` も読みません。
