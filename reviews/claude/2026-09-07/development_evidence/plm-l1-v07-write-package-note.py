import json
from pathlib import Path

outputs=Path(__file__).resolve().parent.parent/"outputs"
v=json.loads((outputs/"PLM-L1-v0.7-VERIFICATION.json").read_text(encoding="utf-8"))
assert v["status"]=="passed" and v["release_manifest_checked"] and v["source_and_archive_unchanged"]
lines=["# PLM-L1 v0.7：配布ZIPの検証結果", "", "2026-09-07、実際の配布ZIPを新しい作業フォルダへ展開して検証を完了した。", "",
       "|項目|結果|", "|---|---|", "|ZIP|PLM-L1-v0.7.zip|", f'|サイズ|{v["archive_bytes"]:,} bytes|',f'|ファイル数|{v["archive_files"]}|',
       "|CRC・全展開ファイルの一致|合格|",f'|機能／回帰テスト|{sum(v["test_counts"].values())}/381（新版40＋旧版341）|',f'|保存数値評価の固定受入|{v["acceptance_checks"]}/364|',
       "|数値再現性|全評価2回で結果JSON・報告・モデル情報・部品重み配列が一致|", "|別環境学習|一事象432対と初期語彙から同一モデルを再現|",
       "|別環境生成|新旧のreader.py/training.py・コーパスなしで二事象四例成功|", "|第二文の未知入力|全体を保留、部分パケットなし|",
       "|展開後の通常CLI|読解→二事象生成、意味直接入力→二事象生成、両方成功|", "|検証後のソース・ZIP|全バイト不変|", "",
       "ZIP SHA-256：", "", "```text",v["archive_sha256"],"```", "",f'ソース固定digest：`{v["source_freeze"]}`',"",f'結果digest：`{v["result_digest"]}`',"",f'モデルfingerprint：`{v["model_fingerprint"]}`',"",
       "## 範囲と限界", "", "Python 3.12.14 / NumPy 2.3.5、OPENBLAS_NUM_THREADS=1。Python自体は同梱しない。展開後の検証は保存結果の整合性・全テスト・別環境の再学習／生成を確認したもので、全数値評価を展開後に3回目として再実行したという意味ではない。",
       "", "二文の明示的な区切りと事象の結合符号は設計したもので、二事象例から学習したものではない。生成環境には共有の学習済み部品モデルと補助コードを残す。新しい二文組合せを既存制御文法で評価した限定実証で、自然文の一般理解や自由長文生成は示していない。",
       "", "意味信号の一つのD係数ペイロードを比較するが、全RAM・速度予算の一致は主張しない。事象符号を外すと順序情報が失われるが、別領域に分ける対照も成功するため、SS重畳の唯一性・優位性ではない。全SS学習、P1/S1統合、R1推論開放、Concept更新、v0.6の負荷偏り対策は未実装。", "",
       "詳細は配布内README.md、SPECIFICATION.md、results/REPORT.md、results/RELEASE_DECISION.mdと検証JSONを参照。", ""]
with (outputs/"PLM-L1-v0.7-VERIFICATION.md").open("x",encoding="utf-8") as stream:
    stream.write("\n".join(lines))
print(json.dumps({"note":str(outputs/"PLM-L1-v0.7-VERIFICATION.md")}))
