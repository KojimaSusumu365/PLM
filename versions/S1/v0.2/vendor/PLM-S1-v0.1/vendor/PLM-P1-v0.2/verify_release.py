"""Re-run all generations, actual CLI paths and frozen first evaluation."""
import os
os.environ.setdefault("OPENBLAS_NUM_THREADS","1")
import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from freeze_release import verify
from plm_p1_v02 import BASELINE
from plm_p1.core import digest
from plm_p1.__main__ import load_json,write_json

ROOT=Path(__file__).resolve().parent


def inventory(root):
    return {p.relative_to(root).as_posix():sha256(p.read_bytes()).hexdigest() for p in sorted(root.rglob("*")) if p.is_file()}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--out-dir",default=str(ROOT/"verification"))
    args=parser.parse_args()
    out=Path(args.out_dir).resolve()
    out.mkdir(parents=True,exist_ok=True)
    frozen=verify()
    if not frozen["valid"]: raise SystemExit("Frozen sources changed: "+str(frozen))
    before=inventory(BASELINE)
    old_manifest=load_json(BASELINE/"RELEASE_MANIFEST.json")["files"]
    old_match={k:v for k,v in before.items() if k!="RELEASE_MANIFEST.json"}==old_manifest
    if not old_match: raise SystemExit("v0.1 dependency hash/inventory mismatch")
    def run(arguments,cwd,name,expected_exit=0):
        r=subprocess.run([sys.executable,"-B",*arguments],cwd=cwd,capture_output=True,encoding="utf-8",errors="replace")
        log=r.stdout+r.stderr
        (out/name).write_text(log,encoding="utf-8")
        if r.returncode!=expected_exit: raise SystemExit("Unexpected exit "+str(r.returncode)+" in "+name+"\n"+log)
        return log
    log=run(["-m","unittest","discover","-s","tests","-v"],ROOT,"P1_V02_TEST_OUTPUT.txt")
    count=int(re.search(r"Ran (\d+) tests?",log).group(1))
    if "skipped=" in log or "FAILED" in log: raise SystemExit("Skipped/failed tests")
    print("v0.2 tests",count,"passed",flush=True)
    # v0.1 intentionally exits 1 for its known numerical gate, not a functional failure.
    run(["verify_release.py","--out-dir",str(out/"P1_V01_REPLAY")],BASELINE,"P1_V01_REPLAY_OUTPUT.txt",expected_exit=1)
    old=load_json(out/"P1_V01_REPLAY/VERIFICATION_RESULTS.json")
    failed=[k for k,v in old["checks"].items() if not v]
    old_accepted=failed==["numerical_acceptance_passed"] and [k for k,v in old["numerical_acceptance"].items() if not v]==["masked_recovery_at_least_95pct"] and old["total_tests"]==377
    if not old_accepted: raise SystemExit("Unexpected v0.1 regression failure")
    print("unchanged v0.1/R1/C2 377 tests replayed; known old performance failure preserved",flush=True)
    run(["evaluate.py","--split","evaluation","--out-dir",str(out/"P1_V02_EVALUATION_REPLAY")],ROOT,"P1_V02_EVALUATION_REPLAY_OUTPUT.txt")
    result=load_json(out/"P1_V02_EVALUATION_REPLAY/EVALUATION_RESULTS.json")
    first=load_json(ROOT/"FIRST_EVALUATION.json")
    cli={}
    with tempfile.TemporaryDirectory(prefix="plm-p1-v02-cli-") as directory:
        temp=Path(directory)
        packet=temp/"packet.json"
        recovery=temp/"recovery.json"
        run(["-m","plm_p1_v02","encode","--input",str(ROOT/"examples/INPUT_FRAMES.json"),"--out",str(packet)],ROOT,"CLI_ENCODE.txt")
        run(["-m","plm_p1_v02","validate-packet","--packet",str(packet)],ROOT,"CLI_VALIDATE.txt")
        base=["-m","plm_p1_v02","decode","--catalogue",str(ROOT/"examples/PUBLIC_CATALOGUE.json"),"--expected-codebook",str(ROOT/"examples/CODEBOOK.json"),"--query",str(ROOT/"examples/QUERY.json"),"--out",str(recovery)]
        truth=load_json(ROOT/"examples/INPUT_FRAMES.json")[0]["slots"]["subject"]
        for name,input_path in (("full",packet),("masked",ROOT/"examples/OBSERVATION_PACKET.json"),("pilot",ROOT/"examples/PILOT_PACKET.json")):
            run(base+["--packet",str(input_path)],ROOT,"CLI_DECODE_"+name+".txt")
            r=load_json(recovery)
            cli["cli_"+name+"_roundtrip"]=r["selected"]==truth and r["eligible_for_inference"] is False
        bad=load_json(ROOT/"examples/QUERY.json")
        bad["gold"]=truth
        write_json(temp/"bad.json",bad)
        rejected=subprocess.run([sys.executable,"-B","-m","plm_p1_v02","decode","--packet",str(packet),"--query",str(temp/"bad.json"),"--catalogue",str(ROOT/"examples/PUBLIC_CATALOGUE.json"),"--expected-codebook",str(ROOT/"examples/CODEBOOK.json"),"--out",str(temp/"must-not-exist.json")],cwd=ROOT,capture_output=True)
        cli["gold_query_rejected"]=rejected.returncode==2 and not (temp/"must-not-exist.json").exists()
    checks={"new_tests_passed":count>0,"legacy_377_tests_and_known_limit_preserved":old_accepted,
            "vendor_177_files_exactly_preserved":old_match and len(before)==177 and before==inventory(BASELINE),
            "source_freeze_valid":verify()["valid"],"first_evaluation_reproduced":digest(result)==first["result_hash"],
            "canonical_first_result_unchanged":digest(load_json(ROOT/"results/EVALUATION_RESULTS.json"))==first["result_hash"],
            "inference_and_ss_disabled":result["inference_enabled"] is False and result["ss_demodulation_implemented"] is False,
            **cli,"numerical_acceptance_passed":result["acceptance_passed"]}
    report={"version":"PLM-P1 v0.2","tests":{"P1_v02":count,"P1_v01":99,"R1":92,"C2":186},"total_tests":count+377,
            "source_freeze":frozen,"checks":checks,"numerical_acceptance":result["acceptance"],
            "functional_passed":all(v for k,v in checks.items() if k!="numerical_acceptance_passed"),"passed":all(checks.values()),
            "comparison_queries":len(result["rows"]),"pilot_queries":len(result["pilot_evaluation"]["rows"]),"state_queries":len(result["state_evaluation"]["rows"])}
    write_json(out/"VERIFICATION_RESULTS.json",report)
    (out/"VERIFICATION_REPORT.md").write_text(f"# PLM-P1 v0.2 検証\n\n単体・連携テスト: {report['total_tests']}件、skipなし。内訳: {report['tests']}。\n\n機能チェック合格: {report['functional_passed']}。数値受入合格: {checks['numerical_acceptance_passed']}。初回評価の完全再現、v0.1全177ファイルの不変、実際のCLI往復を検証。\n\nv0.1の旧95%目標未達は既知の比較結果として保存しており、新版の成功に書き換えていません。\n",encoding="utf-8")
    print(json.dumps(report,indent=2))
    if not report["passed"]: raise SystemExit(1)


if __name__=="__main__": main()
