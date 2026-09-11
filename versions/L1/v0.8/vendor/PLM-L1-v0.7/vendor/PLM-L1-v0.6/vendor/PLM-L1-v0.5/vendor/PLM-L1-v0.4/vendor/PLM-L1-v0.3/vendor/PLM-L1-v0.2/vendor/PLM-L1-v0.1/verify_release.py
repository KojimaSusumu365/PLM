"""Local verification: frozen sources, tests, saved numeric results and isolated CLI."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from evaluate import verify_freeze, judge
from plm_l1.algebra import digest
from plm_l1.runtime import Model
from plm_l1.oracle import interpret

ROOT = Path(__file__).resolve().parent


def run(args, cwd, output, name, expected=0):
    environment = dict(os.environ, OPENBLAS_NUM_THREADS="1", PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1", PYTHONNOUSERSITE="1")
    environment.pop("PYTHONPATH", None)
    result = subprocess.run([sys.executable, "-B", *args], cwd=cwd, env=environment, text=True, encoding="utf-8", capture_output=True, timeout=180)
    (output / (name + ".log")).write_text(result.stdout + result.stderr, encoding="utf-8")
    if result.returncode != expected:
        raise ValueError(name + " failed: " + result.stderr[-1500:])
    return result.stdout


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    output = Path(args.out).resolve()
    if output.exists():
        raise ValueError("output directory already exists")
    output.mkdir(parents=True)
    freeze = verify_freeze()
    tests = run(["-m", "unittest", "discover", "-s", "tests", "-v"], ROOT, output, "UNIT_TESTS")
    result = json.loads((ROOT / "results" / "EVALUATION.json").read_text(encoding="utf-8"))
    claimed_digest = result.pop("result_digest")
    if digest(result) != claimed_digest or result["freeze_hash"] != freeze:
        raise ValueError("saved evaluation integrity failed")
    protocol = json.loads((ROOT / "evaluation" / "PROTOCOL.json").read_text(encoding="utf-8"))
    checks = judge(result["results"], protocol)
    if checks != result["checks"] or not all(x["passed"] for x in checks):
        raise ValueError("saved evaluation acceptance failed")
    isolated = output / "isolated"
    package = isolated / "plm_l1"
    package.mkdir(parents=True)
    for name in ("__init__.py", "__main__.py", "algebra.py", "runtime.py"):
        shutil.copyfile(ROOT / "plm_l1" / name, package / name)
    run(["-c", "import importlib.util; assert importlib.util.find_spec('plm_l1.teacher') is None; assert importlib.util.find_spec('plm_l1.oracle') is None; assert importlib.util.find_spec('plm_l1.training') is None; print('teacher, oracle, training unavailable')"], isolated, output, "ISOLATION")
    model_path = str(ROOT / "results" / "model")
    sentences = ["太郎が花子を助けた。", "花子が太郎を褒めた。", "太郎が花子を助けなかった。", "もし太郎が花子を助けなかったら。"]
    demos = []
    for index, text in enumerate(sentences):
        packet_path = isolated / f"packet-{index}.json"
        read = json.loads(run(["-m", "plm_l1", "read", "--model", model_path, "--text", text, "--out", str(packet_path)], isolated, output, f"CLI_READ_{index}"))
        generated = json.loads(run(["-m", "plm_l1", "generate", "--model", model_path, "--packet", str(packet_path), "--goal", "object_first"], isolated, output, f"CLI_GENERATE_{index}"))
        if read["status"] != "read" or generated["status"] != "generated" or interpret(generated["text"]) != interpret(text):
            raise ValueError("isolated meaning preservation failed")
        demos.append({"input": text, "output": generated["text"], "meaning_exact": True})
    missing_path = isolated / "must-not-exist.json"
    run(["-m", "plm_l1", "read", "--model", model_path, "--text", "未知が花子を助けた。", "--out", str(missing_path)], isolated, output, "CLI_ABSTAIN", expected=2)
    if missing_path.exists():
        raise ValueError("abstention emitted a packet")
    release_path = ROOT / "RELEASE_MANIFEST.json"
    release_checked = False
    if release_path.exists():
        manifest = json.loads(release_path.read_text(encoding="utf-8"))
        for name, expected in manifest["files"].items():
            if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != expected:
                raise ValueError("release file changed: " + name)
        release_checked = True
    verification = {"status": "passed", "source_freeze": freeze, "result_digest": claimed_digest,
                    "acceptance_checks": len(checks), "unit_tests": 47, "isolated_cli_roundtrips": len(demos),
                    "unknown_input_cli_exit": 2, "release_manifest_checked": release_checked,
                    "numeric_full_evaluation_rerun_in_this_command": False, "demos": demos,
                    "python": sys.version, "executable": sys.executable}
    (output / "VERIFICATION.json").write_text(json.dumps(verification, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(verification, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
