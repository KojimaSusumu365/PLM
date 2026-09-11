"""Frozen paired evaluation, explicitly separating entity, whole-frame and sync outcomes."""
import json
from pathlib import Path
import numpy as np
from plm_p1.core import PhaseCodebook,encode,channel,digest,require
from .fixtures import make_frames,entity_candidates,public_catalogue,DOC
from .experiment import trial,aggregates,AdaptivePolicy
from .recovery import Receiver
from . import sync_experiment

ROOT=Path(__file__).resolve().parents[1]


def protocol():
    p=json.loads((ROOT/"evaluation/PROTOCOL.json").read_text(encoding="utf-8"))
    require(not set(p["development_code_seeds"]) & set(p["evaluation_code_seeds"]),"Code seed overlap")
    require(not set(p["development_channel_seeds"]) & set(p["evaluation_channel_seeds"]),"Channel seed overlap")
    require(p["policy"]==AdaptivePolicy().__dict__,"Protocol/runtime policy drift")
    return p


def state_suite(codes,channel_seed):
    rows=[]
    frames=make_frames(4)
    catalogue=public_catalogue()
    per_frame=[]
    for seed in codes:
        book=PhaseCodebook(2048,"p1-v02-code-"+str(seed))
        memory=encode(frames,book)
        y,mask=channel(memory,seed=channel_seed,keep_fraction=.25,noise_std=.15,jitter_std=.1)
        receiver=Receiver(y,mask,book,catalogue)
        for f in frames:
            positive=[]
            for role,truth in f["slots"].items():
                choices=entity_candidates() if role in {"subject","object"} else catalogue["vocabulary"][role]
                for kind in (["present"] if role in {"subject","object"} else ["present","true_value_not_in_dictionary"]):
                    candidates=choices if kind=="present" else [c for c in choices if c!=truth]
                    r=receiver.scores(DOC,f["event_id"],role,candidates)
                    correct=r["selected"]==truth if kind=="present" else r["selected"] is None
                    outcome=("correct" if correct else "abstained" if r["selected"] is None else "wrong") if kind=="present" else ("correct_rejection" if correct else "false_accept")
                    rows.append({"code_seed":seed,"channel_seed":channel_seed,"event_id":f["event_id"],"role":role,"test_kind":kind,"outcome":outcome,"selected":r["selected"],"eligible_for_inference":r["eligible_for_inference"]})
                    if kind=="present": positive.append(correct)
            per_frame.append({"code_seed":seed,"event_id":f["event_id"],"all_seven_slots_recovered":all(positive)})
    positives=[r for r in rows if r["test_kind"]=="present"]
    negatives=[r for r in rows if r["test_kind"]!="present"]
    return {"scope":"separate seven-slot synthetic preservation, no target_clause in this fixture", "rows":rows,"per_frame":per_frame,
            "positive_slots":len(positives),"correct_slots":sum(r["outcome"]=="correct" for r in positives),
            "wrong_slots":sum(r["outcome"]=="wrong" for r in positives),"abstained_slots":sum(r["outcome"]=="abstained" for r in positives),
            "negative_queries":len(negatives),"false_accepts":sum(r["outcome"]=="false_accept" for r in negatives),
            "frames":len(per_frame),"exact_frames":sum(f["all_seven_slots_recovered"] for f in per_frame)}


def run_suite(split):
    require(split in {"development","evaluation"},"Invalid split")
    p=protocol()
    codes,channels=p[split+"_code_seeds"],p[split+"_channel_seeds"]
    rows,budgets=[],[]
    for condition in p["conditions"]:
        for code in codes:
            for chan in channels:
                r,b=trial(code,chan,condition,methods=p["methods"],policy=AdaptivePolicy(**p["policy"]))
                rows.extend(r)
                budgets.append({"condition":condition["name"],"code_seed":code,"channel_seed":chan,"codecs":b})
        print("completed",condition["name"],flush=True)
    summary=aggregates(rows)
    look={(r["condition"],r["method"]):r for r in summary}
    nominal=look[("nominal",p["selected_method"])]
    masked=look[("masked_noise",p["selected_method"])]
    sync=sync_experiment.run(codes,channels)
    states=state_suite(codes,channels[0])
    synced=next(r for r in sync["aggregates"] if r["method"]=="pilot_estimated")
    limits=p["acceptance"]
    acceptance={"nominal_all_recovered":nominal["recovery_rate"]>=limits["nominal_recovery_min"],
                "nominal_no_false_accepts":nominal["false_accept_rate"]<=limits["nominal_false_accept_max"],
                "masked_recovery_at_least_95pct":masked["recovery_rate"]>=limits["masked_recovery_min"],
                "masked_false_accept_at_most_2pct":masked["false_accept_rate"]<=limits["masked_false_accept_max"],
                "no_observation_always_abstains":all(r["selected"] is None for r in rows if r["condition"]=="no_observation" and r["method"]==p["selected_method"]),
                "equal_exact_transmit_energy":all(len({c["transmit_energy"] for c in b["codecs"].values()})==1 for b in budgets),
                "pilot_recovery_at_least_95pct":synced["recovery_rate"]>=p["pilot"]["acceptance_recovery_min"],
                "pilot_false_accept_at_most_2pct":synced["false_accept_rate"]<=p["pilot"]["acceptance_false_accept_max"],
                "all_pilot_trials_aligned":sync["phase_aligned_trials"]==sync["phase_estimation_trials"],
                "pilot_max_phase_error_at_most_0p1rad":sync["max_absolute_phase_error_rad"] is not None and sync["max_absolute_phase_error_rad"]<=p["pilot"]["max_phase_error_rad"],
                "no_state_inference_promotion":all(r["eligible_for_inference"] is False for r in states["rows"])}
    return {"version":"PLM-P1 v0.2","split":split,"protocol_hash":digest(p),"numpy_version":np.__version__,"dataset_kind":p["dataset_kind"],
            "selected_method":p["selected_method"],"code_seeds":codes,"channel_seeds":channels,"aggregates":summary,"rows":rows,"budgets":budgets,
            "state_evaluation":states,"pilot_evaluation":sync,"acceptance":acceptance,"acceptance_passed":all(acceptance.values()),
            "inference_enabled":False,"ss_demodulation_implemented":False,"independent_semantic_evaluation":"not_performed"}


def render_report(result):
    lines=["# PLM-P1 v0.2 数値評価", "", "分割: "+result["split"],"",
           "人工構造の数値回復試験です。独立意味評価ではありません。旧評価seedは使わず、符号seedとチャネルseedを分離して交差させています。",
           "全方式で同じ次元数・結合情報・送信エネルギー・候補辞書・公開カタログを使用。送信正規化の単一gainは全方式へ公開。",
           "v01_fixedは旧復号器を同じ等エネルギー条件で再評価した比較です。v0.1当時の64問の結果と直接同じ母集団ではありません。","",
           "## 主語・目的語の比較", "", "| 条件 | 方式 | 回復 | 誤回復 | 保留 | 負例誤受理 |", "|---|---|---:|---:|---:|---:|"]
    for a in result["aggregates"]:
        lines.append(f"| {a['condition']} | {a['method']} | {a['correct']}/{a['positive_queries']} | {a['wrong']} | {a['abstained']} | {a['false_accepts']}/{a['negative_queries']} |")
    lines += ["", "## 採用方式のseed別変動", "", "同じ試行内の照会は独立ではありません。以下は観測された範囲で、母集団の信頼区間や無誤り保証ではありません。", "",
              "| 条件 | 符号seed別回復率 min–max | 符号seed別誤受理率 min–max | チャネルseed別回復率 min–max |", "|---|---:|---:|---:|"]
    for a in result["aggregates"]:
        if a["method"]!=result["selected_method"]: continue
        cr=[r["recovery_rate"] for r in a["by_code_seed"]]
        cf=[r["false_accept_rate"] for r in a["by_code_seed"]]
        hr=[r["recovery_rate"] for r in a["by_channel_seed"]]
        lines.append(f"| {a['condition']} | {min(cr):.2%}–{max(cr):.2%} | {min(cf):.2%}–{max(cf):.2%} | {min(hr):.2%}–{max(hr):.2%} |")
    s=result["state_evaluation"]
    lines += ["", "## 状態を含む別評価", "", f"7-slot回復: {s['correct_slots']}/{s['positive_slots']}、誤回復{s['wrong_slots']}、保留{s['abstained_slots']}。出来事単位の全7-slot一致: {s['exact_frames']}/{s['frames']}。状態・述語の欠落真値負例誤受理: {s['false_accepts']}/{s['negative_queries']}。",
              "主語・目的語だけの高い回復率をRelation全体の完全回復と混同しないための別集計です。訂正target_clauseは別の連携テストで確認します。", "", "## パイロット位相同期", "",
              "2048成分中128をパイロットへ割当て（6.25%）、残り1920がデータ。25%観測時はデータ観測数がさらに減ります。全フレーム送信エネルギーは57344。",
              "| 方式 | 回復 | 誤回復 | 保留 | 負例誤受理 |", "|---|---:|---:|---:|---:|"]
    for a in result["pilot_evaluation"]["aggregates"]:
        lines.append(f"| {a['method']} | {a['correct']}/{a['positive_queries']} | {a['wrong']} | {a['abstained']} | {a['false_accepts']}/{a['negative_queries']} |")
    pilot=result["pilot_evaluation"]
    lines += ["",f"位相推定成功: {pilot['phase_aligned_trials']}/{pilot['phase_estimation_trials']}。絶対位相誤差平均 {pilot['mean_absolute_phase_error_rad']} rad、最大 {pilot['max_absolute_phase_error_rad']} rad。",
              "oracleは真の回転角を使う評価用参照のみ。実際の推定経路には渡していません。aligned参照は同じパイロット予算で回転なしの別チャネル参照です。",
              "位相角はチャネルseedに対応する4種類（開発は2種類）で、全角度・周波数ずれ・時刻ずれを網羅した試験ではありません。", "", "## 受入判定", ""]
    lines += [f"- {name}: {'PASS' if passed else 'FAIL'}" for name,passed in result["acceptance"].items()]
    lines += ["", "## 限界", "",
              "判定alphaはガウス近似に基づく工学的設定で、回復スコアは確率ではありません。カタログ外の干渉、低次元、過負荷では保留・誤りが起こり得ます。",
              "公開カタログは真のslot割当てではありませんが追加のモデル知識です。無事前知識での改善と主張しません。",
              "SS拡散・逆拡散、遅延・周波数同期、物理時間軸、独立意味評価は未実装。推論は引き続き無効です。", ""]
    return "\n".join(lines)
