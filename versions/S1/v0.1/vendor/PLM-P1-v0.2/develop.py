"""Development-only comparisons. Does NOT read or use held-out evaluation seeds."""
import os
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")
import argparse
from dataclasses import asdict
import json
from pathlib import Path
from plm_p1_v02.experiment import trial, aggregates, AdaptivePolicy

ROOT = Path(__file__).resolve().parent
CONDITIONS = [dict(name=n, events=e, keep_fraction=k, noise_std=noise, phase_offset=0., jitter_std=j)
              for n,e,k,noise,j in [("nominal",4,1.,0.,0.),("masked_noise",4,.25,.15,.1),("higher_load",12,.125,.5,.3)]]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="results/DEVELOPMENT_INITIAL.json")
    args = parser.parse_args()
    rows, budgets = [], []
    for condition in CONDITIONS:
        for code_seed in range(21001, 21005):
            for channel_seed in (81001, 81002):
                r, b = trial(code_seed, channel_seed, condition)
                rows.extend(r)
                budgets.append(dict(condition=condition["name"], code_seed=code_seed, channel_seed=channel_seed, codecs=b))
        print(condition["name"], json.dumps([{k:v for k,v in a.items() if not k.startswith("by_")} for a in aggregates(rows) if a["condition"] == condition["name"]]), flush=True)
    result = {"split":"development", "code_seeds":list(range(21001,21005)), "channel_seeds":[81001,81002], "policy":asdict(AdaptivePolicy()), "conditions":CONDITIONS,
              "aggregates":aggregates(rows), "budgets":budgets, "rows":rows, "note":"Internal synthetic development, not independent semantic evaluation"}
    path = ROOT / args.out
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as f:
        json.dump(result,f,ensure_ascii=False,indent=2)
        f.write("\n")


if __name__ == "__main__":
    main()
