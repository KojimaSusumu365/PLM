"""Tests and physical separation of pair learning, reading and generation."""
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
from evaluation_support import ROOT, data, oracle
from plm_l1_v03.algebra import digest
from plm_l1_v03.runtime import Writer
from plm_l1_v03.bridge import fixed_reader, translate, VENDOR


def run(arguments, cwd, output, label, expected=0):
    env = dict(os.environ, OPENBLAS_NUM_THREADS="1", PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1", PYTHONNOUSERSITE="1")
    env.pop("PYTHONPATH", None)
    completed = subprocess.run([sys.executable, "-B", *arguments], cwd=cwd, env=env, capture_output=True, text=True, encoding="utf-8", timeout=180)
    log = completed.stdout + completed.stderr
    (output / (label + ".log")).write_text(log, encoding="utf-8")
    if completed.returncode != expected:
        raise ValueError(label + " failed: " + log[-2000:])
    return completed.stdout, log


def copy_package(source, target, names=None):
    target.mkdir(parents=True)
    for path in sorted(source.glob("*.py")):
        if names is None or path.name in names:
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
    if args.preflight:
        from plm_l1_v03.training import fit
        writer = fit(data("train"), data("lexicon"))
        freeze, claimed, checks = "preflight_not_frozen", None, []
    else:
        freeze = verify_freeze()
        result = json.loads((ROOT / "results" / "EVALUATION.json").read_text(encoding="utf-8"))
        claimed = result.pop("result_digest")
        if digest(result) != claimed or result["freeze_hash"] != freeze:
            raise ValueError("evaluation integrity failure")
        protocol = json.loads((ROOT / "evaluation" / "PROTOCOL.json").read_text(encoding="utf-8"))
        checks = judge(result["results"], protocol)
        if checks != result["checks"] or not all(c["passed"] for c in checks):
            raise ValueError("acceptance failure")
        writer = Writer.load(ROOT / "results" / "writer")
    test_counts = {}
    for label, cwd in (("NEW_TESTS", ROOT), ("V02_TESTS", VENDOR), ("V01_TESTS", VENDOR / "vendor" / "PLM-L1-v0.1")):
        _, log = run(["-m", "unittest", "discover", "-s", "tests", "-v"], cwd, output, label)
        test_counts[label] = int(re.search(r"Ran (\d+) tests", log).group(1))

    # New writer learns with no old package, reader, teacher or weights present.
    writer_only = output / "writer-training-only"
    copy_package(ROOT / "plm_l1_v03", writer_only / "plm_l1_v03")
    for name in ("train.json", "lexicon.json"):
        shutil.copyfile(ROOT / "data" / name, writer_only / name)
    assertion = "from pathlib import Path; import importlib.util; assert not Path('vendor').exists(); assert importlib.util.find_spec('plm_l1') is None; assert importlib.util.find_spec('plm_l1_v02') is None; assert not Path('evaluation.json').exists(); print('writer: no reader, no old teacher, no old weights, no evaluation data')"
    run(["-c", assertion], writer_only, output, "WRITER_TRAIN_BOUNDARY")
    stdout, _ = run(["-m", "plm_l1_v03", "train", "--pairs", "train.json", "--lexicon", "lexicon.json", "--seed", writer.meta["seed"], "--out", "model"], writer_only, output, "WRITER_PAIR_TRAIN")
    if json.loads(stdout)["writer_fingerprint"] != writer.fingerprint:
        raise ValueError("isolated writer differs")

    # Independently demonstrate that the unchanged v0.2 reader also learns only
    # from pairs/lexicon, with its old teacher and generator weights absent.
    reader_only = output / "reader-training-only"
    copy_package(VENDOR / "plm_l1_v02", reader_only / "plm_l1_v02")
    old_core = VENDOR / "vendor" / "PLM-L1-v0.1"
    minimal_old = reader_only / "vendor" / "PLM-L1-v0.1"
    copy_package(old_core / "plm_l1", minimal_old / "plm_l1", {"__init__.py", "__main__.py", "algebra.py", "runtime.py"})
    for name in ("train.json", "lexicon.json"):
        shutil.copyfile(ROOT / "data" / name, reader_only / name)
    assertion = "from pathlib import Path; from plm_l1_v02.compat import VENDOR; import importlib.util; assert not (VENDOR/'results').exists(); assert importlib.util.find_spec('plm_l1.teacher') is None; assert importlib.util.find_spec('plm_l1.oracle') is None; assert not Path('evaluation.json').exists(); print('reader: no teacher, no old weights, no evaluation data')"
    run(["-c", assertion], reader_only, output, "READER_TRAIN_BOUNDARY")
    reader = fixed_reader()
    stdout, _ = run(["-m", "plm_l1_v02", "train", "--pairs", "train.json", "--lexicon", "lexicon.json", "--seed", reader.meta["seed"], "--out", "model"], reader_only, output, "READER_PAIR_TRAIN")
    if json.loads(stdout)["reader_fingerprint"] != reader.fingerprint:
        raise ValueError("isolated reader differs")

    # Generation-only surface contains no training code, corpora, reader or
    # legacy generation implementation. It receives only numerical packets.
    generation_only = output / "generation-only"
    copy_package(ROOT / "plm_l1_v03", generation_only / "plm_l1_v03", {"__init__.py", "__main__.py", "algebra.py", "features.py", "memory.py", "runtime.py"})
    shutil.copytree(writer_only / "model", generation_only / "model")
    assertion = "from pathlib import Path; import importlib.util; assert importlib.util.find_spec('plm_l1_v03.training') is None; assert importlib.util.find_spec('plm_l1_v03.bridge') is None; assert importlib.util.find_spec('plm_l1_v02') is None; assert importlib.util.find_spec('plm_l1') is None; assert not Path('train.json').exists(); print('generation: no reader, no old generator, no training code/data')"
    run(["-c", assertion], generation_only, output, "GENERATION_BOUNDARY")
    interpret, _, _ = oracle()
    texts = ["太郎が花子を助けた。", "花子が太郎を助けた。", "太郎が花子を助けなかった。", "もし太郎が花子を助けなかったら。"]
    demos = []
    for i, text in enumerate(texts):
        source_packet = f"reader-{i}.json"
        run(["-m", "plm_l1_v02", "read", "--model", "model", "--text", text, "--out", source_packet], reader_only, output, f"READ_{i}")
        packet = json.loads((reader_only / source_packet).read_text(encoding="utf-8"))
        bridged = translate(reader, packet, writer)
        if bridged["status"] != "bridged":
            raise ValueError("isolation bridge failed")
        with (generation_only / f"meaning-{i}.json").open("x", encoding="utf-8") as stream:
            stream.write(json.dumps(bridged["packet"], ensure_ascii=False))
        stdout, _ = run(["-m", "plm_l1_v03", "generate", "--model", "model", "--packet", f"meaning-{i}.json", "--goal", "object"], generation_only, output, f"GENERATE_{i}")
        out = json.loads(stdout)
        if out["status"] != "generated" or interpret(out["text"]) != interpret(text):
            raise ValueError("isolated generation changed meaning")
        demos.append({"input": text, "output": out["text"], "meaning_exact": True})
    run(["-m", "plm_l1_v02", "read", "--model", "model", "--text", "未知が花子を助けた。", "--out", "must-not-exist.json"], reader_only, output, "ABSTAIN", expected=2)
    if (reader_only / "must-not-exist.json").exists():
        raise ValueError("abstention emitted packet")

    manifest_checked = False
    manifest_path = ROOT / "RELEASE_MANIFEST.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for name, expected in manifest["files"].items():
            if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != expected:
                raise ValueError("release file changed: " + name)
        manifest_checked = True
    report = {"status": "passed", "preflight": args.preflight, "source_freeze": freeze,
              "result_digest": claimed, "acceptance_checks": len(checks), "test_counts": test_counts,
              "writer_pair_fit_without_reader_teacher_legacy_weights": True,
              "reader_pair_fit_without_teacher_legacy_weights": True,
              "isolated_writer_and_reader_fingerprints_equal": True,
              "generation_without_reader_training_code_or_old_generator": True,
              "isolated_roundtrips": demos, "release_manifest_checked": manifest_checked,
              "full_numeric_rerun_in_this_command": False, "python": sys.version}
    (output / "VERIFICATION.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
