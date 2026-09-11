"""Derived tables, including coverage loss; no result-dependent gate changes."""
from pathlib import Path


def aggregate(rows,mode):
    keys=("known_requests","known_exact","known_wrong","known_abstained","missing_requests","missing_accepted")
    return {k:sum(r["methods"][mode]["counts"][k] for r in rows) for k in keys}


def write_report(output,result):
    lines=["# PLM-L1 v0.6 評価結果", "", "固定予算の記憶サブシステム比較。未登録照会の拒否率と、登録照会の正答・誤答・保留を分けて評価する。", "",
           "## 言語試験", "", "|方式|未学習組合せ・読解|未学習組合せ・生成|両側未学習・往復|全往復|", "|---|---:|---:|---:|---:|"]
    for mode in ("single","split_proof","split_unchecked"):
        cells=[]
        for bucket in ("read_heldout","generate_heldout","roundtrip_both_heldout","roundtrip_other"):
            cs=[r["methods"][mode]["counts"] for r in result["standard"]]
            keys=(bucket,) if bucket!="roundtrip_other" else ("roundtrip_both_heldout","roundtrip_other")
            cells.append(str(sum(c[k+"_exact"] for c in cs for k in keys))+"/"+str(sum(c[k+"_requests"] for c in cs for k in keys)))
        lines.append("|"+mode+"|"+"|".join(cells)+"|")
    ordinary=[r for r in result["memory"] if r["scenario"]=="ordinary"]
    lines += ["", "## 独立記憶試験・通常のキー分布（全負荷合算）", "", "|方式|登録照会数|正答|誤答|保留|未登録照会の誤受理|", "|---|---:|---:|---:|---:|---:|"]
    for mode in ("single","split","proof","split_proof","split_unchecked"):
        c=aggregate(ordinary,mode)
        lines.append(f'|{mode}|{c["known_requests"]}|{c["known_exact"]}|{c["known_wrong"]}|{c["known_abstained"]}|{c["missing_accepted"]}/{c["missing_requests"]}|')
    a,b=aggregate(ordinary,"split_proof"),aggregate(ordinary,"single")
    lines += ["", f'未登録誤受理の合算減少率：{100*(1-a["missing_accepted"]/max(1,b["missing_accepted"])):.1f}%。登録正答の維持率：{100*a["known_exact"]/max(1,b["known_exact"]):.1f}%（single比）。',
              "", "これは異なる負荷条件を等しい試行構成で合算した値であり、運用時のエラー確率や統計的有意性ではない。負荷ごとの数値を以下に残す。", "",
              "|分布|D|N|方式|正答|誤答|保留|未登録誤受理|", "|---|---:|---:|---|---:|---:|---:|---:|"]
    groups=sorted({(r["scenario"],r["dimension"],r["load"]) for r in result["memory"]})
    for scenario,d,n in groups:
        rows=[r for r in result["memory"] if (r["scenario"],r["dimension"],r["load"])==(scenario,d,n)]
        for mode in ("single","split","proof","split_proof","split_unchecked"):
            c=aggregate(rows,mode)
            lines.append(f'|{scenario}|{d}|{n}|{mode}|{c["known_exact"]}/{c["known_requests"]}|{c["known_wrong"]}|{c["known_abstained"]}|{c["missing_accepted"]}/{c["missing_requests"]}|')
    lines += ["", "## 判定と限界", "", f'固定判定：{sum(c["passed"] for c in result["checks"])}/{len(result["checks"])}。開発実行には合否判定を付けない。',
              "", "確認信号は誤受理を抑えるが、値記憶の次元を消費し、正答を保留に変える場合がある。分割単独の改善、全負荷での容量改善、誤受理ゼロは保証しない。意図的に同じバンクへ衝突させたケースも省略しない。",
              "", "同一予算は記憶ブロック・付随メタデータ予約領域・固定推論キャッシュ・それらのPythonオブジェクトに限定する。意味コーデック、Model側統計、インタプリタ、照会中の一時割当は含めない。TELEMETRY.jsonに時間とtracemallocの一時割当を別記し、結果ハッシュから除く。通常辞書は同じ照会を解く参考実装だが、予算を揃えていない。",
              "", "言語試験は既存の限定一事象・五スロット文法。記憶試験のN増加は言語知識の拡張ではない。ID3型の依存特徴選択、文字列処理、ルーティング、制御は通常Python。明示チップ列の拡散・逆拡散や同期との接続は未実装。", ""]
    (Path(output)/"REPORT.md").write_text("\n".join(lines),encoding="utf-8")
