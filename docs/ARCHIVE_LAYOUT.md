# 格納方針

## 二つの層を分ける理由

このアーカイブは、研究内容をGitHub上で読みやすくする「閲覧用ツリー」と、原本を完全復元する「保存データ」の二層です。

GitHubの通常Gitファイルには100 MiBの上限があり、過去の元ZIPや評価個票にはそれを超えるファイルがあります。大きいファイルだけを捨てたり、数値を丸めたりはせず、同じリポジトリのReleaseに保存します。Releaseの個別アセットも2 GiB未満に収めます。Git LFSは使わず、この作業で有料ストレージの購入はしません。[通常ファイルの制限](https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-large-files-on-github)、[Releaseの制限](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases)。

## 閲覧用ツリー

|場所|内容|
|---|---|
|`versions/C0/v0.1` … `versions/S1/v0.2`|概念・関係・位相・同期復調の段階別スナップショット|
|`versions/L1/v0.1` … `versions/L1/v0.13`|SS型言語コアの初期学習・曖昧性・二事象実証|
|`versions/L1/ss-weighting`, `ss-online`, `ss-multicode`, `ss-active`|重み・逐次学習・複数符号・能動選択|
|`versions/L1/ss-doc`, `p1-s1`, `ss-core`|短文書生成・同期接続・時間波形SSコア|
|`docs/history`|開発方針・レビュー応答の原記録|
|`reviews/claude/2026-09-07`|当時まとめた技術レビュー用資料一式の閲覧用部分|
|`reviews/received`|ユーザーから提示されたレビュー等の関連原資料|
|`archive/verification`|各配布物に付随する外部検証・ハッシュ・ログ|
|`archive/development`|元work直下の開発・梱包・検証補助スクリプト等|
|`manifests`|全原本・版・保存先・ハッシュの機械可読索引|
|`tools`|今回追加した復元・整合検証ツール|

歴代コードのAPIやimport関係を変更しないため、版ごとの内部ディレクトリは組み替えません。重複する旧版のvendorコードも、当時の依存関係として残します。対象拡張子は `.py`, `.md`, `.txt`, `.json`, `.log`, `.sha256`, `.ps1`, `.pdf`、1ファイル1 MiB以下を閲覧用にコピーしています。それ以外も保存データから元のパスへ復元できます。閲覧ツリーだけで実行可能と見なさないでください。

## 完全保存データ

Releaseタグ：`archive-c0-v0.1-to-ss-core-v0.4`

1. 配布済みの元ZIPは、そのまま直接ダウンロード可能なアセットとして保存します。
2. それ以外の全ファイルは、SHA-256ごとの内容に重複排除して `PLM-preservation-blobs-*.zip` に格納します。各メンバー名は `blobs/<先頭2桁>/<SHA-256>` です。
3. `manifests/source-files.jsonl` は、すべての原本パスについて、バイト数・SHA-256・保存アセット・ZIPメンバー・変更時刻・閲覧用パス（該当時）を保持します。
4. 同じ内容を参照する原本パスも一件ずつ残します。訂正前の下書き、途中実験、失敗ログ、配布後の再検査、バイトコードキャッシュも保存対象です。単なる重複と異なる版を混同しません。
5. `source-directories.json` は空ディレクトリも含む元のディレクトリ一覧です。

全量復元時のルートは `outputs/`（歴代成果物）、`work/`（途中作業・再実行・検証）、`inputs/`（明示した元資料）です。Windowsユーザーのホームディレクトリ全体や、Downloads全体のバックアップではありません。今回の移管用作業フォルダーやGitHubの認証設定も対象外です。

`inputs/` はC0 v0.1の元ZIP、Claudeのv0.7レビューと証拠ZIP、脳の基板水準に関するMD/PDF、L1技術引継ぎ、レビューまとめZIP、SS方針文書、関連構想MDの9ファイルです。同名でも内容が異なるSS方針文書は出典別に残しています。C0より前の無関係な実験や別プロジェクトを広く拾っていません。

## バージョンと履歴の解釈

各版の日時や試験ログは原資料の記録です。今回作成するGitコミットを、当時存在したGit履歴の復元とは主張しません。元々Gitで管理されていなかった作業記録から、架空の過去コミットを作りません。入口は [版別索引](VERSION_INDEX.md) です。

元ZIPのSHA-256は変わりません。完全復元はファイル内容・相対パスと記録された変更時刻を対象とし、NTFSのACL・代替データストリーム・作成日時等を含むディスクイメージの復元ではありません。
