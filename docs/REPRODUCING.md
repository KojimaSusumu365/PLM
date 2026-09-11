# 取得・復元・検証

## 一つの版を使う

Windowsでは入れ子の旧版vendorに長いパスがあります。Gitで取得する場合は `git -c core.longpaths=true clone https://github.com/KojimaSusumu365/PLM.git` とし、短い展開先を推奨します。復元ツールはWindowsの長いパス形式にも対応します。

[版別索引](VERSION_INDEX.md) から原本ZIPをダウンロードし、展開した版のREADMEに従うのが簡単です。原本ZIPの照合値は `manifests/versions.json` と `manifests/ASSETS-SHA256.txt` にあります。

もう一つの方法は、Python 3.10以上の標準ライブラリだけで動く復元ツールです。リポジトリのルートで実行します。

```sh
python tools/restore_archive.py --version PLM-L1-SS-core-v0.4 --download --dest ../PLM-restored
cd ../PLM-restored/PLM-L1-SS-core-v0.4
python -B -m unittest discover -s tests -v
```

最後の試験には当該版の依存関係（v0.4の記録ではPython 3.12.14 / NumPy 2.3.5）が必要です。復元ツールは依存パッケージを自動インストールしません。各実験を実行すると追加ファイルができることがあるため、原本の照合は実行前に行い、再現結果は別フォルダーに記録してください。

## 全データを復元する

```sh
python tools/restore_archive.py --download --dest ../PLM-full-history
```

`outputs/`, `work/`, `inputs/` が復元されます。取得済みのReleaseアセットは既定の `.plm-assets/` にキャッシュします。通信量とディスクの使用量は `manifests/summary.json` を確認してください。全履歴は約14.2 GBの原本ファイルを含み、アセット用の空き容量も別途必要です。

範囲を限定する場合：

```sh
python tools/restore_archive.py --scope outputs --download --dest ../PLM-outputs
python tools/restore_archive.py --scope inputs --download --dest ../PLM-inputs
```

`--version` と `--scope` は併用できません。必要なアセットだけを取得しますが、保存用ZIPの単位で取得するため、一つの版の実ファイル量より通信量が大きくなる場合があります。版単位なら原本ZIPの直接取得が最も軽量です。

ネットワークを使わず、すでに取得した全アセットから復元する場合：

```sh
python tools/restore_archive.py --asset-dir /path/to/release-assets --dest /path/to/new-restore
```

アセット全体と各ファイルのSHA-256を検査します。同名の既存ファイルは同じ内容なら再利用し、異なる内容なら停止します。上書き削除はしません。展開先外へのパストラバーサルも拒否します。

## リポジトリとアセットを照合する

```sh
python tools/verify_archive.py
python tools/verify_archive.py --asset-dir /path/to/release-assets --all-blobs
```

最初のコマンドは閲覧用コピー、マニフェストの整合、版の被覆を検査します。2つ目は保存用ZIPを開き、全原本を再構成する内容が揃っているかを検査します。`--restored-root` を追加すると全量復元先の内容も照合します。

## 実験の再現と移管の検証を区別する

移管時の検証は原本の同一性、取りこぼし、復元可能性、公開先への転送を確認するものです。歴代の数値評価をすべて再学習・再実行したという意味ではありません。当時の実験条件、失敗、改訂、再実行記録は各版のREADME・REPORT・PROTOCOL・verification等を参照してください。

古い開発スクリプトには当時のWindows絶対パス、環境依存、ファイル更新処理が含まれます。アーカイブの資料として保存しており、`archive/development` 以下を無条件に一括実行する手順は提供しません。
