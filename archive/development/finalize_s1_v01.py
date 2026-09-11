"""Post-evaluation outcome, without modifying frozen sources or the first result."""
from datetime import datetime,timezone
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parent/"PLM-S1-v0.1"
r=json.loads((ROOT/"results/EVALUATION_RESULTS.json").read_text(encoding="utf-8"))
v=json.loads((ROOT/"verification/VERIFICATION_RESULTS.json").read_text(encoding="utf-8"))
if not v["functional_passed"] or not v["full_s1_numerical_replay_performed"] or not v["full_s1_replay_matches"]:
    raise SystemExit("Full functional verification and numerical replay required")
lookup={(a["condition"],a["method"]):a for a in r["aggregates"]}
failed=[k for k,passed in r["acceptance"].items() if not passed]
status={"version":"PLM-S1 v0.1","created_at_utc":datetime.now(timezone.utc).isoformat(),
        "release_kind":"experimental_target_met" if not failed else "experimental_target_not_met",
        "implementation_complete":True,"functional_verification_passed":v["functional_passed"],"numerical_acceptance_passed":r["acceptance_passed"],
        "unmet_criteria":failed,"ss_demodulation_implemented":True,"implementation_scope":"synthetic_discrete_complex_baseband_only",
        "inference_enabled":False,"independent_semantic_evaluation":"not_performed",
        "next_candidate":"S1 v0.2: resolve frequency ambiguity / widen acquisition safely before fractional-delay and multipath extensions"}
(ROOT/"RELEASE_STATUS.json").write_text(json.dumps(status,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
lines=["# PLM-S1 v0.1 受入判断", "", "実装・機能検証は完了。事前定義した数値受入は **"+("合格" if not failed else "未達あり")+"**。", "",
       "2048個のP1複素成分を4チップずつに拡散し、前後のパイロットとガードを含む8480チップを送受信する最小実証を実装しました。整数遅延・位相・小さな一定周波数ずれをパイロットから推定し、逆拡散した数値を凍結P1 v0.2へ接続しています。",
       "296ファイルを未知評価前に固定。8符号seed×4チャネルseedで評価し、初回結果を保存・別実行で完全再現しました。評価後に方式や閾値を変更していません。", "",
       "## SS実受信器の主条件", "", "| 条件 | 回復 | 誤回復 | 保留 | 負例誤受理 | 同期受理/試行 | 正しい整数遅延 |", "|---|---:|---:|---:|---:|---:|---:|"]
for name in ("nominal","phase_only","integer_delay","small_cfo","combined","partial_combined"):
    a=lookup[(name,"ss_pilot")]
    lines.append(f"| {name} | {a['correct']}/{a['positive_queries']} | {a['wrong']} | {a['abstained']} | {a['false_accepts']}/{a['negative_queries']} | {a['pilot_aligned_trials']}/{a['trials']} | {a['exact_delay_trials']} |")
partial=lookup[("partial_combined","ss_pilot")]
lines += ["", f"25%**チップ**観測の複合条件で、平均P1成分カバー率は{partial['mean_coordinate_coverage']:.2%}でした。P1成分の25%観測と同じ意味ではありません。最大CFO誤差 {partial['max_cfo_error_hz']} Hz、最大位相誤差 {partial['max_phase_error_rad']} rad。", "",
          "## 比較で分かったこと", "", "全方式で総送信エネルギー57344、8480チップ、同じP1入力と候補数を使用。パイロット256チップ・ガード32チップも内数です。", "",
          "| 条件 | 方式 | 回復 | 負例誤受理 | 平均成分カバー率 | 平均NMSE |", "|---|---|---:|---:|---:|---:|"]
for condition in ("partial_combined","tone_interference"):
    for method in ("direct_pilot","repeat_pilot","ss_pilot"):
        a=lookup[(condition,method)]
        lines.append(f"| {condition} | {method} | {a['correct']}/{a['positive_queries']} | {a['false_accepts']}/{a['negative_queries']} | {a['mean_coordinate_coverage']:.2%} | {a['mean_nmse_on_recovered_coordinates']} |")
lines += ["", "非拡散反復も同じ時間・エネルギーを使い、チップ欠落を分散できます。SSだけが白色雑音下で無料の利得を得るとは主張しません。DC干渉を含む限定条件での数値誤差改善と、Relationの回復数や意味の真偽は区別します。", "", "## 状態の保存", ""]
s=r["state_evaluation"]
lines += [f"全7-slotが回復した出来事: {s['exact_frames']}/{s['frames']}。slot正例の回復 {s['summary']['correct']}/{s['summary']['positive_queries']}、誤回復 {s['summary']['wrong']}、保留 {s['summary']['abstained']}。述語・状態の真値欠落負例誤受理 {s['summary']['false_accepts']}/{s['summary']['negative_queries']}。",
          "否定・仮定・引用による隔離・訂正対象・同Concept別個体のR1連携テストも実行。観察内容を肯定事実へ変換せず、推論はfalseのままです。", "", "## 既知の失敗側", ""]
for condition in ("missing_pilots","sparse_observation","out_of_delay","aliased_cfo","no_observation"):
    a=lookup[(condition,"ss_pilot")]
    lines.append(f"- {condition}: 回復 {a['correct']}/{a['positive_queries']}、誤回復 {a['wrong']}、保留 {a['abstained']}、負例誤受理 {a['false_accepts']}/{a['negative_queries']}。同期受理 {a['pilot_aligned_trials']}/{a['trials']}。")
alias=lookup[("aliased_cfo","ss_pilot")]
lines += ["", f"特に範囲外CFOの折返しでは、パイロット同期を受理しても最大周波数誤差は {alias['max_cfo_error_hz']} Hzでした。aligned表示だけでは正しい同期を保証できません。これを本版の動作範囲外として明示し、独立した回復評価も残しています。", "",
          "## 検証と配布", "", f"テスト合計 **{v['total_tests']}件合格**、skipなし。内訳: {v['tests']}。旧P1 v0.2全260ファイルは無変更。",
          f"新規数値評価は{v['numeric_queries']}比較照会と{v['state_queries']}状態照会。全S1数値評価を再実行して初回と一致。旧P1の数値回帰は12条件×5方式×1 seedペアの1440照会を再実行し、旧全評価は保存ハッシュで確認しています。旧全数値評価を再計算したとの主張はしません。",
          "ZIP展開後の検証は外側のPLM-S1-v0.1-VERIFICATION.mdを参照してください。", "", "## 次の工程", "",
          "次は、二つのパイロット間の周波数折返しを解く粗同期・パイロット配置の改善を優先するのが妥当です。より広い周波数範囲で誤同期と保留を評価してから、分数チップ遅延・時計ずれ・マルチパスへ段階的に広げます。",
          "SS復調は人工離散ベースバンドの最小実装です。RF実機、認証、独立意味評価は未実施。R1推論の開放は行っていません。", "",
          "未達の受入条件: "+(", ".join(failed) if failed else "なし（範囲外の既知の制約は上記のとおり）。"), ""]
(ROOT/"results/RELEASE_DECISION.md").write_text("\n".join(lines),encoding="utf-8")
print(json.dumps(status,indent=2))
