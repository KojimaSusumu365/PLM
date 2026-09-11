# PLM-P1 v0.1 — Phase符号・部分相関の最小実証とS1接続仕様

現行のPython構成で、複素位相コードによる出来事・役割・値の結合、重畳、部分観測からの相関回復を実装しました。Lisp/Prologは導入していません。既存C2/R1も変更していません。

## 今回実装したもの

- 絶対値1の複素数成分からなる、再現可能な高次元位相コード。
- 文書/出来事ID、役割、値を別々に結合。同じConceptの別個体と、主体・対象の交換を区別。
- 観測マスクを使った部分相関、雑音・位相揺らぎ・重畳の試験、曖昧時の保留。
- R1/C2の観察を取り込むアダプター。否定・仮定・隔離・訂正先を維持し、事実へ昇格しない。
- S1へのJSON信号パケット、厳格な入出力検証、正解対応表を渡さない復号CLI。
- 開発seedと評価seedを分けた数値評価、役割/出来事結合を外す比較、初回結果とソースの凍結。

まず `examples/DEMO_REPORT.md`、数値結果は `results/EVALUATION_REPORT.md`、次段階の契約は `S1_INTERFACE.md` を参照してください。

## ここでの用語

Phaseは複素位相です。処理工程のフェーズ名でも、物理発振器の実装でもありません。

部分相関は「観測できた座標だけで計算する相関」です。統計学で交絡を除く偏相関、あるいはConcept階層に共有成分を埋め込む意味相関は今回実装していません。

回復には既知の文書/出来事/役割キーと候補辞書が必要です。未知の出来事を信号から列挙する機能や、辞書にないConceptを発見する機能はありません。

## 実行環境

Python 3.10以上、NumPy 2系。検証環境はPython 3.12.14、NumPy 2.3.5、Windows x64です。既存環境のNumPyを使用し、今回パッケージを追加インストールしていません。標準ライブラリだけのC2/R1に比べ、P1数値演算にはNumPyが必要です。

別環境でNumPyがない場合の準備コマンドは `python -m pip install -r requirements.txt`。これは利用者が必要に応じて実行するもので、自動インストールは行いません。

以下は展開したPLM-P1-v0.1フォルダーをカレントディレクトリにして実行します。`python` が見つからない環境ではPython実行ファイルの絶対パスに置き換えてください。

```powershell
python -B demo.py
python -B -m plm_p1 validate-packet --packet examples/S1_OBSERVATION_PACKET.json
python -B -m plm_p1 decode --packet examples/S1_OBSERVATION_PACKET.json --query examples/QUERY.json --expected-codebook examples/CODEBOOK.json --out recovery.json
python -B verify_release.py
```

`decode` はINPUT_FRAMES.jsonを読みません。既知の照会キーと候補辞書はQUERY.json、正解入力は検証用の別ファイルです。パケットの出典ハッシュから正解を検索する処理もありません。

## 自分の観察を使う

```powershell
python -B -m plm_p1 encode --input examples/INPUT_FRAMES.json --kind frames --dimension 2048 --seed plm-p1-v01 --out packet.json
```

C2/R1の `export_r1_observations` 形式なら `--kind r1-envelope` を指定できます。SQLite DBやMarkdown台帳を直接入力する形式ではありません。前段でR1契約の構造検証を行いますが、その結果を独立した意味的真偽の確認と解釈しません。

Python API:

```python
from plm_p1 import PhaseCodebook, encode, decode
from plm_p1.fixtures import make_frames, entity_candidates

frames = make_frames(2)  # 人工例
book = PhaseCodebook(2048, "my-experiment")
signal = encode(frames, book)
result = decode(signal, book, "synthetic:doc", "event-000", "subject", entity_candidates())
```

結果の `recovered` は「符号化された値の数値回復」を意味します。`eligible_for_inference` はfalseのままで、P1からC2/R1への書き戻しはありません。

## 評価の再実行

```powershell
python -B evaluate.py --split development
python -B evaluate.py --split evaluation
```

評価用seedの実行にはSOURCE_MANIFEST.jsonとの一致が必要です。FIRST_EVALUATION.jsonは初回結果を記録し、再実行では上書きしません。生成器と評価の作者は同じで、これは独立意味評価ではありません。

初期閾値で開発負例を2/64誤受理した記録も残しています。閾値を開発データだけで修正し、評価seedを見る前に固定しました。詳細は `evaluation/THRESHOLD_SELECTION.md`。

## 保証しないこと

高負荷・強い欠損・位相基準の不足で誤回復と誤受理が発生します。相関値は確率ではなく、閾値は未校正です。基準ケースの合格を他条件の精度保証に拡張しません。

S1のSS/PN系列、時間同期、搬送波同期、周波数ずれ補償、実際のSS復調はまだ実装していません。今回の信号パケットは、そのための数値基準面と入出力契約です。物理回路、省電力性、自然言語理解の改善も未実証です。

既知のC2誤りや独立意味評価の必要性は解消していません。正しく符号化・回復できても、元の観察が誤っていれば意味的には誤りのままです。

## 構成

`plm_p1/` 実装、`tests/` 機能試験、`evaluation/` 固定条件、`examples/` デモ、`results/` 数値結果、`verification/` 統合検証、`vendor/PLM-R1-v0.1/` 前提版（C2を含む）です。vendor全117ファイルを前版のまま保存しています。
