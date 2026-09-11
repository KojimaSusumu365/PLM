"""Paired recovery and independent numerical lock audits. Not semantic validation."""
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
import json
from pathlib import Path
import numpy as np
from plm_p1.core import PhaseCodebook,encode,digest,require
from plm_p1.evaluation import summarize
from plm_p1_v02.fixtures import make_frames,public_catalogue,entity_candidates,DOC
from plm_p1_v02.recovery import Receiver
from plm_s1.link import Link as OldLink,transmit as old_transmit,simulate_channel as old_channel
from plm_s1.packet import to_packet as old_packet
from plm_s1.receiver import Session as OldSession,synchronize as old_sync
from plm_s1.evaluation import aggregates as old_aggregates,wrap_error
from .link import Link,transmit,simulate_channel,despread_aligned,shifted
from .packet import to_packet
from .receiver import Session,synchronize,THRESHOLDS

ROOT=Path(__file__).resolve().parents[1]
METHODS=['v01_ss','v02_direct','v02_repeat','v02_ss','v02_oracle']


def protocol():
    p=json.loads((ROOT/'evaluation/PROTOCOL.json').read_text(encoding='utf-8'))
    require(p['methods']==METHODS and p['thresholds']==THRESHOLDS,'Protocol/implementation drift')
    for kind in ('code','channel'):
        require(not set(p['development_'+kind+'_seeds'])&set(p['evaluation_'+kind+'_seeds']),'Split leakage')
    require(Link(**p['link']).validate().frame_length==p['frame_chips'],'Framing drift')
    return p


def parameters(code,channel,condition):
    rng=np.random.Generator(np.random.PCG64(700000+31*code+channel))
    phase=float(rng.uniform(-np.pi,np.pi))
    f=float(rng.uniform(-condition.get('cfo_range',1.9),condition.get('cfo_range',1.9)))
    return {'seed':100000*code+channel,'phase_rad':0. if condition.get('nominal') else phase,
            'cfo_hz':0. if condition.get('nominal') else condition.get('fixed_cfo',f),
            'delay_chips':0 if condition.get('nominal') else [-7,-3,4,8][channel%4],
            'keep_fraction':condition['keep_fraction'],'noise_std':condition['noise_std'],
            'jitter_std':0. if condition.get('nominal') else .03,'tone_rms':condition.get('tone_rms',0.)}


def setup(code,channel,condition):
    book=PhaseCodebook(2048,'s1-v02-code-'+str(code))
    frames=make_frames(4)
    memory=encode(frames,book)
    params=parameters(code,channel,condition)
    catalogue=public_catalogue()
    sessions,channels,budgets={},{},{}
    for method,mode in (('v01_ss','spread'),('v02_direct','direct_sparse'),('v02_repeat','repeat'),('v02_ss','spread')):
        old=method=='v01_ss'
        link=OldLink() if old else Link(mode=mode)
        tx,norm=(old_transmit if old else transmit)(memory,book,link)
        y,m=(old_channel if old else simulate_channel)(tx,link,**params)
        packet=(old_packet if old else to_packet)(y,m,book,link,norm,source_digest=digest(frames))
        sessions[method]=(OldSession if old else Session)(packet,catalogue,expected_book=book,expected_link=link)
        channels[method]=(y,m,link,norm)
        budgets[method]={'chips':len(tx),'tx_energy':round(float(np.vdot(tx,tx).real),8),
                         'pilot_chips':256,'duration_seconds':len(tx)/8000,'peak_chip_power':float(np.max(abs(tx)**2))}
    return book,frames,memory,catalogue,params,sessions,channels,budgets


def lock_audit(sync,params):
    aligned=sync['status']=='aligned'
    delay=sync['estimated_delay_chips']==params['delay_chips'] if aligned else None
    cfo=abs(sync['estimated_cfo_hz']-params['cfo_hz']) if aligned else None
    phase=wrap_error(sync['estimated_phase_rad'],params['phase_rad']) if aligned else None
    return {'estimated_delay_correct':delay,'absolute_cfo_error_hz':cfo,'wrapped_phase_error_rad':phase,
            'wrong_lock':bool(aligned and (not delay or cfo>.025 or phase>.15))}


def trial(arguments):
    code,channel,condition=arguments
    book,frames,memory,catalogue,params,sessions,channels,budgets=setup(code,channel,condition)
    y,m,link,norm=channels['v02_ss']
    correction=y*np.exp(-1j*(params['phase_rad']+2*np.pi*params['cfo_hz']*np.arange(8480)/8000))
    oracle,om,oi=despread_aligned(shifted(correction,-params['delay_chips']),shifted(m,-params['delay_chips']),book,link,norm)
    oracle_receiver=Receiver(oracle,om,book,catalogue)
    rows,audits=[],[]
    for method in METHODS:
        if method=='v02_oracle':
            values,mask,info=oracle,om,oi
            sync={'status':'oracle_reference_only','estimated_delay_chips':None,'estimated_cfo_hz':None,'estimated_phase_rad':None}
        else:
            s=sessions[method]
            values,mask,info,sync=s.values,s.mask,s.despreading,s.synchronization
        denominator=float(np.vdot(memory[mask],memory[mask]).real) if mask.any() else 0.
        nmse=float(np.vdot(values[mask]-memory[mask],values[mask]-memory[mask]).real/denominator) if denominator>0 else None
        audits.append({'condition':condition['name'],'method':method,'code_seed':code,'channel_seed':channel,'sync':sync,
                       'evaluator_only_channel_truth':params,'coordinate_coverage':float(mask.mean()),
                       'nmse_on_recovered_coordinates':nmse,'observed_payload_chips':info['observed_payload_chips'],**lock_audit(sync,params)})
        choices=entity_candidates(96)
        for frame in frames:
            for role in ('subject','object'):
                truth=frame['slots'][role]
                for kind in ('present','absent_event','true_value_not_in_dictionary'):
                    event='absent-'+frame['event_id'] if kind=='absent_event' else frame['event_id']
                    candidates=[c for c in choices if c!=truth] if kind=='true_value_not_in_dictionary' else choices
                    q=dict(document_id=DOC,event_id=event,role=role,candidates=candidates)
                    r=oracle_receiver.scores(**q) if method=='v02_oracle' else s.query(q)
                    outcome=('correct' if r['selected']==truth else 'abstained' if r['selected'] is None else 'wrong') if kind=='present' else ('false_accept' if r['selected'] is not None else 'correct_rejection')
                    rows.append({'condition':condition['name'],'method':method,'code_seed':code,'channel_seed':channel,'event_id':event,
                                 'role':role,'test_kind':kind,'outcome':outcome,'selected':r['selected'],'reason':r['reason'],'eligible_for_inference':r['eligible_for_inference']})
    return {'rows':rows,'audits':audits,'budgets':{'condition':condition['name'],'code_seed':code,'channel_seed':channel,'methods':budgets}}


def sync_trial(arguments):
    code,channel,case,keep=arguments
    book=PhaseCodebook(2048,'s1-v02-code-'+str(code))
    memory=encode(make_frames(4),book)
    condition={'keep_fraction':keep,'noise_std':.25,'fixed_cfo':case.get('frequency_hz',.1)}
    params=parameters(code,channel,condition)
    if case['name']=='outside_delay': params['delay_chips']=11
    rows=[]
    for method in ('v02_distributed','v02_edge2_ablation','v01_edge2'):
        old=method=='v01_edge2'
        link=OldLink() if old else Link(layout='edge2' if method=='v02_edge2_ablation' else 'distributed4')
        tx,norm=(old_transmit if old else transmit)(memory,book,link)
        indexes=(np.arange(16,144),np.arange(8336,8464)) if old else link.pilot_indices
        if case['name']=='wrong_pilots':
            tx,_=(old_transmit if old else transmit)(memory,PhaseCodebook(2048,'wrong-s1-v02-'+str(code)),link)
        if case['name'] in ('noise_only','observed_zero'): tx[:]=0
        if case['name']=='pilot_only':
            mask=np.zeros(8480,bool)
            for ix in indexes: mask[ix]=True
            tx[~mask]=0
        if case['name']=='conflicting_phases': tx[indexes[len(indexes)//2]]*=-1
        if case['name']=='equal_frequency_mixture':
            times=np.arange(8480)/8000
            tx*=np.exp(2j*np.pi*.9*times)+np.exp(-2j*np.pi*.9*times)
            tx*=np.sqrt(57344/float(np.vdot(tx,tx).real))
        local=dict(params)
        if case['name']=='observed_zero': local.update(noise_std=0.)
        if case['name']=='no_observation': local.update(keep_fraction=0.)
        y,m=(old_channel if old else simulate_channel)(tx,link,**local)
        if case['name'] in ('one_block_missing','all_pilots_missing'):
            for ix in (indexes if case['name']=='all_pilots_missing' else [indexes[len(indexes)//2]]):
                m[ix+params['delay_chips']]=False
            y[~m]=0
        _,_,s=(old_sync if old else synchronize)(y,m,book,link,norm)
        rows.append({'case':case['name'],'category':case['category'],'frequency_hz':case.get('frequency_hz'),
                     'keep_fraction':keep,'method':method,'code_seed':code,'channel_seed':channel,'sync':s,
                     'evaluator_only_channel_truth':params,**lock_audit(s,params)})
    return rows


def sync_cases(p):
    cases=[]
    for f in p['frequency_sweep_hz']:
        category='interior' if abs(f)<=1.9 else 'boundary' if abs(f)<=2 else 'guard' if abs(f)<=16 else 'sampling_alias_limitation'
        cases.append({'name':'frequency_'+str(f),'category':category,'frequency_hz':f})
    cases += [{'name':name,'category':'negative'} for name in p['negative_sync_cases']]
    cases += [{'name':name,'category':'authentication_limitation'} for name in p['limitation_sync_cases']]
    return cases


def sync_aggregates(rows):
    result=[]
    for case,keep,method in sorted({(r['case'],r['keep_fraction'],r['method']) for r in rows}):
        group=[r for r in rows if (r['case'],r['keep_fraction'],r['method'])==(case,keep,method)]
        aligned=[r for r in group if r['sync']['status']=='aligned']
        reasons={k:sum(r['sync']['reason']==k for r in group) for k in sorted({r['sync']['reason'] for r in group})}
        result.append({'case':case,'category':group[0]['category'],'frequency_hz':group[0]['frequency_hz'],'keep_fraction':keep,'method':method,
                       'trials':len(group),'aligned':len(aligned),'abstained':len(group)-len(aligned),'wrong_locks':sum(r['wrong_lock'] for r in group),
                       'max_cfo_error_hz':max((r['absolute_cfo_error_hz'] for r in aligned),default=None),
                       'max_phase_error_rad':max((r['wrapped_phase_error_rad'] for r in aligned),default=None),'reasons':reasons})
    return result


def state_suite(codes,channel,condition):
    rows,frames_ok=[],[]
    for code in codes:
        book,frames,_,catalogue,_,sessions,_,_=setup(code,channel,condition)
        for f in frames:
            matches=[]
            for role,truth in f['slots'].items():
                choices=entity_candidates() if role in ('subject','object') else catalogue['vocabulary'][role]
                for kind in (['present'] if role in ('subject','object') else ['present','true_value_not_in_dictionary']):
                    r=sessions['v02_ss'].query(dict(document_id=DOC,event_id=f['event_id'],role=role,candidates=choices if kind=='present' else [c for c in choices if c!=truth]))
                    outcome=('correct' if r['selected']==truth else 'abstained' if r['selected'] is None else 'wrong') if kind=='present' else ('correct_rejection' if r['selected'] is None else 'false_accept')
                    rows.append({'code_seed':code,'channel_seed':channel,'event_id':f['event_id'],'role':role,'test_kind':kind,'outcome':outcome,'eligible_for_inference':r['eligible_for_inference']})
                    if kind=='present': matches.append(outcome=='correct')
            frames_ok.append(all(matches))
    return {'rows':rows,'summary':summarize(rows),'frames':len(frames_ok),'exact_frames':sum(frames_ok)}


def run_suite(split,workers=2):
    p=protocol()
    require(split in ('development','evaluation'),'Unknown split')
    codes,channels=p[split+'_code_seeds'],p[split+'_channel_seeds']
    rows,audits,budgets,sync_rows=[],[],[],[]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for condition in p['conditions']:
            for r in pool.map(trial,[(c,h,condition) for c in codes for h in channels]):
                rows.extend(r['rows']); audits.extend(r['audits']); budgets.append(r['budgets'])
            print('completed',split,'recovery',condition['name'],flush=True)
        for case in sync_cases(p):
            for r in pool.map(sync_trial,[(c,h,case,k) for c in codes for h in channels for k in p['sync_keep_fractions']]): sync_rows.extend(r)
            print('completed',split,'sync',case['name'],flush=True)
    summary=old_aggregates(rows,audits)
    for a in summary: a['wrong_locks']=sum(r['wrong_lock'] for r in audits if (r['condition'],r['method'])==(a['condition'],a['method']))
    sync_summary=sync_aggregates(sync_rows)
    lookup={(a['condition'],a['method']):a for a in summary}
    checks={}
    a=p['acceptance']
    for name in p['primary_conditions']:
        s=lookup[(name,'v02_ss')]
        checks[name+'_recovery']=s['recovery_rate']>=(1. if name=='nominal' else a['primary_recovery_min'])
        checks[name+'_false_accept']=s['false_accept_rate']<=(0. if name=='nominal' else a['primary_false_accept_max'])
        checks[name+'_acquisition']=s['pilot_aligned_trials']/s['trials']>=a['primary_acquisition_rate_min']
        checks[name+'_wrong_lock']=s['wrong_locks']==0
    for keep in p['sync_keep_fractions']:
        group=[s for s in sync_summary if s['method']=='v02_distributed' and s['keep_fraction']==keep]
        checks[f'sweep_{keep}_interior_acquisition']=all(s['aligned']/s['trials']>=a['primary_acquisition_rate_min'] for s in group if s['category']=='interior')
        checks[f'sweep_{keep}_interior_boundary_wrong_lock']=all(s['wrong_locks']==0 for s in group if s['category'] in ('interior','boundary'))
        checks[f'sweep_{keep}_guard_rejection']=all(s['aligned']==0 for s in group if s['category']=='guard')
        checks[f'sweep_{keep}_negative_rejection']=all(s['aligned']==0 for s in group if s['category']=='negative')
    checks['equal_energy_chip_budget']=all(len({(b['chips'],b['tx_energy']) for b in budget['methods'].values()})==1 for budget in budgets)
    checks['no_observation_abstain']=lookup[('no_observation','v02_ss')]['abstained']==lookup[('no_observation','v02_ss')]['positive_queries']
    checks['inference_disabled']=all(r['eligible_for_inference'] is False for r in rows)
    state=state_suite(codes,channels[0],next(c for c in p['conditions'] if c['name']=='wide_partial'))
    checks['state_recovery']=state['exact_frames']/state['frames']>=.95
    checks['state_no_false_accept']=state['summary']['false_accepts']==0
    checks['state_inference_disabled']=all(r['eligible_for_inference'] is False for r in state['rows'])
    return {'version':'PLM-S1 v0.2','split':split,'protocol_hash':digest(p),'numpy_version':np.__version__,'dataset_kind':p['dataset_kind'],
            'code_seeds':codes,'channel_seeds':channels,'aggregates':summary,'rows':rows,'trial_audits':audits,'budgets':budgets,
            'synchronization_evaluation':{'rows':sync_rows,'aggregates':sync_summary},'state_evaluation':state,'acceptance':checks,'acceptance_passed':all(checks.values()),
            'inference_enabled':False,'independent_semantic_evaluation':'not_performed','ss_demodulation_implemented':True,'implementation_scope':'synthetic_discrete_complex_baseband_only'}


def render_report(r):
    lines=['# PLM-S1 v0.2 数値評価','',f"分割: {r['split']}。内部人工ベースバンド評価であり、独立意味評価ではありません。",'',
           '## 回復比較','','全方式8480チップ・総エネルギー57344、パイロット256チップを内数とします。旧版との比較は配置と受信器の両方が違います。配置だけを戻す比較は後述の同期評価です。',
           '','| 条件 | 方式 | 正例回復 | 誤回復 | 保留 | 負例誤受理 | 同期誤受理 |','|---|---|---:|---:|---:|---:|---:|']
    for a in r['aggregates']:
        lines.append(f"| {a['condition']} | {a['method']} | {a['correct']}/{a['positive_queries']} | {a['wrong']} | {a['abstained']} | {a['false_accepts']}/{a['negative_queries']} | {a['wrong_locks']} |")
    lines+=['','## 新受信器の数値精度','','NMSEは回復成分だけで計算し、無出力は欠測です。25%チップ観測と25%P1成分観測は異なります。',
            '','| 条件 | 同期受理 | 最大CFO誤差 Hz | 最大位相誤差 rad | 成分カバー率 | 成分NMSE |','|---|---:|---:|---:|---:|---:|']
    for a in r['aggregates']:
        if a['method']=='v02_ss': lines.append(f"| {a['condition']} | {a['pilot_aligned_trials']}/{a['trials']} | {a['max_cfo_error_hz']} | {a['max_phase_error_rad']} | {a['mean_coordinate_coverage']:.2%} | {a['mean_nmse_on_recovered_coordinates']} |")
    lines+=['','## 周波数掃引・負例・配置の比較','','同期誤受理は、受理したのに真の整数遅延と違う、CFO誤差>0.025 Hz、または位相誤差>0.15 radのいずれか。真値は評価者専用で受信器には渡しません。',
            '','| 条件 | チップ観測率 | 方式 | 同期受理/試行 | 同期誤受理 |','|---|---:|---|---:|---:|']
    for a in r['synchronization_evaluation']['aggregates']:
        lines.append(f"| {a['case']} | {a['keep_fraction']:.0%} | {a['method']} | {a['aligned']}/{a['trials']} | {a['wrong_locks']} |")
    state=r['state_evaluation']
    lines+=['','## 状態の別評価','',f"7-slot完全回復 {state['exact_frames']}/{state['frames']}。{state['summary']}。target_clauseとR1の5種類の連携は単体・連携テストで検証。",'',
            '## 受入','',f"事前定義チェック {sum(r['acceptance'].values())}/{len(r['acceptance'])}。",'']
    lines += [f"- {k}: {'PASS' if v else 'FAIL'}" for k,v in r['acceptance'].items()]
    lines+=['','## 限界','','受入周波数は±2 Hz、探索は±4 Hz。境界±2 Hz付近の雑音による保留を別記します。全周波数・全入力で誤同期しない保証はありません。',
            'Fs+0.1 Hzは離散サンプリングにより0.1 Hzと識別できません。有効パイロットだけでも同期を受理でき、これは送信者・ペイロードの認証ではありません。上表に失敗側も保存します。',
            '照会やseed交差内には相関があり、照会数を独立標本数とした信頼区間ではありません。白色雑音下のSS固有の無料利得、RF実機、独立意味評価、推論開放は主張しません。','']
    return '\n'.join(lines)
