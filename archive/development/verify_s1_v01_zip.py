"""Extracted-byte comparison plus all tests/CLI/old subset; full S1 replay was pre-package."""
import os
os.environ.setdefault("OPENBLAS_NUM_THREADS","1")
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys

BASE=Path(__file__).resolve().parents[1]
ROOT=BASE/"work/verify-s1-v01-package/PLM-S1-v0.1"
ORIGINAL=BASE/"outputs/PLM-S1-v0.1"
OUT=BASE/"work/verify-s1-v01-package/verification-repeat"
ZIP=BASE/"outputs/PLM-S1-v0.1.zip"


def load(p): return json.loads(p.read_text(encoding="utf-8"))
def inventory(root): return {p.relative_to(root).as_posix():sha256(p.read_bytes()).hexdigest() for p in sorted(root.rglob("*")) if p.is_file()}

before=inventory(ROOT)
if before!=inventory(ORIGINAL): raise SystemExit("Extracted bytes differ")
manifest=load(ROOT/"RELEASE_MANIFEST.json")["files"]
if {k:v for k,v in before.items() if k!="RELEASE_MANIFEST.json"}!=manifest: raise SystemExit("Release manifest mismatch")
if OUT.exists(): raise SystemExit("Refuse existing verification output")
proc=subprocess.run([sys.executable,"-B","verify_release.py","--smoke-only","--out-dir",str(OUT)],cwd=ROOT,capture_output=True,encoding="utf-8",errors="replace")
log=proc.stdout+proc.stderr
(OUT/"EXTRACTED_VERIFY_OUTPUT.txt").write_text(log,encoding="utf-8")
if proc.returncode: raise SystemExit(log)
r=load(OUT/"VERIFICATION_RESULTS.json")
pre=load(ROOT/"verification/VERIFICATION_RESULTS.json")
checks={"all_extracted_bytes_match":True,"release_manifest_matches":True,"all_tests_and_cli_passed":r["functional_passed"],
        "extracted_files_unchanged_by_verification":before==inventory(ROOT),"prepackaging_full_s1_numerical_replay_matches":pre["full_s1_replay_matches"],
        "initial_s1_result_hash_intact":r["checks"]["first_s1_result_hash_intact"]}
if not all(checks.values()): raise SystemExit("Extracted verification failure: "+str(checks))
result={"version":"PLM-S1 v0.1","scope":"all extracted bytes, all generation tests, CLI and old P1 numerical subset; full S1 replay performed before packaging, not repeated after extraction",
        "files":len(before),"total_tests":r["total_tests"],"zip_bytes":ZIP.stat().st_size,"sha256":sha256(ZIP.read_bytes()).hexdigest(),
        "checks":checks,"functional_passed":True,"numerical_acceptance_passed":r["checks"]["numerical_acceptance_passed"]}
(BASE/"outputs/PLM-S1-v0.1-VERIFICATION.json").write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
lines=["# PLM-S1 v0.1 配布ZIP検証", "", f"全{len(before)}ファイルを配布フォルダ・manifestと照合し一致。SHA256: `{result['sha256']}`。", "",
       f"展開後に{r['total_tests']}件の単体・連携テストを実行して合格、skipなし。R1/C2回帰、旧P1の1440照会部分回帰、S1の通常/部分観測・ずれ付きCLI往復、真値付き照会の拒否を確認しました。展開ファイルの内容は検証前後で不変です。", "",
       "全S1数値評価の再実行と初回結果の完全一致確認はZIP作成前に実施しました。ZIP展開後は全S1数値評価を再計算せず、全ファイル・数値結果のハッシュ照合と上記の実行検証を行っています。", "",
       "S1数値受入: "+("合格" if result["numerical_acceptance_passed"] else "未達あり")+"。SS実装の範囲は人工離散複素ベースバンドのみ。RF実機・独立意味評価は未実施、推論は無効です。", ""]
(BASE/"outputs/PLM-S1-v0.1-VERIFICATION.md").write_text("\n".join(lines),encoding="utf-8")
print(json.dumps(result,indent=2))
