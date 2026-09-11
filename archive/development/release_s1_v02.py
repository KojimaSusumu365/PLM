"""Post-evaluation reporting/packaging only. Never alters frozen algorithm/protocol."""
import os
os.environ.setdefault('OPENBLAS_NUM_THREADS','1')
import argparse
from datetime import datetime,timezone
from hashlib import sha256
import json
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

BASE=Path(__file__).resolve().parents[1]
ROOT=BASE/'work/PLM-S1-v0.2'
DEST=BASE/'outputs/PLM-S1-v0.2'
ZIP=BASE/'outputs/PLM-S1-v0.2.zip'
EXTRACT=BASE/'work/verify-s1-v02-package'


def load(p): return json.loads(p.read_text(encoding='utf-8'))
def write(p,value): p.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def inventory(root): return {p.relative_to(root).as_posix():sha256(p.read_bytes()).hexdigest() for p in sorted(root.rglob('*')) if p.is_file()}


def finalize():
    r=load(ROOT/'results/EVALUATION_RESULTS.json')
    v=load(ROOT/'verification/VERIFICATION_RESULTS.json')
    if not v['functional_passed'] or not v['full_numerical_replay_performed'] or not v['full_replay_matches']:
        raise SystemExit('Functional verification and full NEW numerical replay required')
    if (ROOT/'RELEASE_STATUS.json').exists(): raise SystemExit('Refuse finalization overwrite')
    failed=[k for k,passed in r['acceptance'].items() if not passed]
    status={'version':'PLM-S1 v0.2','created_at_utc':datetime.now(timezone.utc).isoformat(),
            'release_kind':'experimental_target_met' if not failed else 'experimental_target_not_met',
            'implementation_complete':True,'functional_verification_passed':v['functional_passed'],
            'numerical_acceptance_passed':r['acceptance_passed'],'unmet_criteria':failed,
            'inference_enabled':False,'implementation_scope':'synthetic_discrete_complex_baseband_only',
            'independent_semantic_evaluation':'not_performed','authentication':'not_implemented'}
    write(ROOT/'RELEASE_STATUS.json',status)
    p=load(ROOT/'evaluation/PROTOCOL.json')
    lookup={(a['condition'],a['method']):a for a in r['aggregates']}
    lines=['# PLM-S1 v0.2 受入判断','',
           '実装・機能検証は完了。事前定義した数値受入は **'+('合格' if not failed else '未達あり')+'**。',
           f"受入チェック {sum(r['acceptance'].values())}/{len(r['acceptance'])}。未達: {', '.join(failed) if failed else 'なし'}。",'',
           '同じ8480チップ・送信エネルギー57344の中で、256パイロットチップを4か所へ再配置しました。±4 Hzの粗探索・微調整、±2 Hzの受入範囲、候補競合と補正後ブロック整合性による保留を実装しています。',
           f"開発後に{v['source_freeze']['verified_files']}ファイルを固定。8符号seed×4チャネルseedによる初回評価を保存し、全新数値評価の別実行で完全一致を確認しました。評価後に方式・閾値を変更していません。",'',
           '## 新SS受信器の主条件','','| 条件 | 回復 | 誤回復 | 保留 | 負例誤受理 | 同期受理 | 同期誤受理 |','|---|---:|---:|---:|---:|---:|---:|']
    for name in p['primary_conditions']:
        a=lookup[(name,'v02_ss')]
        lines.append(f"| {name} | {a['correct']}/{a['positive_queries']} | {a['wrong']} | {a['abstained']} | {a['false_accepts']}/{a['negative_queries']} | {a['pilot_aligned_trials']}/{a['trials']} | {a['wrong_locks']} |")
    partial=lookup[('wide_partial','v02_ss')]
    lines+=['',f"wide_partialは25%**チップ**観測です。平均P1成分カバー率は{partial['mean_coordinate_coverage']:.2%}、最大CFO誤差は{partial['max_cfo_error_hz']} Hz、最大位相誤差は{partial['max_phase_error_rad']} rad。P1成分の25%観測とは区別します。",'',
            '## 旧版の折り返し条件との比較','','同じP1情報量、チップ数、エネルギー、位相・遅延・雑音条件で比較しています。旧版との違いはパイロット配置と受信器の両方です。','',
            '| 条件 | 方式 | 回復 | 負例誤受理 | 同期受理 | 同期誤受理 |','|---|---|---:|---:|---:|---:|']
    for name in ('alias_positive','alias_negative','alias_partial'):
        for method in ('v01_ss','v02_ss'):
            a=lookup[(name,method)]
            lines.append(f"| {name} | {method} | {a['correct']}/{a['positive_queries']} | {a['false_accepts']}/{a['negative_queries']} | {a['pilot_aligned_trials']}/{a['trials']} | {a['wrong_locks']} |")
    lines+=['','## 同期判定を分けて集計','',
            'interiorは±1.9 Hz以内の11試験点、boundaryは±1.99/±2 Hz、guardは絶対値2.05/3/4.5/8/16 Hz、negativeは雑音・不整合など9種類です。各分類の個別結果もEVALUATION_REPORT.mdへ掲載しています。',
            '同期誤受理は受理後の整数遅延不一致、CFO誤差>0.025 Hz、または位相誤差>0.15 rad。真値は評価者専用です。',
            '','| 分類 | 方式 | 同期受理/試行 | 同期誤受理 |','|---|---|---:|---:|']
    sync=r['synchronization_evaluation']['aggregates']
    grouped=[]
    for category in ('interior','boundary','guard','negative','sampling_alias_limitation','authentication_limitation'):
        for method in p['sync_methods']:
            group=[a for a in sync if a['category']==category and a['method']==method]
            item={'category':category,'method':method,'trials':sum(a['trials'] for a in group),
                  'aligned':sum(a['aligned'] for a in group),'wrong_locks':sum(a['wrong_locks'] for a in group)}
            grouped.append(item)
            lines.append(f"| {category} | {method} | {item['aligned']}/{item['trials']} | {item['wrong_locks']} |")
    tone=lookup[('tone_interference','v02_ss')]
    lines+=['','旧配置へ戻して新受信器を使うv02_edge2_ablationも同じ送信予算です。広い周波数探索では、配置が前後2か所だけだと複数候補を区別できず保留し得ることを確認します。',
            '上の全試験点の成績は有限個の人工試験であり、あらゆる範囲外入力への保証ではありません。',
            '', '## 追加のDC干渉ストレス', '',
            f"tone_interferenceは主受入条件とは別の追加ストレスです。新SSの回復は{tone['correct']}/{tone['positive_queries']}、負例誤受理{tone['false_accepts']}/{tone['negative_queries']}でしたが、同期の監査基準を超えた試行は{tone['wrong_locks']}/{tone['trials']}ありました。最大CFO誤差{tone['max_cfo_error_hz']} Hz、最大位相誤差{tone['max_phase_error_rad']} rad。候補回復成功と同期誤差基準への適合は別々に扱います。",
            '','## 限界を成功率から隠さない','',
            '8000.1 Hzは1サンプル/チップの離散モデルでは0.1 Hzと区別できません。sampling_alias_limitationの誤受理をそのまま記録しています。帯域制限された入力という前提やRF前段を実装したことにはなりません。',
            '有効パイロットだけでも同期を受理でき、同期は送信者やペイロードの認証ではありません。空ペイロードの候補回復は別テストで保留を確認しています。SHA256も認証ではありません。',
            '','## 意味状態と既存版の保存','']
    s=r['state_evaluation']
    lines += [f"7-slot完全回復 {s['exact_frames']}/{s['frames']}。正例回復 {s['summary']['correct']}/{s['summary']['positive_queries']}、負例誤受理 {s['summary']['false_accepts']}/{s['summary']['negative_queries']}。R1の否定・仮定・隔離・訂正対象・同Concept別個体の連携テストも実行。推論は無効のままです。",'',
              '## 検証と配布','',f"全世代テスト {v['total_tests']}件合格、skipなし。内訳: {v['tests']}。旧S1 v0.1全330ファイルは無変更。",
              f"新規評価は{v['comparison_queries']}比較照会、{v['sync_trials']}同期判定、{v['state_queries']}状態照会。全新数値結果を再実行して初回と一致。",
              '旧S1は1440照会・60同期監査、旧P1は1440照会を部分回帰。旧全数値評価は保存ハッシュを確認し、全部再計算したとは主張しません。ZIP展開後の実行検証は外側のPLM-S1-v0.2-VERIFICATION.mdを参照してください。',
              '','## 次の検討','',
              ('まず未達条件の再現・原因分析を次版の開発データとして扱い、今回の未知評価結果は変更せず保存します。' if failed else '次は入力の帯域・時間軸の前提を明文化したうえで、分数チップ遅延・小さな時計ずれを段階的に評価するのが妥当です。'),
              'RF実機、認証、独立意味評価、推論開放は未実施。現行のPython/NumPy構成を維持しています。','']
    (ROOT/'results/RELEASE_DECISION.md').write_text('\n'.join(lines),encoding='utf-8')
    write(ROOT/'results/RELEASE_SUMMARY.json',{'status':status,'primary':[lookup[(name,'v02_ss')] for name in p['primary_conditions']],
                                            'sync_categories':grouped,'state_summary':s['summary'],'verification':v})
    print(json.dumps(status,indent=2))


def package():
    if any(p.exists() for p in (DEST,ZIP,EXTRACT)): raise SystemExit('Refuse overwrite of release/extraction targets')
    v=load(ROOT/'verification/VERIFICATION_RESULTS.json')
    status=load(ROOT/'RELEASE_STATUS.json')
    if not v['functional_passed'] or not v['full_replay_matches']: raise SystemExit('Functional/replay failure')
    check=subprocess.run([sys.executable,'-B','freeze_release.py'],cwd=ROOT,capture_output=True)
    if check.returncode: raise SystemExit('Frozen source changed before packaging')
    shutil.copytree(ROOT,DEST)
    files=inventory(DEST)
    write(DEST/'RELEASE_MANIFEST.json',{'version':'PLM-S1 v0.2','release_kind':status['release_kind'],'scope':'all files except this manifest','files':files})
    with zipfile.ZipFile(ZIP,'x',zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
        for p in sorted(DEST.rglob('*')):
            if p.is_file(): archive.write(p,p.relative_to(DEST.parent).as_posix())
    EXTRACT.mkdir()
    with zipfile.ZipFile(ZIP) as archive:
        for entry in archive.infolist():
            if not (EXTRACT/entry.filename).resolve().is_relative_to(EXTRACT.resolve()): raise SystemExit('Unsafe ZIP entry')
        archive.extractall(EXTRACT)
    if inventory(EXTRACT/DEST.name)!=inventory(DEST): raise SystemExit('Extraction bytes mismatch')
    checksum=sha256(ZIP.read_bytes()).hexdigest()
    (BASE/'outputs/PLM-S1-v0.2.sha256').write_text(checksum+'  '+ZIP.name+'\n',encoding='utf-8')
    print(json.dumps({'zip':str(ZIP),'bytes':ZIP.stat().st_size,'files':len(files)+1,'sha256':checksum},indent=2))


def verify_zip():
    root=EXTRACT/DEST.name
    out=EXTRACT/'verification-repeat'
    if out.exists(): raise SystemExit('Refuse verification overwrite')
    before=inventory(root)
    if before!=inventory(DEST): raise SystemExit('Extracted folder mismatch')
    if {k:v for k,v in before.items() if k!='RELEASE_MANIFEST.json'}!=load(root/'RELEASE_MANIFEST.json')['files']:
        raise SystemExit('Manifest mismatch')
    proc=subprocess.run([sys.executable,'-B','verify_release.py','--smoke-only','--out-dir',str(out)],cwd=root,capture_output=True,encoding='utf-8',errors='replace')
    if not out.exists(): raise SystemExit(proc.stdout+proc.stderr)
    (out/'EXTRACTED_VERIFICATION_OUTPUT.txt').write_text(proc.stdout+proc.stderr,encoding='utf-8')
    if not (out/'VERIFICATION_RESULTS.json').exists(): raise SystemExit(proc.stdout+proc.stderr)
    v=load(out/'VERIFICATION_RESULTS.json')
    if not v['functional_passed']: raise SystemExit('Extracted functional failure')
    if proc.returncode not in (0,1) or (proc.returncode==1 and v['checks']['numerical_acceptance_passed']): raise SystemExit('Unexpected verification failure')
    pre=load(root/'verification/VERIFICATION_RESULTS.json')
    checks={'all_extracted_bytes_match':True,'manifest_matches':True,'all_tests_and_cli_passed':v['functional_passed'],
            'extracted_files_unchanged':before==inventory(root),'prepackaging_full_new_replay_matches':pre['full_replay_matches'],
            'first_result_hash_intact':v['checks']['initial_result_hash_intact']}
    if not all(checks.values()): raise SystemExit('ZIP check failed: '+str(checks))
    result={'version':'PLM-S1 v0.2','files':len(before),'tests':v['tests'],'total_tests':v['total_tests'],
            'scope':'all extracted bytes, all tests, CLI, old S1/P1 subsets; full NEW numerical replay performed before packaging, not repeated after extraction',
            'zip_bytes':ZIP.stat().st_size,'sha256':sha256(ZIP.read_bytes()).hexdigest(),'checks':checks,
            'functional_passed':True,'numerical_acceptance_passed':v['checks']['numerical_acceptance_passed']}
    write(BASE/'outputs/PLM-S1-v0.2-VERIFICATION.json',result)
    lines=['# PLM-S1 v0.2 配布ZIP検証','',f"全{len(before)}ファイルを配布フォルダとmanifestへ照合して一致。ZIP SHA256: `{result['sha256']}`。",'',
           f"展開後に全世代テスト{v['total_tests']}件、skipなしで合格。通常・部分観測かつ約1.06 HzずれのCLI復号、真値付きpacketと旧wireの拒否、R1/C2回帰、旧S1/P1の部分数値回帰を再実行しました。展開ファイルは検証前後で不変です。",'',
           '新S1 v0.2全数値評価の再実行・初回結果との完全一致確認はZIP作成前に実施。展開後は全数値評価を再計算せず、保存結果を含む全ファイル照合と上記の実行検証を行っています。', '',
           '数値受入: '+('合格' if result['numerical_acceptance_passed'] else '未達あり。RELEASE_DECISION.mdを参照。'),
           '人工離散複素ベースバンドのみ。RF実機・認証・独立意味評価は未実施、推論は無効です。','']
    (BASE/'outputs/PLM-S1-v0.2-VERIFICATION.md').write_text('\n'.join(lines),encoding='utf-8')
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('action',choices=['finalize','package','verify-zip'])
    action=parser.parse_args().action
    {'finalize':finalize,'package':package,'verify-zip':verify_zip}[action]()
