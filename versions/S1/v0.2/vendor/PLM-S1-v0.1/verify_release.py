"""All generation tests, immutable dependency, numerical replay and actual CLI."""
import os
os.environ.setdefault("OPENBLAS_NUM_THREADS","1")
os.environ.setdefault("OMP_NUM_THREADS","1")
import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from freeze_release import verify
from plm_s1 import BASELINE
from plm_p1.core import digest
from plm_p1.__main__ import load_json,write_json

ROOT=Path(__file__).resolve().parent


def inventory(root):
    return {p.relative_to(root).as_posix():sha256(p.read_bytes()).hexdigest() for p in sorted(root.rglob("*")) if p.is_file()}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--out-dir",default=str(ROOT/"verification"))
    parser.add_argument("--smoke-only",action="store_true",help="Run all tests/CLI and old numerical subset, but only hash-check the archived full S1 result")
    args=parser.parse_args()
    out=Path(args.out_dir).resolve()
    if args.smoke_only and out==ROOT/"verification": raise SystemExit("Smoke verification must not replace full verification")
    out.mkdir(parents=True,exist_ok=True)
    frozen=verify()
    if not frozen["valid"]: raise SystemExit("Source freeze mismatch: "+str(frozen))
    before=inventory(BASELINE)
    expected=load_json(BASELINE/"RELEASE_MANIFEST.json")["files"]
    if {k:v for k,v in before.items() if k!="RELEASE_MANIFEST.json"}!=expected or len(before)!=260:
        raise SystemExit("Frozen P1 v0.2 inventory/hash mismatch")
    def run(arguments,cwd,filename):
        proc=subprocess.run([sys.executable,"-B",*arguments],cwd=cwd,capture_output=True,encoding="utf-8",errors="replace")
        log=proc.stdout+proc.stderr
        (out/filename).write_text(log,encoding="utf-8")
        if proc.returncode: raise SystemExit("Failed "+filename+"\n"+log)
        return log
    p1v01=BASELINE/"vendor/PLM-P1-v0.1"
    r1=p1v01/"vendor/PLM-R1-v0.1"
    counts={}
    for name,directory in (("S1",ROOT),("P1_v02",BASELINE),("P1_v01",p1v01)):
        log=run(["-m","unittest","discover","-s","tests","-v"],directory,name+"_TEST_OUTPUT.txt")
        if "FAILED" in log or "skipped=" in log: raise SystemExit("Failed/skipped tests in "+name)
        counts[name]=int(re.search(r"Ran (\d+) tests?",log).group(1))
    run(["verify_release.py","--out-dir",str(out/"R1_C2_REPLAY")],r1,"R1_C2_REPLAY_OUTPUT.txt")
    previous=load_json(out/"R1_C2_REPLAY/VERIFICATION_RESULTS.json")
    counts.update(previous["tests"])
    print("tests",counts,"total",sum(counts.values()),flush=True)
    run(["baseline_regression.py","--out",str(out/"P1_V02_REGRESSION.json")],ROOT,"P1_V02_REGRESSION_OUTPUT.txt")
    regression=load_json(out/"P1_V02_REGRESSION.json")
    original=load_json(ROOT/"results/EVALUATION_RESULTS.json")
    first=load_json(ROOT/"FIRST_EVALUATION.json")
    first_intact=digest(original)==first["result_hash"]
    replay_matches=None
    if not args.smoke_only:
        run(["evaluate.py","--split","evaluation","--out-dir",str(out/"S1_EVALUATION_REPLAY")],ROOT,"S1_EVALUATION_REPLAY_OUTPUT.txt")
        replay_matches=digest(load_json(out/"S1_EVALUATION_REPLAY/EVALUATION_RESULTS.json"))==first["result_hash"]
        print("full S1 numerical replay matches",replay_matches,flush=True)
    cli={}
    with tempfile.TemporaryDirectory(prefix="plm-s1-cli-") as directory:
        temp=Path(directory)
        packet=temp/"packet.json"
        run(["-m","plm_s1","encode","--input",str(ROOT/"examples/INPUT_FRAMES.json"),"--codebook",str(ROOT/"examples/CODEBOOK.json"),"--link",str(ROOT/"examples/LINK.json"),"--out",str(packet)],ROOT,"CLI_ENCODE.txt")
        truth=load_json(ROOT/"examples/INPUT_FRAMES.json")[0]["slots"]["subject"]
        for name,path in (("nominal",packet),("partial_shifted_cfo",ROOT/"examples/RECEIVED_CHIP_PACKET.json")):
            output=temp/(name+".json")
            run(["-m","plm_s1","validate-packet","--packet",str(path)],ROOT,"CLI_VALIDATE_"+name+".txt")
            run(["-m","plm_s1","decode","--packet",str(path),"--query",str(ROOT/"examples/QUERY.json"),"--catalogue",str(ROOT/"examples/PUBLIC_CATALOGUE.json"),"--expected-codebook",str(ROOT/"examples/CODEBOOK.json"),"--expected-link",str(ROOT/"examples/LINK.json"),"--out",str(output)],ROOT,"CLI_DECODE_"+name+".txt")
            r=load_json(output)
            cli[name]=r["selected"]==truth and r["eligible_for_inference"] is False and r["spreading_applied"] is True
        bad=load_json(ROOT/"examples/QUERY.json")
        bad["true_phase_rad"]=1.8
        write_json(temp/"bad.json",bad)
        rejected=subprocess.run([sys.executable,"-B","-m","plm_s1","decode","--packet",str(packet),"--query",str(temp/"bad.json"),"--catalogue",str(ROOT/"examples/PUBLIC_CATALOGUE.json"),"--expected-codebook",str(ROOT/"examples/CODEBOOK.json"),"--expected-link",str(ROOT/"examples/LINK.json"),"--out",str(temp/"must-not-exist.json")],cwd=ROOT,capture_output=True)
        cli["truth_query_rejected"]=rejected.returncode==2 and not (temp/"must-not-exist.json").exists()
    checks={"all_generation_tests_passed":sum(counts.values())>465,"r1_c2_regression_preserved":previous["acceptance_passed"] and previous["total_tests"]==278,
            "vendor_260_files_unchanged":before==inventory(BASELINE),"frozen_sources_valid":verify()["valid"],
            "p1_numerical_subset_exact":regression["exact_reference_match"],"first_s1_result_hash_intact":first_intact,
            "inference_disabled":original["inference_enabled"] is False,"ss_scope_is_synthetic_baseband":original["ss_demodulation_implemented"] is True and original["implementation_scope"]=="synthetic_discrete_complex_baseband_only",
            **{"cli_"+k:v for k,v in cli.items()},"numerical_acceptance_passed":original["acceptance_passed"]}
    if not args.smoke_only: checks["full_s1_numerical_replay_matches"]=replay_matches
    functional=all(v for k,v in checks.items() if k!="numerical_acceptance_passed")
    result={"version":"PLM-S1 v0.1","tests":counts,"total_tests":sum(counts.values()),"source_freeze":frozen,"checks":checks,
            "functional_passed":functional,"passed":all(checks.values()),"full_s1_numerical_replay_performed":not args.smoke_only,
            "full_s1_replay_matches":replay_matches,"legacy_numerical_scope":regression["scope"],"numeric_queries":len(original["rows"]),
            "state_queries":len(original["state_evaluation"]["rows"]),"numerical_acceptance":original["acceptance"]}
    write_json(out/"VERIFICATION_RESULTS.json",result)
    text=(f"# PLM-S1 v0.1 検証\n\n単体・連携テスト {result['total_tests']}件合格、skipなし。内訳: {counts}。\n\n"
          f"機能チェック: {functional}。数値受入: {original['acceptance_passed']}。全S1数値再実行の実施: {not args.smoke_only}、初回との一致: {replay_matches}。\n\n"
          "旧P1 v0.2全260ファイルを無変更で検証。旧P1数値評価は12条件×5方式の1 seedペア（1440照会）を再実行して照合し、元の全評価結果はハッシュで保存を確認します。旧P1の全数値評価を毎回再計算したとは主張しません。R1/C2の回帰とCLIも再実行。\n\n"
          "通常信号と25%観測・遅延・周波数ずれを含むS1パケットの実際のCLI往復を確認。真値付き照会は拒否します。独立意味評価、RF実機は未実施、推論は無効です。\n")
    (out/"VERIFICATION_REPORT.md").write_text(text,encoding="utf-8")
    print(json.dumps(result,indent=2))
    if not result["passed"]: raise SystemExit(1)


if __name__=="__main__": main()
