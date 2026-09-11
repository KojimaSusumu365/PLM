"""Tests plus two-stage physical isolation of pair learning and fixed generation."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from evaluate import verify_freeze, judge
from plm_l1_v02.compat import ROOT, VENDOR, digest
from plm_l1_v02.runtime import PairReader
from evaluation_support import interpret


def run(args, cwd, output, name, expected=0):
    env = dict(os.environ, OPENBLAS_NUM_THREADS="1", PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1", PYTHONNOUSERSITE="1")
    env.pop("PYTHONPATH", None)
    result = subprocess.run([sys.executable, "-B", *args], cwd=cwd, env=env, text=True, encoding="utf-8", capture_output=True, timeout=180)
    log = result.stdout + result.stderr
    (output / (name + ".log")).write_text(log, encoding="utf-8")
    if result.returncode != expected:
        raise ValueError(name + " failed: " + log[-2000:])
    return result.stdout, log


def copy_legacy_runtime(target):
    package = target / "plm_l1"
    package.mkdir(parents=True)
    for name in ("__init__.py", "__main__.py", "algebra.py", "runtime.py"):
        shutil.copyfile(VENDOR / "plm_l1" / name, package / name)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    output = Path(args.out).resolve()
    if output.exists():
        raise ValueError("fresh verification output required")
    output.mkdir(parents=True)
    freeze = verify_freeze()
    _, new_log = run(["-m", "unittest", "discover", "-s", "tests", "-v"], ROOT, output, "NEW_TESTS")
    _, old_log = run(["-m", "unittest", "discover", "-s", "tests", "-v"], VENDOR, output, "LEGACY_TESTS")
    test_counts = {"new": int(re.search(r"Ran (\d+) tests", new_log).group(1)), "v01": int(re.search(r"Ran (\d+) tests", old_log).group(1))}
    result = json.loads((ROOT / "results" / "EVALUATION.json").read_text(encoding="utf-8"))
    claimed = result.pop("result_digest")
    if digest(result) != claimed or result["freeze_hash"] != freeze:
        raise ValueError("saved evaluation integrity failed")
    protocol = json.loads((ROOT / "evaluation" / "PROTOCOL.json").read_text(encoding="utf-8"))
    checks = judge(result["results"], protocol)
    if checks != result["checks"] or not all(c["passed"] for c in checks):
        raise ValueError("saved acceptance failed")
    isolated = output / "pair-only"
    (isolated / "plm_l1_v02").mkdir(parents=True)
    for source in (ROOT / "plm_l1_v02").glob("*.py"):
        shutil.copyfile(source, isolated / "plm_l1_v02" / source.name)
    isolated_vendor = isolated / "vendor" / "PLM-L1-v0.1"
    copy_legacy_runtime(isolated_vendor)
    for name in ("train.json", "lexicon.json"):
        shutil.copyfile(ROOT / "data" / name, isolated / name)
    # At this point neither teacher, evaluation files, nor ANY legacy weights
    # are present. Reader fitting must use only the supplied pair/lexicon files.
    assertion = "from pathlib import Path; from plm_l1_v02.compat import VENDOR; import importlib.util; assert not (VENDOR/'results').exists(); assert importlib.util.find_spec('plm_l1.teacher') is None; assert importlib.util.find_spec('plm_l1.oracle') is None; assert not Path('evaluation.json').exists(); print('no teacher, no evaluation data, no legacy weights')"
    run(["-c", assertion], isolated, output, "PAIR_ONLY_BOUNDARY")
    stdout, _ = run(["-m", "plm_l1_v02", "train", "--pairs", "train.json", "--lexicon", "lexicon.json", "--seed", protocol["evaluation_seeds"][0], "--out", "reader"], isolated, output, "PAIR_ONLY_TRAIN")
    fitted = json.loads(stdout)
    expected_reader = PairReader.load(ROOT / "results" / "reader")
    if fitted["reader_fingerprint"] != expected_reader.fingerprint:
        raise ValueError("isolated fit differs from release reader")
    # Add only fixed generator numerical weights after the training check.
    model_dir = isolated_vendor / "results" / "model"
    model_dir.mkdir(parents=True)
    for name in ("model.json", "weights.npz"):
        shutil.copyfile(VENDOR / "results" / "model" / name, model_dir / name)
    generation_only = output / "generation-only"
    copy_legacy_runtime(generation_only)
    (generation_only / "model").mkdir()
    for name in ("model.json", "weights.npz"):
        shutil.copyfile(VENDOR / "results" / "model" / name, generation_only / "model" / name)
    run(["-c", "import importlib.util; assert importlib.util.find_spec('plm_l1_v02') is None; assert importlib.util.find_spec('plm_l1.teacher') is None; assert importlib.util.find_spec('plm_l1.oracle') is None; print('fixed generator only')"], generation_only, output, "GENERATOR_ONLY_BOUNDARY")
    texts = ["太郎が花子を助けた。", "花子が太郎を助けた。", "太郎が花子を助けなかった。", "もし太郎が花子を助けなかったら。"]
    demos = []
    for index, text in enumerate(texts):
        own_packet = f"meaning-{index}.json"
        bridge_packet = f"legacy-{index}.json"
        run(["-m", "plm_l1_v02", "read", "--model", "reader", "--text", text, "--out", own_packet], isolated, output, f"READ_{index}")
        run(["-m", "plm_l1_v02", "bridge", "--model", "reader", "--packet", own_packet, "--out", bridge_packet], isolated, output, f"BRIDGE_{index}")
        shutil.copyfile(isolated / bridge_packet, generation_only / bridge_packet)
        stdout, _ = run(["-m", "plm_l1", "generate", "--model", "model", "--packet", bridge_packet, "--goal", "object_first"], generation_only, output, f"GENERATE_{index}")
        generated = json.loads(stdout)
        if generated["status"] != "generated" or interpret(generated["text"]) != interpret(text):
            raise ValueError("isolated generation changed meaning")
        demos.append({"input": text, "output": generated["text"], "meaning_exact": True})
    run(["-m", "plm_l1_v02", "read", "--model", "reader", "--text", "未知が花子を助けた。", "--out", "must-not-exist.json"], isolated, output, "ABSTAIN", expected=2)
    if (isolated / "must-not-exist.json").exists():
        raise ValueError("abstention emitted packet")
    manifest_path = ROOT / "RELEASE_MANIFEST.json"
    manifest_checked = False
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for name, expected in manifest["files"].items():
            if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != expected:
                raise ValueError("release file changed: " + name)
        manifest_checked = True
    verification = {"status": "passed", "source_freeze": freeze, "result_digest": claimed,
                    "test_counts": test_counts, "acceptance_checks": len(checks),
                    "pair_only_fit_without_teacher_or_old_weights": True, "isolated_fit_fingerprint_equal": True,
                    "fixed_generator_without_new_reader": True, "isolated_roundtrips": demos,
                    "release_manifest_checked": manifest_checked, "full_numeric_rerun_in_this_command": False,
                    "python": sys.version}
    (output / "VERIFICATION.json").write_text(json.dumps(verification, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(verification, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
