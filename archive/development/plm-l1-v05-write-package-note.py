import json
from pathlib import Path

outputs=Path(__file__).resolve().parent.parent/"outputs"
v=json.loads((outputs/"PLM-L1-v0.5-VERIFICATION.json").read_text(encoding="utf-8"))
assert v["status"]=="passed" and v["release_manifest_checked"] and v["source_and_archive_unchanged"]
lines=["# PLM-L1 v0.5：配布ZIPの検証結果", "", "2026-09-07、実際のZIPを新しい作業フォルダへ展開して検証を完了しました。", "",
       "| 項目 | 結果 |", "|---|---|", "| ZIP | PLM-L1-v0.5.zip |", f"| サイズ | {v['archive_bytes']:,} bytes |", f"| ファイル数 | {v['archive_files']} |",
       "| CRC・全展開ファイルのバイト一致 | 合格 |", f"| テスト | {sum(v['test_counts'].values())}/268（新版70＋旧版198） |", f"| 固定数値評価の受入 | {v['acceptance_checks']}/283 |",
       "| 全数値評価 | 2回で結果JSON・報告・モデル情報・重み配列が一致 |", "| 別環境学習 | 432対と初期語彙から同一モデルを再現 |",
       "| 別環境生成 | reader.py・training.py・旧版・コーパスなしで4例成功 |", "| 既知128次元不具合2件 | 通常CLIで保留、パケットファイルなし |",
       "| ZIP展開後の通常CLI | 未学習組合せの読解→語順変更、意味直接入力→未学習組合せ生成が成功 |", "| 検証後のソース・ZIP | 全バイト不変 |", "",
       "ZIP SHA-256：", "", "```text", v["archive_sha256"], "```", "",
       f"ソース固定digest：`{v['source_freeze']}`", "", f"結果digest：`{v['result_digest']}`", "", f"モデルfingerprint：`{v['model_fingerprint']}`", "",
       "## 検証範囲と限界", "",
       "Python 3.12.14 / NumPy 2.3.5、OPENBLAS_NUM_THREADS=1で実施。Python本体は同梱しません。",
       "ZIP展開後のverify_releaseは、保存結果の整合性・機能テスト・別プロセスの学習/生成を再確認しています。全数値評価の2回実行は別工程で、ZIP展開後に3回目の全数値評価を行ったという意味ではありません。268テストは1回あたりの件数で、実行回数を掛けていません。",
       "生成専用環境は共有数値モデル・語彙候補・特徴補助コードを保持します。読解に関係する知識をすべて消した検証ではありません。",
       "v0.5の変更は数値信号を復元できない読解候補を受理しないことです。意味回復能力・記憶容量・雑音耐性を自動的に向上させる変更ではありません。自己整合した誤読もあり得るため、独立意味採点を維持しています。",
       "元コーパスを再利用する限定文法の実証です。高負荷の独立記憶試験には誤回復・未格納誤受理が残り、全結果を保存しています。SS独自の優位性、全学習のSS化、P1/S1統合、複数出来事/長文、R1推論開放、Concept更新は主張しません。", "",
       "機械可読の完全な記録はPLM-L1-v0.5-VERIFICATION.json、起動方法は配布内README.md、結果と限界はresults/RELEASE_DECISION.mdを参照してください。", ""]
with (outputs/"PLM-L1-v0.5-VERIFICATION.md").open("x",encoding="utf-8") as stream:
    stream.write("\n".join(lines))
print(json.dumps({"note":str(outputs/"PLM-L1-v0.5-VERIFICATION.md")}))
