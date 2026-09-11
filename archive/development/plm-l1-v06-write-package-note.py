import json
from pathlib import Path

outputs=Path(__file__).resolve().parent.parent/"outputs"
v=json.loads((outputs/"PLM-L1-v0.6-VERIFICATION.json").read_text(encoding="utf-8"))
assert v["status"]=="passed" and v["release_manifest_checked"] and v["source_and_archive_unchanged"]
lines=["# PLM-L1 v0.6：配布ZIPの検証結果", "", "2026-09-07、実際のZIPを新しい作業フォルダへ展開して検証を完了した。", "",
       "|項目|結果|", "|---|---|", "|ZIP|PLM-L1-v0.6.zip|", f"|サイズ|{v['archive_bytes']:,} bytes|", f"|ファイル数|{v['archive_files']}|",
       "|CRC・全展開ファイルのバイト一致|合格|", f"|機能／回帰テスト|{sum(v['test_counts'].values())}/341（新版73＋旧版268）|", f"|保存数値評価の固定受入|{v['acceptance_checks']}/351|",
       "|全数値評価|2回で結果JSON・報告・モデル情報・重み配列が一致|", "|別環境学習|432対と初期語彙から同一モデルを再現|",
       "|別環境生成|reader.py・training.py・旧版・コーパスなしで4例成功|", "|旧128次元不具合2件|single同等方程式の通常CLIで保留、パケットなし|",
       "|ZIP展開後の通常CLI|未学習組合せの読解→語順変更、意味直接入力→生成に成功|", "|検証後のソース・ZIP|全バイト不変|", "",
       "ZIP SHA-256：", "", "```text", v["archive_sha256"], "```", "",
       f"ソース固定digest：`{v['source_freeze']}`", "", f"結果digest：`{v['result_digest']}`", "", f"モデルfingerprint：`{v['model_fingerprint']}`", "",
       "## 検証範囲", "", "Python 3.12.14 / NumPy 2.3.5、OPENBLAS_NUM_THREADS=1。Python本体は同梱しない。ZIP展開後は保存評価の整合性・テスト・別環境の学習／生成を検証した。全数値評価の2回実行は別工程で、ZIP展開後に3回目の全数値評価を行ったという意味ではない。タイミング・tracemalloc観測値は決定論的な一致比較から外している。",
       "", "記憶分割と確認信号によって未登録誤受理を抑制するが、固定係数予算での正答の保留増加が残る。同一予算は記憶サブシステムの所有領域に限定し、プロセス全体・意味コーデック・一時領域の一致を意味しない。完全な存在判定、誤受理ゼロ、SS独自の優位性は主張しない。",
       "", "限定文法・既存データの実証。全SS学習、Phase部分観測/S1同期の統合、複数事象／長文、R1推論開放、Concept更新は未実装。生成専用環境にも共有数値モデル・特徴補助コードは残る。",
       "", "詳細は配布内README.md、SPECIFICATION.md、results/REPORT.md、results/RELEASE_DECISION.md、および同名の検証JSONを参照。", ""]
with (outputs/"PLM-L1-v0.6-VERIFICATION.md").open("x",encoding="utf-8") as stream:
    stream.write("\n".join(lines))
print(json.dumps({"note":str(outputs/"PLM-L1-v0.6-VERIFICATION.md")}))
