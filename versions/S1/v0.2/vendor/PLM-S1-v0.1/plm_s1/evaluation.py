"""Paired chip-level comparisons, first-evaluation freeze enforced by evaluate.py."""
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
import json
from pathlib import Path
import numpy as np
from plm_p1.core import PhaseCodebook,encode,digest,require
from plm_p1.evaluation import summarize
from plm_p1_v02.fixtures import make_frames,entity_candidates,public_catalogue,DOC
from plm_p1_v02.recovery import Receiver
from .link import Link,transmit,simulate_channel,despread_aligned,shifted
from .packet import to_packet
from .receiver import Session,MIN_COHERENCE,MIN_DELAY_GAP,MIN_PILOTS_PER_BLOCK

ROOT=Path(__file__).resolve().parents[1]
METHODS=["direct_pilot","repeat_pilot","ss_pilot","ss_sync_disabled","ss_oracle"]


def protocol():
    p=json.loads((ROOT/"evaluation/PROTOCOL.json").read_text(encoding="utf-8"))
    for kind in ("code","channel"):
        require(not set(p[f"development_{kind}_seeds"])&set(p[f"evaluation_{kind}_seeds"]),"Development/evaluation seed overlap")
    require(p["methods"]==METHODS,"Method/protocol drift")
    require(p["pilot_thresholds"]=={"min_observed_per_block":MIN_PILOTS_PER_BLOCK,"min_coherence":MIN_COHERENCE,"min_delay_gap":MIN_DELAY_GAP},"Pilot threshold drift")
    Link(**p["link"]).validate()
    return p


def channel_parameters(channel_seed,condition,link):
    rng=np.random.Generator(np.random.PCG64(700000+channel_seed))
    phase=float(rng.uniform(-np.pi,np.pi))
    cfo=float(rng.uniform(-.16,.16))
    params={"seed":channel_seed,"delay_chips":condition.get("delay_override",[-7,-3,4,8][channel_seed%4] if condition.get("delay") else 0),
            "phase_rad":phase if condition.get("phase") else 0.,"cfo_hz":cfo if condition.get("cfo") else 0.,
            "keep_fraction":condition["keep_fraction"],"noise_std":condition["noise_std"],"jitter_std":condition.get("jitter_std",0.),
            "tone_rms":condition.get("tone_rms",0.),"tone_hz":condition.get("tone_hz",0.),"erase_pilots":condition.get("erase_pilots",False)}
    if condition.get("aliased_cfo"): params["cfo_hz"]=link.chip_rate_hz/link.pilot_separation+.1
    return params


def setup(code_seed,channel_seed,condition):
    p=protocol()
    book=PhaseCodebook(2048,"s1-v01-code-"+str(code_seed))
    frames=make_frames(p["events"])
    memory=encode(frames,book)
    catalogue=public_catalogue()
    base=Link(**p["link"])
    params=channel_parameters(channel_seed,condition,base)
    packets,sessions,channels,budgets={},{},{},{}
    for mode in ("spread","repeat","direct_sparse"):
        link=replace(base,mode=mode)
        frame,norm=transmit(memory,book,link,total_energy=p["total_tx_energy"])
        y,m=simulate_channel(frame,link,**params)
        packet=to_packet(y,m,book,link,norm,source_digest=digest(frames))
        packets[mode]=packet
        sessions[mode]=Session(packet,catalogue,expected_book=book,expected_link=link)
        channels[mode]=(y,m,link,norm)
        budgets[mode]={"frame_chips":len(frame),"duration_seconds":len(frame)/link.chip_rate_hz,
                       "tx_energy":round(float(np.vdot(frame,frame).real),8),"pilot_chips":2*link.pilot_length,"guard_chips":2*link.guard_length,
                       "pilot_energy":round(2*link.pilot_length*norm["pilot_amplitude"]**2,8),
                       "peak_chip_power":round(float(np.max(abs(frame)**2)),8),"public_payload_gain":round(norm["payload_gain"],10)}
    return book,frames,memory,catalogue,params,packets,sessions,channels,budgets


def wrap_error(a,b): return abs(float(np.angle(np.exp(1j*(a-b)))))


def trial(arguments):
    code_seed,channel_seed,condition=arguments
    book,frames,memory,catalogue,params,packets,sessions,channels,budgets=setup(code_seed,channel_seed,condition)
    y,m,link,norm=channels["spread"]
    # These two controls never enter the real Session implementation.
    disabled,disabled_mask,disabled_info=despread_aligned(y,m,book,link,norm)
    corrected=y*np.exp(-1j*(params["phase_rad"]+2*np.pi*params["cfo_hz"]*np.arange(link.frame_length)/link.chip_rate_hz))
    oracle_chips=shifted(corrected,-params["delay_chips"])
    oracle_mask=shifted(m,-params["delay_chips"])
    oracle,oracle_obs,oracle_info=despread_aligned(oracle_chips,oracle_mask,book,link,norm)
    controls={"ss_sync_disabled":(Receiver(disabled,disabled_mask,book,catalogue),disabled,disabled_mask,disabled_info),
              "ss_oracle":(Receiver(oracle,oracle_obs,book,catalogue),oracle,oracle_obs,oracle_info)}
    session_modes={"ss_pilot":"spread","repeat_pilot":"repeat","direct_pilot":"direct_sparse"}
    rows,audits=[],[]
    for method in METHODS:
        if method in session_modes:
            session=sessions[session_modes[method]]
            signal,observed,info=session.values,session.mask,session.despreading
            sync=session.synchronization
        else:
            receiver,signal,observed,info=controls[method]
            sync={"status":"oracle_reference_only" if method=="ss_oracle" else "disabled","estimated_delay_chips":None,"estimated_cfo_hz":None,"estimated_phase_rad":None}
        n=int(observed.sum())
        denominator=float(np.vdot(memory[observed],memory[observed]).real) if n else 0.
        nmse=float(np.vdot(signal[observed]-memory[observed],signal[observed]-memory[observed]).real/denominator) if denominator>0 else None
        audit={"condition":condition["name"],"method":method,"code_seed":code_seed,"channel_seed":channel_seed,
               "sync":sync,"recovered_coordinates":n,"coordinate_coverage":n/book.dimension,"nmse_on_recovered_coordinates":nmse,
               "observed_payload_chips":info["observed_payload_chips"],
               "evaluator_only_channel_truth":params,"estimated_delay_correct":sync["estimated_delay_chips"]==params["delay_chips"] if sync["status"]=="aligned" else None,
               "absolute_cfo_error_hz":abs(sync["estimated_cfo_hz"]-params["cfo_hz"]) if sync["status"]=="aligned" else None,
               "wrapped_phase_error_rad":wrap_error(sync["estimated_phase_rad"],params["phase_rad"]) if sync["status"]=="aligned" else None}
        audits.append(audit)
        choices=entity_candidates(96)
        for f in frames:
            for role in ("subject","object"):
                truth=f["slots"][role]
                for kind in ("present","absent_event","true_value_not_in_dictionary"):
                    candidates=[c for c in choices if c!=truth] if kind=="true_value_not_in_dictionary" else choices
                    event="absent-"+f["event_id"] if kind=="absent_event" else f["event_id"]
                    query={"document_id":DOC,"event_id":event,"role":role,"candidates":candidates}
                    result=session.query(query) if method in session_modes else receiver.scores(**query)
                    outcome=("correct" if result["selected"]==truth else "abstained" if result["selected"] is None else "wrong") if kind=="present" else ("false_accept" if result["selected"] is not None else "correct_rejection")
                    rows.append({"condition":condition["name"],"method":method,"code_seed":code_seed,"channel_seed":channel_seed,
                                 "event_id":event,"role":role,"test_kind":kind,"outcome":outcome,"selected":result["selected"],"reason":result["reason"],
                                 "eligible_for_inference":result["eligible_for_inference"],"p1_top_score":result.get("top_candidates",[{}])[0].get("score") if result.get("top_candidates") else None})
    return {"rows":rows,"audits":audits,"budgets":{"condition":condition["name"],"code_seed":code_seed,"channel_seed":channel_seed,"modes":budgets}}


def aggregates(rows,audits):
    result=[]
    for condition,method in sorted({(r["condition"],r["method"]) for r in rows}):
        group=[r for r in rows if r["condition"]==condition and r["method"]==method]
        details=[a for a in audits if a["condition"]==condition and a["method"]==method]
        nmse=[a["nmse_on_recovered_coordinates"] for a in details if a["nmse_on_recovered_coordinates"] is not None]
        aligned=[a for a in details if a["sync"]["status"]=="aligned"]
        result.append({"condition":condition,"method":method,**summarize(group),"trials":len(details),"pilot_aligned_trials":len(aligned),
                       "exact_delay_trials":sum(a["estimated_delay_correct"] for a in aligned),
                       "max_cfo_error_hz":max((a["absolute_cfo_error_hz"] for a in aligned),default=None),
                       "max_phase_error_rad":max((a["wrapped_phase_error_rad"] for a in aligned),default=None),
                       "mean_coordinate_coverage":float(np.mean([a["coordinate_coverage"] for a in details])),
                       "mean_nmse_on_recovered_coordinates":float(np.mean(nmse)) if nmse else None,
                       "by_code_seed":[dict(code_seed=s,**summarize([r for r in group if r["code_seed"]==s])) for s in sorted({r["code_seed"] for r in group})],
                       "by_channel_seed":[dict(channel_seed=s,**summarize([r for r in group if r["channel_seed"]==s])) for s in sorted({r["channel_seed"] for r in group})]})
    return result


def state_suite(codes,channel_seed,condition):
    rows,full_frames=[],[]
    for code_seed in codes:
        book,frames,memory,catalogue,params,packets,sessions,channels,budgets=setup(code_seed,channel_seed,condition)
        session=sessions["spread"]
        for f in frames:
            matches=[]
            for role,truth in f["slots"].items():
                choices=entity_candidates() if role in {"subject","object"} else catalogue["vocabulary"][role]
                for kind in (["present"] if role in {"subject","object"} else ["present","true_value_not_in_dictionary"]):
                    candidates=choices if kind=="present" else [c for c in choices if c!=truth]
                    result=session.query({"document_id":DOC,"event_id":f["event_id"],"role":role,"candidates":candidates})
                    correct=result["selected"]==truth if kind=="present" else result["selected"] is None
                    outcome=("correct" if correct else "abstained" if result["selected"] is None else "wrong") if kind=="present" else ("correct_rejection" if correct else "false_accept")
                    rows.append({"code_seed":code_seed,"channel_seed":channel_seed,"event_id":f["event_id"],"role":role,"test_kind":kind,"outcome":outcome,"eligible_for_inference":result["eligible_for_inference"]})
                    if kind=="present": matches.append(correct)
            full_frames.append({"code_seed":code_seed,"event_id":f["event_id"],"all_seven_slots_recovered":all(matches)})
    return {"scope":"separate seven-slot synthetic evaluation; target_clause covered in integration tests","summary":summarize(rows),"rows":rows,
            "frames":len(full_frames),"exact_frames":sum(r["all_seven_slots_recovered"] for r in full_frames),"per_frame":full_frames}


def run_suite(split,workers=2):
    require(split in {"development","evaluation"},"Invalid split")
    p=protocol()
    codes,channels=p[split+"_code_seeds"],p[split+"_channel_seeds"]
    rows,audits,budgets=[],[],[]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for condition in p["conditions"]:
            work=[(c,h,condition) for c in codes for h in channels]
            for r in pool.map(trial,work):
                rows.extend(r["rows"])
                audits.extend(r["audits"])
                budgets.append(r["budgets"])
            print("completed",split,condition["name"],flush=True)
    summary=aggregates(rows,audits)
    lookup={(a["condition"],a["method"]):a for a in summary}
    checks={}
    a=p["acceptance"]
    for condition in p["primary_conditions"]:
        s=lookup[(condition,"ss_pilot")]
        checks[condition+"_recovery"]=s["recovery_rate"] >= (a["nominal_recovery_min"] if condition=="nominal" else a["primary_recovery_min"])
        checks[condition+"_false_accept"]=s["false_accept_rate"] <= (a["nominal_false_accept_max"] if condition=="nominal" else a["primary_false_accept_max"])
        checks[condition+"_pilot_alignment"]=s["pilot_aligned_trials"]==s["trials"]
        checks[condition+"_integer_delay"]=s["exact_delay_trials"]/s["trials"]>=a["primary_delay_exact_rate_min"]
        checks[condition+"_cfo_error"]=s["max_cfo_error_hz"] is not None and s["max_cfo_error_hz"]<=a["primary_max_cfo_error_hz"]
        checks[condition+"_phase_error"]=s["max_phase_error_rad"] is not None and s["max_phase_error_rad"]<=a["primary_max_wrapped_phase_error_rad"]
    checks["equal_energy_and_chip_budget"]=all(len({(v["frame_chips"],v["tx_energy"]) for v in b["modes"].values()})==1 for b in budgets)
    checks["missing_pilots_and_zero_observation_abstain"]=all(r["selected"] is None for r in rows if r["method"]=="ss_pilot" and r["condition"] in {"missing_pilots","no_observation"})
    checks["inference_stays_disabled"]=all(r["eligible_for_inference"] is False for r in rows)
    state=state_suite(codes,channels[0],next(c for c in p["conditions"] if c["name"]=="partial_combined"))
    checks["state_inference_stays_disabled"]=all(r["eligible_for_inference"] is False for r in state["rows"])
    return {"version":"PLM-S1 v0.1","split":split,"protocol_hash":digest(p),"numpy_version":np.__version__,
            "dataset_kind":p["dataset_kind"],"code_seeds":codes,"channel_seeds":channels,"aggregates":summary,"rows":rows,"trial_audits":audits,
            "budgets":budgets,"state_evaluation":state,"acceptance":checks,"acceptance_passed":all(checks.values()),
            "real_receiver_has_truth_offsets":False,"inference_enabled":False,"independent_semantic_evaluation":"not_performed",
            "ss_demodulation_implemented":True,"implementation_scope":"synthetic_discrete_complex_baseband_only"}


def render_report(result):
    lines=["# PLM-S1 v0.1 数値評価", "", "分割: "+result["split"], "",
           "人工ベースバンドのチップ列での最小実証です。独立意味評価・実無線機・通信規格への適合試験ではありません。", "",
           "全方式で8480チップ、総送信エネルギー57344、同じP1 2048成分・4出来事・28結合・96候補。パイロット256チップ、ガード32チップを内数とします。",
           "direct_pilotは各成分を1つのチップに載せ残りを空ける直接参照です。repeat_pilotは同じ成分を4回反復する非拡散対照で、同一時間・消失分散の比較としてより強い対照です。",
           "ss_pilotが実際の受信経路。ss_sync_disabledは補正なし、ss_oracleは評価者だけが真の遅延・位相・周波数を使う参照です。", "",
           "## 主語・目的語の回復", "", "| 条件 | 方式 | 回復 | 誤回復 | 保留 | 負例誤受理 |", "|---|---|---:|---:|---:|---:|"]
    for a in result["aggregates"]:
        lines.append(f"| {a['condition']} | {a['method']} | {a['correct']}/{a['positive_queries']} | {a['wrong']} | {a['abstained']} | {a['false_accepts']}/{a['negative_queries']} |")
    lines += ["", "## 実受信器の同期と成分回復", "", "NMSEは回復できた成分だけで計算します。出力なしは0誤差とはせず欠測。比較時は成分カバー率も確認してください。", "",
              "| 条件 | 同期受理/試行 | 正しい整数遅延 | 最大周波数誤差 Hz | 最大位相誤差 rad | 平均成分カバー率 | 平均NMSE |", "|---|---:|---:|---:|---:|---:|---:|"]
    for a in result["aggregates"]:
        if a["method"]!="ss_pilot": continue
        lines.append(f"| {a['condition']} | {a['pilot_aligned_trials']}/{a['trials']} | {a['exact_delay_trials']} | {a['max_cfo_error_hz']} | {a['max_phase_error_rad']} | {a['mean_coordinate_coverage']:.2%} | {a['mean_nmse_on_recovered_coordinates']} |")
    lines += ["", "## 同一予算での干渉比較", "", "| 条件 | 方式 | 平均成分カバー率 | 平均NMSE |", "|---|---|---:|---:|"]
    for a in result["aggregates"]:
        if a["condition"] in {"combined","partial_combined","tone_interference"} and a["method"] in {"ss_pilot","repeat_pilot","direct_pilot"}:
            lines.append(f"| {a['condition']} | {a['method']} | {a['mean_coordinate_coverage']:.2%} | {a['mean_nmse_on_recovered_coordinates']} |")
    lines += ["", "拡散により同一エネルギーでAWGN性能が自動的に上がるとは主張しません。toneは受信側DC干渉の限定例であり、任意の狭帯域・広帯域干渉への保証ではありません。", "",
              "## seed別の観測範囲", "", "同一試行内や交差したseed間には相関があります。以下は信頼区間ではなく、実測グループの最小・最大です。", "",
              "| 条件 | 符号seed別回復率 | チャネルseed別回復率 |", "|---|---:|---:|"]
    for a in result["aggregates"]:
        if a["method"]!="ss_pilot": continue
        cr=[r["recovery_rate"] for r in a["by_code_seed"]]
        hr=[r["recovery_rate"] for r in a["by_channel_seed"]]
        lines.append(f"| {a['condition']} | {min(cr):.2%}–{max(cr):.2%} | {min(hr):.2%}–{max(hr):.2%} |")
    s=result["state_evaluation"]
    lines += ["", "## 状態を含む別評価", "", f"7-slot全体の完全回復: {s['exact_frames']}/{s['frames']}。slot集計: {s['summary']}。訂正target_clauseは別の連携テストで確認します。", "",
              "## 受入", "", f"事前定義した受入チェック: {sum(result['acceptance'].values())}/{len(result['acceptance'])}。", ""]
    lines += [f"- {k}: {'PASS' if v else 'FAIL'}" for k,v in result["acceptance"].items()]
    lines += ["", "## 限界", "", "位相・周波数・遅延の真値はtrial_auditsの評価者用記録にだけ保持し、実際の受信器へ渡しません。公開された小さな周波数範囲の事前条件は使います。",
              "二つの離れたパイロットによる周波数推定には折り返し曖昧性があります。範囲外では同期受理が正しい同期を保証しません。aliased_cfoを隠さず報告します。",
              "分数チップ遅延、サンプル時計ずれ、時間変動周波数、マルチパス、FEC、RF回路、パイロット認証は未実装。SHA256は認証ではありません。",
              "P1の公開候補カタログと近似的な判定規則はそのままです。相関・復調成功は意味の真偽ではなく、推論許可は常にfalseです。", ""]
    return "\n".join(lines)
