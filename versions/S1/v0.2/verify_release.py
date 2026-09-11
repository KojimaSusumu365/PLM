"""All generation tests, preserved package hashes, numerical replay and real CLI."""
import os
os.environ.setdefault('OPENBLAS_NUM_THREADS','1')
os.environ.setdefault('OMP_NUM_THREADS','1')
import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from freeze_release import verify
from plm_s1_v02 import BASELINE
from plm_p1.core import digest
from plm_p1.__main__ import load_json,write_json

ROOT=Path(__file__).resolve().parent


def inventory(root):
    return {p.relative_to(root).as_posix():sha256(p.read_bytes()).hexdigest() for p in sorted(root.rglob('*')) if p.is_file()}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--out-dir',default=str(ROOT/'verification'))
    parser.add_argument('--smoke-only',action='store_true',help='Skip only full NEW S1 v0.2 numerical replay; run all tests/CLI and both old numeric subsets')
    args=parser.parse_args()
    out=Path(args.out_dir).resolve()
    if args.smoke_only and out==ROOT/'verification': raise SystemExit('Do not replace full verification with smoke result')
    if (out/'VERIFICATION_RESULTS.json').exists(): raise SystemExit('Refuse existing verification result')
    out.mkdir(parents=True,exist_ok=True)
    frozen=verify()
    if not frozen['valid']: raise SystemExit('Source freeze invalid: '+str(frozen))
    before=inventory(BASELINE)
    if len(before)!=330 or {k:v for k,v in before.items() if k!='RELEASE_MANIFEST.json'}!=load_json(BASELINE/'RELEASE_MANIFEST.json')['files']:
        raise SystemExit('Frozen S1 v0.1 inventory mismatch')
    def run(arguments,cwd,filename):
        proc=subprocess.run([sys.executable,'-B',*arguments],cwd=cwd,capture_output=True,encoding='utf-8',errors='replace')
        log=proc.stdout+proc.stderr
        (out/filename).write_text(log,encoding='utf-8')
        if proc.returncode: raise SystemExit('Failed '+filename+'\n'+log)
        return log
    log=run(['-m','unittest','discover','-s','tests','-v'],ROOT,'S1_V02_TEST_OUTPUT.txt')
    if 'FAILED' in log or 'skipped=' in log: raise SystemExit('Failed/skipped new tests')
    new_count=int(re.search(r'Ran (\d+) tests?',log).group(1))
    run(['verify_release.py','--smoke-only','--out-dir',str(out/'LEGACY_REPLAY')],BASELINE,'LEGACY_REPLAY_OUTPUT.txt')
    previous=load_json(out/'LEGACY_REPLAY/VERIFICATION_RESULTS.json')
    counts={'S1_v02':new_count,**{('S1_v01' if k=='S1' else k):v for k,v in previous['tests'].items()}}
    print('tests',counts,'total',sum(counts.values()),flush=True)
    run(['baseline_regression.py','--out',str(out/'S1_V01_REGRESSION.json')],ROOT,'S1_V01_REGRESSION_OUTPUT.txt')
    regression=load_json(out/'S1_V01_REGRESSION.json')
    original=load_json(ROOT/'results/EVALUATION_RESULTS.json')
    first=load_json(ROOT/'FIRST_EVALUATION.json')
    replay_matches=None
    if not args.smoke_only:
        run(['evaluate.py','--split','evaluation','--out-dir',str(out/'S1_V02_EVALUATION_REPLAY')],ROOT,'S1_V02_EVALUATION_REPLAY_OUTPUT.txt')
        replay_matches=digest(load_json(out/'S1_V02_EVALUATION_REPLAY/EVALUATION_RESULTS.json'))==first['result_hash']
        print('full S1 v0.2 numerical replay matches',replay_matches,flush=True)
    cli={}
    with tempfile.TemporaryDirectory(prefix='plm-s1-v02-cli-') as directory:
        temp=Path(directory)
        packet=temp/'packet.json'
        run(['-m','plm_s1_v02','encode','--input',str(ROOT/'examples/INPUT_FRAMES.json'),'--codebook',str(ROOT/'examples/CODEBOOK.json'),'--link',str(ROOT/'examples/LINK.json'),'--out',str(packet)],ROOT,'CLI_ENCODE.txt')
        common=['--query',str(ROOT/'examples/QUERY.json'),'--catalogue',str(ROOT/'examples/PUBLIC_CATALOGUE.json'),'--expected-codebook',str(ROOT/'examples/CODEBOOK.json'),'--expected-link',str(ROOT/'examples/LINK.json')]
        truth=load_json(ROOT/'examples/INPUT_FRAMES.json')[0]['slots']['subject']
        for name,path in (('nominal',packet),('partial_alias',ROOT/'examples/RECEIVED_CHIP_PACKET.json')):
            output=temp/(name+'.json')
            run(['-m','plm_s1_v02','validate-packet','--packet',str(path)],ROOT,'CLI_VALIDATE_'+name+'.txt')
            run(['-m','plm_s1_v02','decode','--packet',str(path),*common,'--out',str(output)],ROOT,'CLI_DECODE_'+name+'.txt')
            r=load_json(output)
            cli[name]=r['selected']==truth and r['eligible_for_inference'] is False
        bad=load_json(packet)
        bad['true_cfo_hz']=1.061538
        bad['payload_hash']=digest({k:v for k,v in bad.items() if k!='payload_hash'})
        write_json(temp/'bad.json',bad)
        for name,path in (('truth',temp/'bad.json'),('old_wire',BASELINE/'examples/RECEIVED_CHIP_PACKET.json')):
            output=temp/(name+'-must-not-exist.json')
            proc=subprocess.run([sys.executable,'-B','-m','plm_s1_v02','decode','--packet',str(path),*common,'--out',str(output)],cwd=ROOT,capture_output=True)
            cli[name+'_rejected']=proc.returncode==2 and not output.exists()
    checks={'all_new_tests_passed':new_count>=63,'all_legacy_tests_passed':previous['functional_passed'] and previous['total_tests']==556,
            'legacy_330_files_unchanged':before==inventory(BASELINE),'source_freeze_valid':verify()['valid'],
            'legacy_s1_subset_exact':regression['exact_reference_match'],'legacy_p1_subset_exact':previous['checks']['p1_numerical_subset_exact'],
            'initial_result_hash_intact':digest(original)==first['result_hash'],'inference_disabled':original['inference_enabled'] is False,
            'implementation_scope_correct':original['implementation_scope']=='synthetic_discrete_complex_baseband_only',
            **{'cli_'+k:v for k,v in cli.items()},'numerical_acceptance_passed':original['acceptance_passed']}
    if not args.smoke_only: checks['full_new_numerical_replay_matches']=replay_matches
    functional=all(v for k,v in checks.items() if k!='numerical_acceptance_passed')
    result={'version':'PLM-S1 v0.2','tests':counts,'total_tests':sum(counts.values()),'checks':checks,'source_freeze':frozen,
            'functional_passed':functional,'passed':all(checks.values()),'full_numerical_replay_performed':not args.smoke_only,'full_replay_matches':replay_matches,
            'comparison_queries':len(original['rows']),'sync_trials':len(original['synchronization_evaluation']['rows']),
            'state_queries':len(original['state_evaluation']['rows']),'legacy_numerical_scope':'S1 v0.1 1440 queries + 60 sync audits; P1 v0.2 1440 queries; complete older results preserved by hashes, not fully recomputed'}
    write_json(out/'VERIFICATION_RESULTS.json',result)
    text=(f"# PLM-S1 v0.2 検証\n\nテスト {result['total_tests']}件合格、skipなし。内訳: {counts}。\n\n"
          f"機能検証: {functional}。数値受入: {original['acceptance_passed']}。新S1 v0.2全数値再実行: {not args.smoke_only}、初回と一致: {replay_matches}。\n\n"
          "S1 v0.1全330ファイルは無変更。旧S1は1440照会・60同期監査、旧P1は1440照会の部分回帰を再実行。旧全数値評価を再計算したとは主張しません。全世代のテストとR1/C2回帰も実行。\n\n"
          "通常・部分観測かつ約1.06 HzずれのCLI復号を確認。真値付きパケットと旧wireを拒否。推論は無効、RF実機・独立意味評価は未実施。\n")
    (out/'VERIFICATION_REPORT.md').write_text(text,encoding='utf-8')
    print(json.dumps(result,indent=2))
    if not result['passed']: raise SystemExit(1)


if __name__=='__main__': main()
