"""Test suites, fixed-result integrity and physically isolated learning/generation."""
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
from evaluation_support import ROOT, V05, V04, V03, V02, train_for, data, interpret, text_goal
from plm_l1_v06.algebra import digest
from plm_l1_v06.runtime import Model


def run(arguments, cwd, output, label, expected=0):
    env = dict(os.environ, OPENBLAS_NUM_THREADS="1", PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1", PYTHONNOUSERSITE="1")
    env.pop("PYTHONPATH", None)
    completed = subprocess.run([sys.executable, "-B", *arguments], cwd=cwd, env=env, capture_output=True, text=True, encoding="utf-8", timeout=180)
    log = completed.stdout + completed.stderr
    (output / (label + ".log")).write_text(log, encoding="utf-8")
    if completed.returncode != expected:
        raise ValueError(label + " failed: " + log[-2000:])
    return completed.stdout, log


def copy_package(source, target, excluded=()):
    target.mkdir(parents=True)
    for path in sorted(source.glob("*.py")):
        if path.name not in excluded:
            shutil.copyfile(path, target / path.name)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("--preflight", action="store_true")
    args = parser.parse_args()
    output = Path(args.out).resolve()
    if output.exists():
        raise ValueError("fresh verification directory required")
    output.mkdir(parents=True)
    protocol = json.loads((ROOT / "evaluation" / "PROTOCOL.json").read_text(encoding="utf-8"))
    if args.preflight:
        from plm_l1_v06.training import fit
        model = fit(train_for(protocol["folds"][0]), data("lexicon"), seed=protocol["development_seeds"][0])
        freeze, claimed, checks = "preflight_not_frozen", None, []
    else:
        freeze = verify_freeze()
        result = json.loads((ROOT / "results" / "EVALUATION.json").read_text(encoding="utf-8"))
        claimed = result.pop("result_digest")
        if digest(result) != claimed or result["freeze_hash"] != freeze:
            raise ValueError("evaluation integrity failure")
        checks = judge(result, protocol)
        if checks != result["checks"] or not all(c["passed"] for c in checks):
            raise ValueError("acceptance failure")
        model = Model.load(ROOT / "results" / "model")
        first = result["standard"][0]["methods"]["split_proof"]
        if first["fingerprint"] != model.fingerprint:
            raise ValueError("saved model differs from evaluation")
    test_counts = {}
    for label, cwd in (("NEW_TESTS", ROOT), ("V05_TESTS", V05), ("V04_TESTS", V04), ("V03_TESTS", V03), ("V02_TESTS", V02), ("V01_TESTS", V02 / "vendor" / "PLM-L1-v0.1")):
        _, log = run(["-m", "unittest", "discover", "-s", "tests", "-v"], cwd, output, label)
        test_counts[label] = int(re.search(r"Ran (\d+) tests", log).group(1))

    # Same 432 training pairs and initial lexicon, no old packages or evaluators.
    training_only = output / "pair-training-only"
    copy_package(ROOT / "plm_l1_v06", training_only / "plm_l1_v06")
    shutil.copyfile(ROOT / "data" / "folds" / protocol["folds"][0] / "train.json", training_only / "train.json")
    shutil.copyfile(ROOT / "data" / "lexicon.json", training_only / "lexicon.json")
    assertion = "from pathlib import Path; import importlib.util; assert not Path('vendor').exists(); assert all(importlib.util.find_spec(n) is None for n in ('plm_l1','plm_l1_v02','plm_l1_v03','plm_l1_v04','plm_l1_v05','evaluation_support')); assert not Path('evaluation.json').exists(); print('pair learner: no legacy model, teacher or evaluation corpus')"
    run(["-c", assertion], training_only, output, "PAIR_TRAIN_BOUNDARY")
    stdout, _ = run(["-m", "plm_l1_v06", "train", "--pairs", "train.json", "--lexicon", "lexicon.json", "--seed", model.meta["seed"], "--dimension", str(model.meta["dimension"]), "--out", "model"], training_only, output, "PAIR_TRAIN")
    if json.loads(stdout)["fingerprint"] != model.fingerprint:
        raise ValueError("isolated training differs")

    # Generation executable has neither reader.py nor training.py. Shared
    # numerical memories and feature/codec helpers remain: this is not proof
    # of absent reader-related knowledge or of all-symbolic-code removal.
    generation_only = output / "generation-only"
    copy_package(ROOT / "plm_l1_v06", generation_only / "plm_l1_v06", {"reader.py", "training.py"})
    shutil.copytree(training_only / "model", generation_only / "model")
    assertion = "from pathlib import Path; import importlib.util; assert all(importlib.util.find_spec(n) is None for n in ('plm_l1_v06.reader','plm_l1_v06.training','plm_l1_v05','plm_l1_v04','plm_l1_v03','plm_l1_v02','plm_l1','evaluation_support')); assert not Path('train.json').exists(); print('generation: no reader/training entrypoint, legacy package or corpus; shared weights remain')"
    run(["-c", assertion], generation_only, output, "GENERATION_BOUNDARY")
    demos = []
    texts = ("花子を太郎が助けなかった。", "もし花子を太郎が助けなかったら。", "太郎を花子が助けなかった。", "太郎が花子を助けた。")
    for i, text in enumerate(texts):
        packet_name = f"meaning-{i}.json"
        run(["-m", "plm_l1_v06", "read", "--model", "model", "--text", text, "--out", packet_name], training_only, output, f"READ_{i}")
        packet = json.loads((training_only / packet_name).read_text(encoding="utf-8"))
        if set(packet) != {"schema", "model_fingerprint", "dimension", "real", "imag", "eligible_for_inference"}:
            raise ValueError("non-numerical payload leaked")
        shutil.copyfile(training_only / packet_name, generation_only / packet_name)
        stdout, _ = run(["-m", "plm_l1_v06", "generate", "--model", "model", "--packet", packet_name, "--goal", "object"], generation_only, output, f"GENERATE_{i}")
        out = json.loads(stdout)
        if out["status"] != "generated" or interpret(out["text"]) != interpret(text) or text_goal(out["text"]) != "object":
            raise ValueError("isolated generation changed meaning or goal")
        demos.append({"input_for_verifier_only": text, "output": out["text"], "meaning_and_goal_exact": True})
    # No feature selection/tree induction is invoked during inference.
    assertion = "import json; from unittest.mock import patch; from plm_l1_v06.runtime import Model; m=Model.load('model'); p=json.load(open('meaning-0.json',encoding='utf-8')); guard=patch('plm_l1_v06.banked.dependency_leaves',side_effect=AssertionError('runtime retraining')); guard.start(); assert m.generate(p,'object')['status']=='generated'; print('no runtime dependency learner call')"
    run(["-c", assertion], generation_only, output, "NO_RUNTIME_FEATURE_LEARNING")
    run(["-m", "plm_l1_v06", "read", "--model", "model", "--text", "未知が花子を助けた。", "--out", "must-not-exist.json"], training_only, output, "ABSTAIN", expected=2)
    if (training_only / "must-not-exist.json").exists():
        raise ValueError("abstention emitted packet")

    # Exercise the repaired low-dimensional contract through the ordinary CLI
    # in a directory without old code, not only in-process test doubles.
    run(["-m", "plm_l1_v06", "train", "--pairs", "train.json", "--lexicon", "lexicon.json", "--seed", "parts-stress-0", "--dimension", "128", "--memory-mode", "single", "--out", "low-model"], training_only, output, "LOW_DIMENSION_TRAIN")
    low_cases = []
    for i, text in enumerate(("花子が健太を褒めた。", "健太を花子が褒めた。")):
        filename = f"low-must-not-exist-{i}.json"
        stdout, _ = run(["-m", "plm_l1_v06", "read", "--model", "low-model", "--text", text, "--out", filename], training_only, output, f"LOW_DIMENSION_ABSTAIN_{i}", expected=2)
        low = json.loads(stdout)
        if low["reason"] != "meaning_signal_unrecoverable" or (training_only / filename).exists():
            raise ValueError("low-dimensional read contract failed")
        low_cases.append({"input": text, "mode": "single_legacy_equations_regression", "status": low["status"], "reason": low["reason"], "packet_file_absent": True})

    manifest_checked = False
    manifest_path = ROOT / "RELEASE_MANIFEST.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        actual_files = {p.relative_to(ROOT).as_posix() for p in ROOT.rglob("*") if p.is_file() and p != manifest_path and "__pycache__" not in p.parts and p.relative_to(ROOT).parts[0] != "work"}
        if actual_files != set(manifest["files"]):
            raise ValueError("release inventory changed")
        for name, expected in manifest["files"].items():
            if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != expected:
                raise ValueError("release file changed: " + name)
        manifest_checked = True
    report = {"status": "passed", "preflight": args.preflight, "source_freeze": freeze,
              "result_digest": claimed, "acceptance_checks": len(checks), "test_counts": test_counts,
              "pair_training_without_legacy_teacher_or_evaluation_data": True,
              "isolated_model_fingerprint_equal": True, "model_fingerprint": model.fingerprint,
              "generation_without_reader_or_training_entrypoint_or_corpora": True,
              "numerical_packet_only_transfer": True, "no_runtime_feature_learning": True,
              "known_low_dimension_cli_regressions": low_cases,
              "boundary_limit": "Shared full numerical model and feature helpers remain in generation-only environment.",
              "isolated_roundtrips": demos, "release_manifest_checked": manifest_checked,
              "full_numeric_rerun_in_this_command": False, "python": sys.version}
    (output / "VERIFICATION.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
