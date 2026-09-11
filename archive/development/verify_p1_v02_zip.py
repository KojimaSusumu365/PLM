"""Verify extracted bytes, execute all tests and CLI; full numerical replay was pre-packaging.

This does NOT claim another full 99k-query numerical replay after extraction.
The complete numerical result and all its sources are instead checked byte for byte.
"""
import os
os.environ.setdefault("OPENBLAS_NUM_THREADS","1")
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile

BASE=Path(__file__).resolve().parents[1]
ROOT=BASE/"work/verify-p1-v02-package/PLM-P1-v0.2"
OUT=BASE/"work/verify-p1-v02-package/verification-repeat"
ORIGINAL=BASE/"outputs/PLM-P1-v0.2"
ZIP=BASE/"outputs/PLM-P1-v0.2.zip"
OUT.mkdir(exist_ok=False)


def load(path): return json.loads(path.read_text(encoding="utf-8"))
def inventory(path): return {p.relative_to(path).as_posix():sha256(p.read_bytes()).hexdigest() for p in sorted(path.rglob("*")) if p.is_file()}
def canonical_hash(value): return sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":"),allow_nan=False).encode("utf-8")).hexdigest()
def run(args,cwd,name,expected=0):
    result=subprocess.run([sys.executable,"-B",*args],cwd=cwd,capture_output=True,encoding="utf-8",errors="replace")
    log=result.stdout+result.stderr
    (OUT/name).write_text(log,encoding="utf-8")
    if result.returncode!=expected: raise SystemExit(name+" unexpected exit\n"+log)
    return log

before=inventory(ROOT)
expected=inventory(ORIGINAL)
if before!=expected: raise SystemExit("Extracted bytes differ")
manifest=load(ROOT/"RELEASE_MANIFEST.json")["files"]
if {k:v for k,v in before.items() if k!="RELEASE_MANIFEST.json"}!=manifest: raise SystemExit("Release manifest mismatch")
run(["freeze_release.py"],ROOT,"SOURCE_FREEZE.txt")
log=run(["-m","unittest","discover","-s","tests","-v"],ROOT,"P1_V02_TESTS.txt")
count=int(re.search(r"Ran (\d+) tests?",log).group(1))
if "skipped=" in log or "FAILED" in log: raise SystemExit("Failed/skipped tests")
legacy=ROOT/"vendor/PLM-P1-v0.1"
run(["verify_release.py","--out-dir",str(OUT/"LEGACY")],legacy,"LEGACY_OUTPUT.txt",expected=1)
old=load(OUT/"LEGACY/VERIFICATION_RESULTS.json")
if old["total_tests"]!=377 or [k for k,v in old["checks"].items() if not v]!=["numerical_acceptance_passed"] or [k for k,v in old["numerical_acceptance"].items() if not v]!=["masked_recovery_at_least_95pct"]:
    raise SystemExit("Unexpected legacy failure")
cli={}
with tempfile.TemporaryDirectory(prefix="plm-p1-v02-extracted-") as directory:
    temp=Path(directory)
    generated=temp/"encoded.json"
    run(["-m","plm_p1_v02","encode","--input",str(ROOT/"examples/INPUT_FRAMES.json"),"--out",str(generated)],ROOT,"CLI_ENCODE.txt")
    for name,packet in (("full",generated),("masked",ROOT/"examples/OBSERVATION_PACKET.json"),("pilot",ROOT/"examples/PILOT_PACKET.json")):
        recovered=temp/(name+".json")
        run(["-m","plm_p1_v02","validate-packet","--packet",str(packet)],ROOT,"CLI_VALIDATE_"+name+".txt")
        run(["-m","plm_p1_v02","decode","--packet",str(packet),"--catalogue",str(ROOT/"examples/PUBLIC_CATALOGUE.json"),"--query",str(ROOT/"examples/QUERY.json"),"--expected-codebook",str(ROOT/"examples/CODEBOOK.json"),"--out",str(recovered)],ROOT,"CLI_DECODE_"+name+".txt")
        r=load(recovered)
        truth=load(ROOT/"examples/INPUT_FRAMES.json")[0]["slots"]["subject"]
        cli[name]=r["selected"]==truth and r["eligible_for_inference"] is False
first=load(ROOT/"FIRST_EVALUATION.json")
evaluation=load(ROOT/"results/EVALUATION_RESULTS.json")
pre=load(ROOT/"verification/VERIFICATION_RESULTS.json")
checks={"all_extracted_bytes_match":before==expected,"release_manifest_matches":True,"frozen_sources_valid":True,
        "all_465_tests_passed":count+old["total_tests"]==465,
        "prepackaging_full_numerical_replay_passed":pre["checks"]["first_evaluation_reproduced"],
        "first_evaluation_hash_preserved":canonical_hash(evaluation)==first["result_hash"],
        "extracted_files_unchanged_by_tests":inventory(ROOT)==before,**{"cli_"+k:v for k,v in cli.items()}}
report={"version":"PLM-P1 v0.2","scope":"ZIP extracted-byte verification plus all tests/CLI; full new numerical replay performed before packaging, not repeated after extraction",
        "total_tests":count+old["total_tests"],"files":len(before),"zip_bytes":ZIP.stat().st_size,"sha256":sha256(ZIP.read_bytes()).hexdigest(),
        "checks":checks,"functional_passed":all(checks.values()),"numerical_acceptance_passed":evaluation["acceptance_passed"]}
(BASE/"outputs/PLM-P1-v0.2-VERIFICATION.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
lines=["# PLM-P1 v0.2 配布ZIP検証", "", f"ZIP全{len(before)}ファイルの内容を配布フォルダと照合し、一致を確認。SHA256: `{report['sha256']}`。", "",
       f"展開後に新P1 {count} + 旧P1 99 + R1 92 + C2 186 = {report['total_tests']}件のテストを実行し合格。通常・部分観測・パイロット信号のCLI往復も実行しました。検証前後で展開したファイルの内容は不変です。", "",
       "v0.2の全数値評価の再実行と初回結果の完全一致確認はZIP作成前に実施しました。ZIP展開後は全数値評価を再計算する代わりに、全ソース・初回数値結果のバイト照合と上記の実行テストを行っています。", "",
       "v0.1の既知の95%回復目標未達は以前と同じ結果で保存・再現されています。新版の数値受入: "+("合格" if evaluation["acceptance_passed"] else "未達あり")+"。", "",
       "独立意味評価とSS型復調本体は未実施。推論は無効です。", ""]
(BASE/"outputs/PLM-P1-v0.2-VERIFICATION.md").write_text("\n".join(lines),encoding="utf-8")
print(json.dumps(report,indent=2))
if not all(checks.values()): raise SystemExit(1)
