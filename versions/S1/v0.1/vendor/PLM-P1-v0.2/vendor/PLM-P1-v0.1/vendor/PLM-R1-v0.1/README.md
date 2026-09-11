# PLM-R1 v0.1 — 観察専用Relation層と独立評価の準備

C2 v0.4が出力したRelationを、原文・個体・根拠・否定・仮定・隔離状態を保って受け取り、レビューできるローカルPython実装です。推論・Concept更新・学習・外部サービスへの登録は行いません。

## 今回の成果

- SQLiteによる観察保存。再取り込みは冪等、出典の改訂は追跡可能です。
- 内容IDと外部出典IDを分離。同じ内容のコピーを独立した証拠として数えません。
- 個体IDを内容IDで名前空間化。同じConceptの別個体、別文書の同名IDを混同しません。
- 原文、役割、根拠、訂正前後の証拠、照応候補、C2分類を確認できるJSON/Markdown台帳。
- 追記式のレビュー。賛同記録を付けても観察の書き換えや推論への昇格は起きません。
- 独立評価用の盲検タスク作成、注釈仕様、原文span採点、タスク凍結、未実施状態の表示。

まず `examples/REVIEW_LEDGER.md`、次に `evaluation/ANNOTATION_GUIDE.md` を参照してください。

## 実行環境

Python 3.10以上、標準ライブラリのみ。追加パッケージ・ネットワークは不要です。以下は展開したこのフォルダーをカレントディレクトリにして実行します。環境によっては `python` をPython実行ファイルの絶対パスに置き換えてください。

```powershell
python -B -m plm_r1 verify-dependency
python -B verify_release.py
python -B demo.py
```

`verify_release.py` はR1テスト、C2の既存テスト、C2評価結果の再現、CLI往復を検証し、`verification/` に結果を出力します。C2の保存済み成果物は変更しません。`demo.py` は内部16例の台帳と空の独立評価テンプレートを再生成します。実データを記入した注釈ファイルは別名で管理してください。

## 観察を取り込む

```powershell
python -B -m plm_r1 ingest --db observations.sqlite3 --input examples/INPUTS.json --kind inputs --source-id local-document-001 --revision 1
python -B -m plm_r1 ledger --db observations.sqlite3 --json-out ledger.json --markdown-out ledger.md
```

`--kind inputs` は文字列または文字列配列のJSONをC2で解析します。`analysis` はC2解析結果全体、`envelope` は `export_r1_observations` の出力を受け取ります。同じ出典・改訂に異なる内容を登録すると拒否します。変更版は `--revision 2` など、別改訂として登録してください。

Python API:

```python
from plm_r1 import ObservationStore, analyze

result = analyze(["A dog and another dog entered.", "They were photographed."])
with ObservationStore("observations.sqlite3") as store:
    receipt = store.ingest_analysis(result, source_id="doc-001", revision="1")
    ledger = store.ledger()
```

解析全体を渡す場合はC2の規則監査を再実行し、原文・分類・未解決照応・操作履歴も保存します。envelopeだけでは原文の内容ハッシュ、元グラフ、未解決照応を再検証できません。その不足を台帳と取り込み結果に明示します。同じenvelopeに完全解析を後から追加することはできますが、既存の異なる解析を上書きしません。

## レビューを追記する

`python -B -m plm_r1 review --db observations.sqlite3 --input review.json`

`review.json` は次のキーを持つJSONです。対象IDは台帳から取得してください。

```json
{
  "event_id": "review-001",
  "document_id": "台帳の64桁内容ID",
  "target_id": "内容ID、または内容ID:F0001",
  "reviewer_id": "reviewer-local-id",
  "decision": "needs_review",
  "error_types": ["missing_relation"],
  "note": "原文を確認した結果と、その根拠を記す。"
}
```

decisionは `needs_review / agrees_with_observation / disagrees / uncertain` のみ。訂正は新しいevent_idで追記します。誰がいつ何を判断したかは残りますが、本人性を認証する機能はありません。

## 独立評価を開始するとき

`evaluation/SAMPLING_PLAN.md` に従って実例80件を目安に収集し、別担当者2名の注釈と別の裁定者を用意します。実データも独立注釈者も今回未提供であり、独立評価は未実施です。

```powershell
python -B -m plm_r1 prepare-evaluation --corpus corpus.json --out annotations.json --manifest-out task-manifest.json
python -B -m plm_r1 evaluate --annotations annotations.json --task-manifest task-manifest.json --out independent-result.json
```

入力形式は `evaluation/ANNOTATION_GUIDE.md`。採点結果が成功でも推論は有効になりません。次のリリースで結果と境界を別途審査する必要があります。

## 制約

C2 v0.4の3件の既知失敗を保持しています。高信頼度の分類誤り、未知金融述語、未知訂正述語はR1では修正していません。`rule_checked` は同じ実装系列の規則整合性であり、独立に確認された意味的真実ではありません。

暗号署名・ユーザー認証・暗号化・共有DBサービス・クロス文書照応・推論エンジンは対象外です。DBと台帳には原文が含まれるため、機密文書の保存先・アクセス権・共有範囲は利用者が管理してください。削除APIは提供せず、テスト/実データDBは分離してください。

## ファイル構成

`plm_r1/` 実装、`tests/` R1検証、`vendor/PLM-C2-v0.4/` 無変更の前提版、`examples/` 内部デモ台帳、`evaluation/` 独立評価準備、`verification/` 実行証跡です。`SOURCE_MANIFEST.json` は実装・試験・手順・依存ファイルを固定します。
