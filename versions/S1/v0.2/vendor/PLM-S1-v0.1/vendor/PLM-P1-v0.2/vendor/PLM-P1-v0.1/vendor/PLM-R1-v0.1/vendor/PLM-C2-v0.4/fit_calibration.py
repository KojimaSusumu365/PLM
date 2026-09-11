import json
from pathlib import Path
from plm_c2.calibration import fit_calibration


if __name__ == "__main__":
    root = Path(__file__).resolve().parent
    model = fit_calibration(root / "data" / "calibration_c2_v04.json")
    (root / "data" / "calibration_v04_model.json").write_text(json.dumps(model, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"samples": model["sample_count"], "bins": model["bins"]}))
