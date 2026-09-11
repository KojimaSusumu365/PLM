"""Post-evaluation release decision. Does not change frozen sources or first results."""
from datetime import datetime,timezone
from hashlib import sha256
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parent/"PLM-P1-v0.2"
result=json.loads((ROOT/"results/EVALUATION_RESULTS.json").read_text(encoding="utf-8"))
verification=json.loads((ROOT/"verification/VERIFICATION_RESULTS.json").read_text(encoding="utf-8"))
if not verification["functional_passed"]:
    raise SystemExit("Functional verification must pass before release decision")
lookup={(a["condition"],a["method"]):a for a in result["aggregates"]}
old=lookup[("masked_noise","v01_fixed")]
new=lookup[("masked_noise","projected_adaptive")]
pilot=next(a for a in result["pilot_evaluation"]["aggregates"] if a["method"]=="pilot_estimated")
states=result["state_evaluation"]
failures=[k for k,v in result["acceptance"].items() if not v]
status={"version":"PLM-P1 v0.2","created_at_utc":datetime.now(timezone.utc).isoformat(),
        "release_kind":"experimental_target_met" if not failures else "experimental_target_not_met",
        "implementation_complete":True,"functional_verification_passed":verification["functional_passed"],
        "numerical_acceptance_passed":result["acceptance_passed"],"unmet_criteria":failures,
        "next_recommended_stage":"PLM-S1 v0.1: minimal chip spreading/despreading with measured synchronization",
        "independent_semantic_evaluation":"not_performed","inference_enabled":False,"ss_demodulation_implemented":False}
(ROOT/"RELEASE_STATUS.json").write_text(json.dumps(status,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
lines=["# PLM-P1 v0.2 受入判断", "", "実装・機能検証は完了。数値受入は **"+("合格" if not failures else "未達あり")+"**。", "",
       "開発・既知回帰の確認後、215ファイルを固定してから初回の未知評価を実行しました。方式や閾値を未知結果に合わせて変更していません。",
       "評価は16符号seed×4チャネルseed。旧評価seedは含めていません。ただし人工frameの生成規則は共通で、自然文・独立意味評価の成功を表しません。", "",
       "| 25%観測の方式 | 主語・目的語の回復 | 誤回復 | 保留 | 負例誤受理 |", "|---|---:|---:|---:|---:|"]
for name,a in (("v0.1固定復号器（同じ新規評価・等エネルギー条件）",old),("v0.2干渉除去＋適応判定",new),("v0.2＋パイロット推定位相補正（パイロット費用込み）",pilot)):
    lines.append(f"| {name} | {a['correct']}/{a['positive_queries']}（{a['recovery_rate']:.2%}） | {a['wrong']} | {a['abstained']} | {a['false_accepts']}/{a['negative_queries']}（{a['false_accept_rate']:.2%}） |")
lines += ["", f"状態を含む別集計: 全7-slotが一致した出来事 {states['exact_frames']}/{states['frames']}。slot回復 {states['correct_slots']}/{states['positive_slots']}、誤回復{states['wrong_slots']}、保留{states['abstained_slots']}。状態・述語の欠落真値負例誤受理 {states['false_accepts']}/{states['negative_queries']}。",
          "", "干渉除去＋固定判定ではmasked_noiseの誤受理が0件でしたが、強い位相揺らぎでは回復508/512でした。採用した適応判定はそれぞれ誤受理1件・回復512/512です。万能な優越は主張せず、事前の選択を維持しています。残存誤りと比較の解釈はPOST_EVALUATION_AUDIT.mdに記録しました。",
          "", f"単体・連携テスト: 新規{verification['tests']['P1_v02']} + 旧P1 99 + R1 92 + C2 186 = **{verification['total_tests']}件合格**、skipなし。旧P1/R1/C2は全177ファイル無変更。初回の数値結果も別実行で完全再現しました。", "",
          f"比較照会 {verification['comparison_queries']}件、パイロット照会 {verification['pilot_queries']}件、状態関連照会 {verification['state_queries']}件。これらの反復照会数を単体テスト数や独立標本数へ足しません。", "",
          "## 制約と失敗側", ""]
for condition in ("small_dimension","unknown_nuisance","higher_load","load_only","jitter_only","overload","unreferenced_quarter_turn"):
    a=lookup[(condition,"projected_adaptive")]
    lines.append(f"- {condition}: 回復 {a['correct']}/{a['positive_queries']}、誤回復 {a['wrong']}、保留 {a['abstained']}、負例誤受理 {a['false_accepts']}/{a['negative_queries']}。")
lines += ["", "観測不足・過負荷で全保留する条件は、誤受理が0でも回復に成功したとは扱いません。状態候補の公開カタログが必要で、未知の任意干渉を完全除去するものではありません。",
          "候補スコアと閾値alphaは真偽の確率ではありません。同一seedを共有する試行には相関があるため、試験中0件の誤りをリスク0と解釈しません。", "", "## 次の工程", "",
          "次はPLM-S1 v0.1として、明示的なチップ列の拡散・逆拡散と、パイロットによる同期を接続する最小実証が妥当です。総チップ数・送信エネルギーを固定し、遅延・周波数ずれは段階的に導入します。",
          "この版で実装した同期はグローバル位相だけです。SS型復調、時間・周波数同期、独立意味評価は未実施。R1推論は引き続き開放しません。", "",
          "未達条件: "+(", ".join(failures) if failures else "事前定義した数値受入条件はすべて合格。範囲外の制約は上記の通り。"), ""]
(ROOT/"results/RELEASE_DECISION.md").write_text("\n".join(lines),encoding="utf-8")
print(json.dumps(status,indent=2))
