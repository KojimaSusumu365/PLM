"""Render measured results without treating abstention as correct retrieval."""


def totals(rows):
    out={}
    for row in rows:
        for k,v in row["counts"].items():
            out[k]=out.get(k,0)+v
    return out


def ratio(c,key):
    return f"{c[key+'_exact']}/{c[key+'_requests']}"


def read_total(c,metric):
    return c["read_seen_"+metric]+c["read_heldout_"+metric]


def write_report(output,r):
    a,b=[totals([row[k] for row in r["standard"]]) for k in ("checked","v04")]
    lines=["# PLM-L1 v0.5：評価結果", "", "## 標準条件での能力維持", "",
           "v0.4と同じ各432文・意味対、同じ符号seed・次元で双方を再学習。全位相記憶の重み・マスク・候補が一致することを確認。変更は読解受理の復元確認と版識別で、回復アルゴリズムや閾値は変更していません。", "",
           "| 方式 | 未学習組合せ 読解 | 未学習組合せ 生成 | 両側未学習 往復 | 既出 読解/生成 | 読解受理後に復元不能 |", "|---|---:|---:|---:|---:|---:|"]
    for name,c in (("v0.5",a),("v0.4再学習",b)):
        lines.append(f"| {name} | {ratio(c,'read_heldout')} | {ratio(c,'generate_heldout')} | {ratio(c,'roundtrip_both_heldout')} | {ratio(c,'read_seen')} / {ratio(c,'generate_seen')} | {c['read_signal_unrecoverable']} |")
    lines += ["",f"受入条件 {sum(x['passed'] for x in r['checks'])}/{len(r['checks'])}、合格判定 {r['passed']}。開発実行は受入条件0件で合格判定を付けません。", "",
              "評価は既存192文を再利用し、4分割×4符号を反復するものです。768種類の新規自然文ではありません。意味・指定語順の両方を独立した限定文法で採点し、自己確認だけで正解とはしていません。保留は成功に数えません。", "",
              "## v0.4で既知だった2件", "", "| 入力 | v0.4 | v0.5 |", "|---|---|---|"]
    for row in r["known_regressions"]:
        lines.append(f"| {row['input']} | {row['old_status']} → {row['old_recovery']['status']} | {row['checked_status']}（{row['checked_reason']}） |")
    lines += ["", "この2件は既知不具合の回帰試験であり、未知評価ではありません。v0.5は意味を新しく復元できたのではなく、復元不能なパケットを読解成功として外へ出さなくなりました。", "",
              "## 言語モデルの次元試験", "", "| seed | 次元 | v0.5 読解正解/要求 | v0.5 誤受理/保留 | v0.4 誤受理/保留 | v0.5 復元不能受理 |", "|---|---:|---:|---:|---:|---:|"]
    for row in r["dimension"]:
        a,b=row["checked"]["counts"],row["v04"]["counts"]
        lines.append(f"| {row['seed']} | {row['dimension']} | {read_total(a,'exact')}/{read_total(a,'requests')} | {read_total(a,'wrong')} / {read_total(a,'abstained')} | {read_total(b,'wrong')} / {read_total(b,'abstained')} | {a['read_signal_unrecoverable']} |")
    lines += ["", "誤受理には、復元不能の受理と、復元できるが独立正解と違う意味の受理を含みます。両者はJSONで別集計しています。新しい受理は旧版で出た信号・完成文の部分集合であることも確認します。", "",
              "## 読解後の意味信号への雑音", "",
              "複素ガウス雑音の方向を固定し、雑音L2ノルム/元信号L2ノルムを指定します。雑音付加は読解の受理後。受信側は必ず再検査します。電波・チップ同期を模擬するものではありません。", "",
              "| seed | 次元 | 相対雑音 | v0.5 復元正解/転送 | 誤受理/保留 | 生成正解/全要求 | v0.4 復元正解/転送 |", "|---|---:|---:|---:|---:|---:|---:|"]
    old={(x['seed'],x['dimension'],x['noise_level']):x for x in r["channel"] if x["condition"]=="v04"}
    for row in r["channel"]:
        if row["condition"]!="checked":
            continue
        c=row["counts"]
        before=old[(row['seed'],row['dimension'],row['noise_level'])]["counts"]
        lines.append(f"| {row['seed']} | {row['dimension']} | {row['noise_level']} | {ratio(c,'recover')} | {c['recover_wrong']} / {c['recover_abstained']} | {c['end_to_end_generate_exact']}/{c['end_to_end_generate_requests']} | {ratio(before,'recover')} |")
    lines += ["", "転送後の成功率だけでなく、読解側で保留した入力も含む全要求に対する生成正解を報告します。生成要求は入力数×2語順。雑音0でも低次元で入力を保留する場合があります。信号が別の有効な意味へ完全に置換された場合、その出典の真正性を識別する認証機能はありません。", "",
              "## 連想記憶の負荷試験（言語モデルとは別）", "",
              "同じ8候補に対して格納するアドレス→値の対応数を増やします。格納した全アドレスと、未格納64アドレスを照会。言語モデルの語彙・出来事数を増やした実験ではありません。位相演算・閾値はv0.4と同一です。", "",
              "| seed | 次元 | 格納数 | 正回復/格納照会 | 誤回復/保留 | 未格納の誤受理/64 |", "|---|---:|---:|---:|---:|---:|"]
    for row in r["memory"]:
        c=row["counts"]
        lines.append(f"| {row['seed']} | {row['dimension']} | {row['load']} | {ratio(c,'known')} | {c['known_wrong']} / {c['known_abstained']} | {c['missing_accepted']}/64 |")
    lines += ["", "通常辞書の対照は同じ対応を格納して実測し、格納照会はすべて正解、未格納はすべて拒否でした。速度・総メモリ予算は揃えていません。高負荷での誤回復や未格納誤受理はそのまま記録し、読解の自己確認で記憶容量問題まで解決したとは主張しません。", "",
              "## 主張の境界", "",
              "受理ゲートは『読解時の自分の候補を数値信号で保持できたか』を調べるもので、候補の意味が正しいことの証明ではありません。整合した誤読は残り得るため、独立採点を継続します。全保留を改善と数えないよう、標準条件の正解率98%以上とv0.4の正解数維持を事前条件にしました。", "",
              "特徴選択は通常の記号・統計処理、分解規約と5意味スロットは手設計。全学習のSS化・容量適応・干渉除去・任意長文・複数出来事は未実装。今回の雑音試験はP1の数値観測マスクやS1同期受信器の統合ではありません。R1推論/Concept更新も開放していません。", "",
              f"ソース固定digest：`{r['freeze_hash']}`", f"結果digest：`{r['result_digest']}`", ""]
    (output/"EVALUATION_REPORT.md").write_text("\n".join(lines),encoding="utf-8")
