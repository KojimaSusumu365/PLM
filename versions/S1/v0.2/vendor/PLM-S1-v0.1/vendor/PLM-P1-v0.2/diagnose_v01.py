"""Known v0.1 evaluation is REGRESSION data now, never a new held-out result."""
import os
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
import json
from pathlib import Path
import numpy as np
from plm_p1_v02 import BASELINE
from plm_p1.core import PhaseCodebook,encode,decode,channel,canonical
from plm_p1.__main__ import write_json
from plm_p1_v02.fixtures import make_frames,entity_candidates,public_catalogue,DOC
from plm_p1_v02.recovery import Receiver

ROOT=Path(__file__).resolve().parent


def main():
    previous=json.loads((BASELINE/"results/EVALUATION_RESULTS.json").read_text(encoding="utf-8"))
    failures=[r for r in previous["rows"] if r["dimension"]==2048 and r["condition"]=="masked_noise" and r["outcome"] in {"abstained","wrong","false_accept"}]
    rows=[]
    frames=make_frames(4)
    candidates=entity_candidates()
    for failure in failures:
        seed,event,role=failure["seed"],failure["event_id"],failure["role"]
        book=PhaseCodebook(2048,"experiment-"+str(seed))
        memory=encode(frames,book)
        y,mask=channel(memory,seed=seed+2048,keep_fraction=.25,noise_std=.15,jitter_std=.1)
        templates={canonical(c):book.key(DOC,event,role)*book.value(c) for c in candidates}
        scores={canonical(c):float(np.real(np.mean(y[mask]*np.conj(templates[canonical(c)][mask])))) for c in candidates}
        ranked=sorted(candidates,key=lambda c:(-scores[canonical(c)],canonical(c)))
        truth=next((f["slots"][role] for f in frames if f["event_id"]==event),None)
        interesting=[truth, next(c for c in ranked if c!=truth)] if truth else ranked[:1]
        contributions=[]
        for candidate in interesting:
            t=templates[canonical(candidate)][mask]
            by_role={}
            self_contribution=0.
            for f in frames:
                for source_role,value in f["slots"].items():
                    component=book.key(DOC,f["event_id"],source_role)*book.value(value)
                    score=float(np.real(np.mean(component[mask]*np.conj(t))))
                    by_role[source_role]=by_role.get(source_role,0.)+score
                    if f["event_id"]==event and source_role==role and value==candidate:
                        self_contribution+=score
            clean=sum(by_role.values())
            contributions.append({"candidate":candidate,"is_truth":candidate==truth,"observed_score":round(scores[canonical(candidate)],8),
                                  "clean_masked_score":round(clean,8),"self_contribution":round(self_contribution,8),
                                  "by_source_role":{k:round(v,8) for k,v in by_role.items()},
                                  "nuisance_contribution":round(sum(v for k,v in by_role.items() if k not in {"subject","object"}),8),
                                  "channel_perturbation_contribution":round(scores[canonical(candidate)]-clean,8)})
        new=Receiver(y,mask,book,public_catalogue()).scores(DOC,event,role,candidates)
        rows.append({"original":failure,"truth":truth,"truth_rank":next((i+1 for i,c in enumerate(ranked) if c==truth),None),
                     "contributions":contributions,"v02_regression_recovery":new,
                     "regression_correct":new["selected"]==truth})
    out=ROOT/"results"
    out.mkdir(exist_ok=True)
    write_json(out/"V01_FAILURE_DIAGNOSIS.json",{"scope":"known regression cases, not fresh evaluation", "rows":rows})
    lines=["# v0.1既知失敗の診断（回帰試験）","","v0.1の評価seedは既知データとして扱います。v0.2の未知データ性能には数えません。","",
           "| seed | 照会 | 元の結果 | 真値順位 | v0.2回帰結果 |","|---:|---|---|---:|---|"]
    for r in rows:
        f=r["original"]
        lines.append(f"| {f['seed']} | {f['event_id']} / {f['role']} | {f['outcome']} / {f['reason']} | {r['truth_rank']} | {r['v02_regression_recovery']['status']}（照合 {'一致' if r['regression_correct'] else '不一致'}） |")
    lines += ["","各照会の真値と最大競合候補について、観測マスク上のスコアを、元の役割別干渉とチャネル摂動へ分解しました。詳細は同名JSON。",
              "保留時のtop_scoreを無条件に真値のスコアと解釈せず、96候補全部の順位を再計算しています。",
              "状態情報を削除せず、その公開候補が張る部分空間を観測成分上で除きます。真の割当てや干渉の正解寄与は評価者の診断にだけ使い、復号器には渡していません。",""]
    (out/"V01_FAILURE_DIAGNOSIS.md").write_text("\n".join(lines),encoding="utf-8")
    print(json.dumps([{ "seed":r["original"]["seed"],"event":r["original"]["event_id"],"truth_rank":r["truth_rank"],"regression_correct":r["regression_correct"],"contributions":r["contributions"]} for r in rows],indent=2))


if __name__=="__main__": main()
