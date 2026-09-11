"""Generate user-facing decision from completed, verified measurements."""
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parent.parent/"outputs"/"PLM-L1-v0.6"
sys.path.insert(0,str(ROOT))
from report import aggregate

r=json.loads((ROOT/"results"/"EVALUATION.json").read_text(encoding="utf-8"))
v=json.loads((ROOT/"verification"/"REPRODUCIBILITY.json").read_text(encoding="utf-8"))
assert r["passed"] and v["status"]=="passed"
ordinary=[x for x in r["memory"] if x["scenario"]=="ordinary"]
a,b=aggregate(ordinary,"split_proof"),aggregate(ordinary,"single")
coverage=100*a["known_exact"]/b["known_exact"]
reduction=100*(1-a["missing_accepted"]/b["missing_accepted"])
cs=[x["methods"]["split_proof"]["counts"] for x in r["standard"]]
language={key:(sum(c[key+"_exact"] for c in cs),sum(c[key+"_requests"] for c in cs)) for key in ("read_heldout","generate_heldout","roundtrip_both_heldout","roundtrip_other")}
memory_bytes=sum(m["owned_heap_bytes"] for m in v["primary_memory_storage"].values())
lines=["# PLM-L1 v0.6：実施結果と次の判断", "", "2026-09-07", "",
       "## 結論", "", "負荷に応じた学習時の記憶分割と、部分キー／候補値の位相確認信号を実装した。固定した限定言語試験を維持しつつ、通常分布の独立記憶試験で未登録照会誤受理を抑制した。高負荷の正答を保留に変える代償が残るため、容量問題の全面解決や分割方式の普遍的優越とは判定しない。", "",
       "## 実測", "", "|項目|結果|", "|---|---:|"]
for title,key in (("未学習組合せの読解","read_heldout"),("未学習組合せの直接生成","generate_heldout"),("両側未学習の往復","roundtrip_both_heldout")):
    e,n=language[key]; lines.append(f"|{title}|{e}/{n}|")
e=sum(language[k][0] for k in ("roundtrip_both_heldout","roundtrip_other"))
n=sum(language[k][1] for k in ("roundtrip_both_heldout","roundtrip_other"))
lines += [f"|全往復|{e}/{n}|",f'|記憶・未登録誤受理（single → split_proof）|{b["missing_accepted"]}/{b["missing_requests"]} → {a["missing_accepted"]}/{a["missing_requests"]}|',
          f'|記憶・登録誤答|{b["known_wrong"]} → {a["known_wrong"]}|',f'|記憶・登録正答|{b["known_exact"]}/{b["known_requests"]} → {a["known_exact"]}/{a["known_requests"]}|',
          f'|記憶・登録保留|{b["known_abstained"]} → {a["known_abstained"]}|',f'|固定受入条件|{len(r["checks"])}/{len(r["checks"])}|',f'|新版＋旧版の機能／回帰テスト|{sum(v["test_counts"].values())}/341|',
          "",f"記憶の通常分布32条件の合算で、未登録誤受理は{reduction:.1f}%減少。登録正答はsingleの{coverage:.1f}%を維持した。これらは試験条件の合算であり、実運用の出現頻度を反映した保証や有意性検定ではない。通常分布と意図的なバンク集中を区別し、全34条件×5方式をREPORTとJSONに残した。", "",
          "## 同一予算の範囲", "", f"主モデルの記憶サブシステム所有ヒープは{memory_bytes:,} bytes。比較するsingle／split_proof／split_unchecked間で同じで、独立記憶試験の五方式も各条件内で同じ。確認用係数を追加予算にせず、値記憶の1/4を置き換える。",
          "", "この数値は記憶ブロック・予約メタデータ・固定キャッシュ等の所有領域である。意味コーデック、Model側の監査統計、プロセス全体、一時領域を含めた総RAM一致ではない。時間・一時割当の別測定はTELEMETRYを参照する。通常辞書は参考として同じ照会を処理するが、同一予算対照ではない。", "",
          "## 再現性・情報境界", "", "ソース300ファイルと評価条件を固定し、全数値評価を2回実行。結果JSON・報告・モデル情報・全ブロック配列が一致した。341テストの件数は1回の実行分であり、繰返し回数を掛けていない。",
          "", "旧モデル・教師・評価コーパスのない別環境で432の文／意味対と初期語彙から同じモデルを再学習できた。reader.py・training.py・旧版・コーパスのない生成専用環境で、数値意味パケットだけを渡す4例も成功した。ただし共有の数値モデルと特徴補助コードは残るため、読解に関する知識が一切ないという主張ではない。",
          "", "v0.5の代数・特徴構築・依存選択・語彙処理・読解受理コードはバイト一致を確認。旧L1/P1/S1の1421ファイルと同梱v0.5の268ファイルを維持した。旧128次元不具合2件は、singleの旧版同等方程式を使うCLI回帰試験でもパケットを出さず保留した。", "",
          "## 未達事項と次の焦点", "", "バンク集中条件では、singleの正答251/256・誤答0・未登録誤受理1/256に対し、split_proofは正答85/256・誤答7・未登録誤受理5/256となり、悪化した。確認だけのproofはこの条件で正答205/256・誤答0・未登録誤受理0/256だった。したがって分割を万能な改善として採用してはいけない。次は、バンクの偏りを検知して安全に扱う仕組みと、負荷に対する受理／誤受理の利用範囲を先に定めたい。二事象や長文への拡張は別の段階として扱い、本版へ自動追加していない。",
          "", "最終目標に向けて、特徴選択や制御に残る通常処理、複数事象／長文、Phase部分観測、S1明示チップ列・同期接続は未実装。推論やConcept更新は開放していない。既存の制御コーパスを再利用した実証であり、新規自然文への一般性やSSだけの優位性は主張しない。",
          "", f'ソース固定digest：`{v["source_freeze"]}`', "", f'結果digest：`{r["result_digest"]}`', "", f'主モデルfingerprint：`{v["primary_model_fingerprint"]}`', ""]
with (ROOT/"results"/"RELEASE_DECISION.md").open("x",encoding="utf-8") as stream:
    stream.write("\n".join(lines))
print(json.dumps({"missing_false_reduction_percent":reduction,"known_correct_retention_percent":coverage,"memory_owned_bytes":memory_bytes},ensure_ascii=False))
