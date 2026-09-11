"""Produce a concise release decision from finished, verified measurements."""
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parent.parent/"outputs"/"PLM-L1-v0.5"
sys.path.insert(0,str(ROOT))
from report import totals,ratio,read_total

r=json.loads((ROOT/"results"/"EVALUATION.json").read_text(encoding="utf-8"))
v=json.loads((ROOT/"verification"/"REPRODUCIBILITY.json").read_text(encoding="utf-8"))
assert r["passed"] and v["status"]=="passed"
c=totals([x["checked"] for x in r["standard"]])
low={key:totals([x[key] for x in r["dimension"] if x["dimension"]==128]) for key in ("checked","v04")}
channel=[x for x in r["channel"] if x["condition"]=="checked" and x["dimension"]==8192]
memory_worst=max(r["memory"],key=lambda x:x["counts"]["known_wrong"]+x["counts"]["missing_accepted"])
mc=memory_worst["counts"]
lines=["# PLM-L1 v0.5：実施結果と到達点", "", "実施日：2026-09-07", "",
       "## 結論", "",
       "読解の受理を『意味候補を選んだ』だけでなく、『その候補を数値信号から復元できる』まで含めるよう修正しました。v0.4の部品再利用能力は標準条件で維持し、次元・雑音・記憶負荷を分離した測定を追加しました。",
       "", "既知の128次元の2件は、v0.4ではreadを返してから意味復元が保留になりました。v0.5では読解側でmeaning_signal_unrecoverableとして保留し、パケットを出しません。意味回復能力を増やしたのではなく、成功扱いと復元可能性の不整合を解消した変更です。",
       "", "## 標準能力と受入", "",
       f"- 未学習組合せ：読解 {ratio(c,'read_heldout')}、生成単体 {ratio(c,'generate_heldout')}、両側未学習の往復 {ratio(c,'roundtrip_both_heldout')}。",
       f"- 既出組合せ：読解 {ratio(c,'read_seen')}、生成 {ratio(c,'generate_seen')}。全往復 {c['roundtrip_other_exact']+c['roundtrip_both_heldout_exact']}/{c['roundtrip_other_requests']+c['roundtrip_both_heldout_requests']}。",
       f"- 読解成功後の復元不能 {c['read_signal_unrecoverable']}、標準条件の全段階の誤受理/誤出力 {sum(c[k] for k in c if k.endswith('_wrong'))}。不正文受理 {c['invalid_text_accepted']}/{c['invalid_text_requests']}、不正パケット生成 {c['invalid_packet_generated']}/{c['invalid_packet_requests']}。",
       f"- 事前受入 {sum(x['passed'] for x in r['checks'])}/{len(r['checks'])}、テスト {sum(v['test_counts'].values())}件（新版70＋v0.4の46＋v0.3の53＋v0.2の52＋v0.1の47）。",
       "", "比較モデルはv0.4も含めて同じ432対・seed・次元から再学習し、数値重み・マスク・候補が完全一致しました。標準正解率98%以上と旧版正解数維持を事前条件にして、保留を増やすだけでは合格しないようにしています。",
       "", "評価は元の192文を再利用した4fold×4符号の反復です。各foldで語順×肯否の1組合せの144学習例を除いています。768は768種類の新しい自然文を意味しません。", "",
       "## 低次元・雑音で分かったこと", "",
       "新しい4符号での128次元の結果（既知不具合2例とは別の集計）：", "", "| 方式 | 読解正解/要求 | 誤受理 | 保留 | 受理後の復元不能 |", "|---|---:|---:|---:|---:|"]
for name in ("checked","v04"):
    a=low[name]
    lines.append(f"| {name} | {read_total(a,'exact')}/{read_total(a,'requests')} | {read_total(a,'wrong')} | {read_total(a,'abstained')} | {a['read_signal_unrecoverable']} |")
lines += ["", "受理ゲートは自分の候補との整合を確認するだけなので、整合した誤読まで排除する保証はありません。主客を反転した教師で学習すると、内部確認を通っても独立正解とは違う意味になり得る対照試験も通しています。", "",
          "標準8192次元での読解後の雑音試験（2符号の合計）：", "", "| 相対L2雑音 | 復元正解/転送 | 誤受理/保留 | 生成正解/元の全要求 |", "|---|---:|---:|---:|"]
for level in sorted({x["noise_level"] for x in channel}):
    a=totals([x for x in channel if x["noise_level"]==level])
    lines.append(f"| {level} | {ratio(a,'recover')} | {a['recover_wrong']} / {a['recover_abstained']} | {a['end_to_end_generate_exact']}/{a['end_to_end_generate_requests']} |")
lines += ["", "雑音は複素ガウス方向をノルム調整して数値信号へ足したものです。信号受信時の回復アルゴリズムは旧版と同じで、v0.5で雑音耐性を向上させたという比較ではありません。S1の同期・チップ列・RF環境の試験でもありません。", "",
          "## 高負荷記憶の限界", "",
          "別の連想記憶部品で、候補8種類を固定し、格納対応数8/32/128/256と次元数を変えました。未格納アドレス64件も照会しています。これは言語モデルの語彙や出来事数を増やす実装とは異なります。",
          f"誤回復＋未格納誤受理が最多だった固定条件は、{memory_worst['dimension']}次元・{memory_worst['load']}対応・{memory_worst['seed']}。格納照会の正回復 {ratio(mc,'known')}、誤回復 {mc['known_wrong']}、保留 {mc['known_abstained']}、未格納の誤受理 {mc['missing_accepted']}/64でした。全32条件と全照会記録をEVALUATION.jsonに保持しています。",
          "通常辞書の対照は格納照会をすべて正回復し、未格納をすべて拒否しました。ただし総メモリ/速度予算は揃えていません。今回の読解ゲートは記憶部品を改良しておらず、容量適応や干渉除去が完成したとは主張しません。", "",
          "## 再現性と配布", "",
          "ソースとプロトコルを凍結して全数値評価を2回実行し、結果JSON・結果報告・モデル情報がバイト一致、全数値重み配列が完全一致しました。再実行で条件や閾値は変えていません。",
          "新版パッケージ・432対・初期語彙だけの環境で同じモデルを再学習できました。読解/学習の実行ファイルを置かない生成専用環境でも、数値パケットのみの転送で4例が正しい意味と語順を保持しました。共有モデル・特徴補助コードは残るため、読解知識そのものをすべて消した検証ではありません。",
          "既知の低次元2件は通常CLIでも終了コード2で保留し、パケットファイルが作られないことを確認しました。",
          f"旧L1/P1/S1の{v['preserved_previous_release_files']}ファイルと同梱v0.4の203ファイルを保持しました。最終ZIP実展開後の検証は配布フォルダ外のPLM-L1-v0.5-VERIFICATION.json/.mdに記録します。", "",
          "## SS方針との関係・残課題", "",
          "位相相関で読解候補・数値意味を扱う方向は維持しています。ただし特徴選択は従来の記号・統計処理、構造分解と5スロットは手設計、受理の一致比較・分岐はPython補助処理です。全学習処理のSS化やSS独自の性能優位性を示す実験ではありません。",
          "P1の観測数値成分マスク/干渉除去、S1同期受信器、未知語義・任意階層・複数出来事・長文は未統合/未実装です。R1推論とConcept更新も開放せず、数値パケットと外部意味結果は観察専用です。",
          "次の実装へ進む場合は、高負荷時の誤回復/未格納誤受理に対する保留・記憶分割の制御を検討する余地があります。二つ以上の出来事の読解・生成へ拡張する際も、今回の整合検査と独立評価を維持する必要があります。本版では次段階を実装していません。", "",
          "## 識別子", "",
          f"- ソース固定：`{r['freeze_hash']}`",f"- 結果：`{r['result_digest']}`",f"- 付属モデル：`{v['primary_model_fingerprint']}`", "",
          "起動方法はREADME.md、詳細はEVALUATION_REPORT.md、再現確認はverification/REPRODUCIBILITY.jsonを参照してください。", ""]
with (ROOT/"results"/"RELEASE_DECISION.md").open("x",encoding="utf-8") as stream:
    stream.write("\n".join(lines))
print(json.dumps({"report":str(ROOT/"results"/"RELEASE_DECISION.md"),"result_digest":r["result_digest"]}))
