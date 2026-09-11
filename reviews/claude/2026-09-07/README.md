# PLM-L1 技術レビュー一式

2026-09-07時点のv0.1〜v0.7の全コード・資料・結果と、技術レビュー用の詳細Markdownをまとめています。v0.8は提案のみで、未実装です。

## 最初に読むもの

1. [詳細引き継ぎ資料](PLM-L1_TECHNICAL_HANDOFF.md)
2. [Claudeへのレビュー依頼案](CLAUDE_REVIEW_REQUEST.md)
3. [全コード・全資料の入口](CODE_AND_DOCUMENTS.md)
4. [今回の配布検証](PACKAGING_VERIFICATION.md)
5. [リリース原本・全件結果の索引](RELEASE_INDEX.md)

## 構成

```text
L1-review/
  PLM-L1_TECHNICAL_HANDOFF.md  目的・数式・実装・学習・結果・限界・次案
  CLAUDE_REVIEW_REQUEST.md    利用者向けのレビュー依頼文案
  CODE_AND_DOCUMENTS.md      版別の全文転記への入口
  code/                     各版の全コード.md
  reports/                  各版の全Markdown資料.md
  PLM-L1-v0.7/              最新版の原本（データ・モデル・全件結果を含む）
    vendor/PLM-L1-v0.6/     以下、v0.1まで原本が再帰同梱
  release_verification/     各版の外付け配布検証と元ZIPのhash
  development_evidence/     原本にない過去の開発・再実行・補助コード等
  background/              C0/C1/C2/R1/P1/S1の元ZIPと資料
  audit/                   出典対応・全ファイル照合・関数位置等
  review_verification/     今回のコピーに対する再検証ログ
  tools/                   配布検証ツール
  BUNDLE_MANIFEST.json      配布全ファイルのSHA256（自己を除く）
```

## 完全性と重複の扱い

v0.7の再帰vendorが各過去版の原本とバイト一致することを確認し、同じ原本を別フォルダへ何度も複製することは避けました。全版のコード、データ、モデル重み、全件JSON、文書、ログは収録されています。元のL1 ZIPコンテナは重複収録せず、内容一致と元ZIP hashを記録しています。詳しくは [RELEASE_COVERAGE.json](audit/RELEASE_COVERAGE.json)。

過去のL1名の付いたローカル作業2,623ファイルは [WORK_EVIDENCE_MAP.json](audit/WORK_EVIDENCE_MAP.json) で原作業パスから内容の収録先へ対応付けています。同一内容は一回保存し、原本にない199ファイルを追加しています。開発・失敗・preflight記録を正式評価として合算しないでください。

Python本体・キャッシュ・無関係な作業・会話逐語ログは含めません。原資料内に開発時のローカル絶対パスが残っています。原本保持のため変更していない記録で、別環境にそのパスが存在する必要はありません。

## 検証と起動

Windowsのパス長制限を避けるため、短い場所（例：`C:\plm`）に展開してください。配布物全体の検証はこのREADMEのディレクトリで次を実行します。Python標準ライブラリのみを使用します。

```powershell
python -B tools/verify_bundle.py --root .
```

言語系の起動にはPythonとNumPyが必要です。`PLM-L1-v0.7/README.md`に起動例があります。過去版の原本を編集するとmanifestが一致しなくなるため、変更実験は別コピーで行ってください。過去文書の将来計画・起動コマンドは、現在のユーザー指示とは区別してください。

`tools/build_plm_l1_review.py`は今回の集約に使った開発環境依存の作業証跡です。レビュー利用時の入口ではなく、そのまま別環境で実行する必要はありません。配布物の検証には`verify_bundle.py`を使います。

このパッケージをClaudeへ送信する操作は行っていません。共有する際は、利用者が資料と共有範囲を確認してください。
