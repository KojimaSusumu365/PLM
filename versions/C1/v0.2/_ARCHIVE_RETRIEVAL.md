# PLM-C1-v0.2：完全データの取得

このフォルダーは履歴を読みやすくするための閲覧用コピーです。原本のコード・文書は編集していませんが、1 MiBを超える結果や数値配列、元ZIP等はGitツリーの対象外です。

- [この版の原本ZIP](https://github.com/KojimaSusumu365/PLM/releases/download/archive-c0-v0.1-to-ss-core-v0.4/PLM-C1-v0.2.zip)
- 原本ZIPのSHA-256：`fe6936fcc2677a4f14cfd654b5987a8578d1c907e720f9ac1d947cfa791877c4`
- 保存した展開済みスナップショット：31ファイル、2,454,302 bytes。
- [全版索引](https://github.com/KojimaSusumu365/PLM/blob/main/docs/VERSION_INDEX.md)
- [復元・照合手順](https://github.com/KojimaSusumu365/PLM/blob/main/docs/REPRODUCING.md)

リポジトリのルートで次を実行すると、当時のスナップショットを完全復元できます。

```sh
python tools/restore_archive.py --version PLM-C1-v0.2 --download --dest ../PLM-restored
```

通常は原本ZIPを優先して取得します。ZIPに含まれない配布後のキャッシュ等がスナップショットに存在する場合は、保存用アセットを使います。原本ZIPと展開済みスナップショットの両方を、それぞれ変更せず保持しています。

復元先にはこの案内ファイルは追加しません。復元した版のREADMEに従って実行してください。この案内はGitHub移管時に新規作成した資料です。
