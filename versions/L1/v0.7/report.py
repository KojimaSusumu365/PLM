"""Human-readable report derived from all measured successes and failures."""
from pathlib import Path


def write_report(output,result):
    lines=["# PLM-L1 v0.7 評価結果", "", "## 二事象の読解・生成", "", "|方式|読解・両事象完全一致|直接生成・意味と語順一致|往復・意味と語順一致|", "|---|---:|---:|---:|"]
    for mode in ("bound","partitioned"):
        rows=[r for r in result["standard"] if r["mode"]==mode]
        cells=[str(sum(r["counts"][s]["exact"] for r in rows))+"/"+str(sum(r["counts"][s]["requests"] for r in rows)) for s in ("read","generate","roundtrip")]
        lines.append("|"+mode+"|"+"|".join(cells)+"|")
    lines += ["", "一文ごとの正解ではなく、二つの出来事の五スロットと提示順を両方保持した場合だけ完全一致と数える。生成はさらに各文の指定語順を満たす必要がある。", "",
              "## 共有信号の低次元・符号なし対照", "", "|D|方式|復元正答|受理誤答|保留|異なる二事象の順番交換で信号が同じ|", "|---:|---|---:|---:|---:|---:|"]
    for d in sorted({r["dimension"] for r in result["codec"]}):
        for mode in ("bound","partitioned","unbound"):
            rows=[r for r in result["codec"] if r["dimension"]==d and r["mode"]==mode]
            counts={k:sum(r["counts"][k] for r in rows) for k in ("requests","exact","wrong","abstained")}
            distinct=[x for r in rows for x in r["records"] if x["distinct_events"]]
            lines.append(f'|{d}|{mode}|{counts["exact"]}/{counts["requests"]}|{counts["wrong"]}|{counts["abstained"]}|{sum(x["swapped_signal_equal"] for x in distinct)}/{len(distinct)}|')
    lines += ["", "unboundは事象の符号だけを外した対照。異なる出来事の順序が消える。partitionedは前半・後半を事象別に割り当てる対照で、同じD係数を持つ。比較予算は数値パケットの係数数だけであり、実行時の基底配列・全RAM・計算時間は一致させていない。", "",
              "## 共有信号への数値雑音（bound）", "", "|D|相対L2雑音|復元正答|受理誤答|保留|", "|---:|---:|---:|---:|---:|"]
    for d,level in sorted({(r["dimension"],r["level"]) for r in result["noise"]}):
        rows=[r for r in result["noise"] if r["dimension"]==d and r["level"]==level]
        c={k:sum(r["counts"][k] for r in rows) for k in ("requests","exact","wrong","abstained")}
        lines.append(f'|{d}|{level}|{c["exact"]}/{c["requests"]}|{c["wrong"]}|{c["abstained"]}|')
    lines += ["", "雑音試験は評価者の意味から直接作った数値信号の復元試験で、読解→通信→生成の実証ではない。P1観測マスクやS1チップ列・同期は統合していない。", "",
              "## 検証の範囲", "", f'固定受入：{sum(c["passed"] for c in result["checks"])}/{len(result["checks"])}。開発実行には合否判定を付けない。',
              "", "一事象の読解・生成部品はv0.6と同じ432対・同じseedで学習する。新しい事象符号のseedだけを変える。二事象の区切りと位置符号は設計したもので、二文対から学習したものではない。訓練APIに二事象例や評価正解は渡していない。",
              "", "二文は明示的な句点で分割する。提示順と各事象の役割・否定・仮定を扱い、時系列・因果・代名詞・省略・矛盾解消・自由長文は扱わない。生成器へ原文や意味のJSON一覧を転送せず、一つの数値パケットと二つの出力語順指定だけを渡す。意味スロットの復元後には通常Pythonによる制御処理が残る。",
              "", "新しい二文の組合せを既存の制御文法と語彙から構築した試験で、独立に収集した自然文の評価ではない。partitioned対照も成功する場合、共有SS符号化が唯一の方法・性能上優越すると主張しない。v0.6の記憶負荷偏り問題を解消した実験でもない。", ""]
    (Path(output)/"REPORT.md").write_text("\n".join(lines),encoding="utf-8")
