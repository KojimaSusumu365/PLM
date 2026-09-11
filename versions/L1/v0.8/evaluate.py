"""Freeze-aware evaluation, per-request records, explicit development separation."""
import argparse
import hashlib
import json
from pathlib import Path
from plm_l1_v06.algebra import digest
from plm_l1_v08.training import fit
from evaluation_support import ROOT,legacy,data,CATEGORIES
from measurements import assess,count,codec_probe,noise_probe,learning_controls,STAGES
from report import render


def source_files():
    files=[p for p in ROOT.iterdir() if p.is_file() and p.suffix in ('.py','.md','.txt')]
    for name in ('plm_l1_v08','plm_l1_v06','tests','data','evaluation','vendor'):
        files.extend(p for p in (ROOT/name).rglob('*') if p.is_file())
    return sorted(p for p in files if '__pycache__' not in p.parts and p.suffix!='.pyc')


def hashes(files,root):
    return {p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in files}


def verify_freeze():
    manifest=json.loads((ROOT/'SOURCE_MANIFEST.json').read_text(encoding='utf-8'))
    if manifest['files']!=hashes(source_files(),ROOT): raise ValueError('frozen source changed')
    return digest(manifest)


def judge(result,protocol):
    checks=[]
    def add(name,passed,**context): checks.append({'name':name,'passed':bool(passed),**context})
    wanted={(s,m) for s in protocol['evaluation_seeds'] for m in protocol['standard_modes']}
    if len(result['standard'])!=len(wanted) or {(r['seed'],r['mode']) for r in result['standard']}!=wanted:
        raise ValueError('standard inventory changed')
    for r in result['standard']:
        context={'seed':r['seed'],'mode':r['mode']}
        if count(r['records'])!=r['counts']: raise ValueError('standard counters changed')
        add('component_unchanged',r['component_fingerprint']==result['component_fingerprint'],**context)
        add('temporal_training_six_contexts',all(v['complete_contexts']==6 for v in r['training']['statistics'].values()),**context)
        for stage,n in protocol['standard_requests_per_condition'].items():
            c=r['counts'][stage]
            add(stage+'_coverage',c['requests']==n and c['exact']/n>=.98 and c['wrong']==0,**context)
        for category in CATEGORIES:
            c=count([x for x in r['records'] if x['category']==category])
            if c!=r['categories'][category]: raise ValueError('category counters changed')
            for stage in STAGES: add('category_exact',c[stage]['requests']>0 and c[stage]['exact']==c[stage]['requests'],category=category,stage=stage,**context)
        for kind in ('before','unknown'):
            subset=[x for x in r['records'] if x['temporal_kind']==kind]
            add('time_kind_exact',bool(subset) and all(x['exact'] for x in subset),kind=kind,**context)
        for order in ('preserve','reverse'):
            subset=[x for x in r['records'] if x.get('order')==order]
            add('presentation_goal_exact',bool(subset) and all(x['exact'] for x in subset),order=order,**context)
        add('invalid_texts_abstain',len(r['invalid_texts'])==17 and all(x['status']=='abstain' for x in r['invalid_texts']),**context)
        add('invalid_packets_abstain',len(r['invalid_packets'])==16 and all(x=='abstain' for x in r['invalid_packets']),**context)
    wanted={(s,d,m) for s in protocol['evaluation_seeds'] for d in protocol['codec_dimensions'] for m in protocol['codec_modes']}
    if len(result['codec'])!=len(wanted) or {(r['seed'],r['dimension'],r['mode']) for r in result['codec']}!=wanted: raise ValueError('codec inventory changed')
    for r in result['codec']:
        if count(r['records'],('codec',))['codec']!=r['counts'] or r['counts']['requests']!=216: raise ValueError('codec counters changed')
        context={k:r[k] for k in ('seed','dimension','mode')}
        before=[x for x in r['records'] if x['temporal_kind']=='before']
        add('directed_edge_control',len(before)==144 and all(x['reversed_edge_same_signal']==(r['mode']=='undirected') for x in before),**context)
        add('separate_presentation_signal',all(not x['reordered_presentation_same_signal'] for x in r['records']),**context)
        add('same_numeric_payload',r['payload_bytes']==16*r['dimension'],**context)
    wanted={(s,d,l) for s in protocol['noise_seeds'] for d in protocol['noise_dimensions'] for l in protocol['noise_levels']}
    if len(result['noise'])!=len(wanted) or {(r['seed'],r['dimension'],r['level']) for r in result['noise']}!=wanted: raise ValueError('noise inventory changed')
    for r in result['noise']:
        if count(r['records'],('noise',))['noise']!=r['counts'] or r['counts']['requests']!=216: raise ValueError('noise counters changed')
        if r['dimension']==8192 and r['level']==0: add('high_dimension_zero_noise',r['counts']['exact']==216,seed=r['seed'])
    if set(result['learning_controls'])!={'no_learning','flipped_teacher','renamed_markers','without_after','relation_table_reference'}: raise ValueError('control inventory changed')
    for name,r in result['learning_controls'].items():
        if name=='relation_table_reference':
            add('symbolic_relation_reference',len(r['records'])==864 and r['read_keys']==r['write_keys']==6 and all(x['read_exact'] and x['write_exact'] for x in r['records']))
        else:
            if count(r['records'],('read','generate'))!=r['counts']: raise ValueError('control counters changed')
            add('learning_correspondence_control',len(r['records'])==648 and all(not x['accepted'] if x['expected_abstain'] else x['exact'] for x in r['records']),mode=name)
    add('one_event_regression',result['component_regression']=={'read_exact':192,'generation_exact':384})
    return checks


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--out',required=True); parser.add_argument('--development',action='store_true'); a=parser.parse_args()
    output=Path(a.out).resolve()
    if output.exists(): raise ValueError('fresh evaluation output required')
    freeze='development_not_frozen' if a.development else verify_freeze()
    p=json.loads((ROOT/'evaluation'/'PROTOCOL.json').read_text(encoding='utf-8'))
    rows=data('development' if a.development else 'evaluation'); seeds=p['development_seeds'] if a.development else p['evaluation_seeds']
    output.mkdir(parents=True)
    result={'schema':'plm-temporal-evaluation-v1','split':'development' if a.development else 'evaluation','freeze_hash':freeze,
            'standard':[],'codec':[],'noise':[],'checks':[]}
    primary=None
    for seed in seeds:
        for mode in p['standard_modes']:
            m=fit(data('component_train'),data('temporal_train'),data('lexicon'),seed=seed,mode=mode)
            row=assess(m,rows)
            row.update(seed=seed,mode=mode,fingerprint=m.fingerprint,component_fingerprint=m.component.fingerprint,training=m.meta['training'])
            result['standard'].append(row)
            if primary is None: primary=m; m.save(output/'model')
            print(json.dumps({'stage':'standard','seed':seed,'mode':mode,'counts':row['counts']}),flush=True)
    for seed in seeds:
        for d in p['codec_dimensions']:
            for mode in p['codec_modes']:
                result['codec'].append(codec_probe(primary.codec.candidates,rows,d,seed,mode))
        print(json.dumps({'stage':'codec','seed':seed}),flush=True)
    for seed in p['development_noise_seeds'] if a.development else p['noise_seeds']:
        for d in p['noise_dimensions']:
            for level in p['noise_levels']:
                result['noise'].append(noise_probe(primary.codec.candidates,rows,d,seed,level))
        print(json.dumps({'stage':'noise','seed':seed}),flush=True)
    result['learning_controls']=learning_controls(rows)
    result['component_fingerprint']=primary.component.fingerprint
    regression={'read_exact':0,'generation_exact':0}
    for row in legacy.data('evaluation'):
        out=primary.component.read(row['text'])
        regression['read_exact']+=int(out['status']=='read' and primary.component.recover(out['packet'])['meaning']==row['meaning'])
        for goal in ('subject','object'):
            out=primary.component.generate(primary.component.encode(row['meaning']),goal)
            regression['generation_exact']+=int(out['status']=='generated' and legacy.interpret(out['text'])==row['meaning'] and legacy.text_goal(out['text'])==goal)
    result['component_regression']=regression
    if not a.development: result['checks']=judge(result,p)
    result['result_digest']=digest(result)
    with (output/'EVALUATION.json').open('x',encoding='utf-8') as f: f.write(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    with (output/'REPORT.md').open('x',encoding='utf-8') as f: f.write(render(result))
    print(json.dumps({'status':'development' if a.development else 'passed' if all(c['passed'] for c in result['checks']) else 'failed',
                      'checks':len(result['checks']),'result_digest':result['result_digest']}))
    if not a.development and not all(c['passed'] for c in result['checks']): raise SystemExit(1)


if __name__=='__main__': main()
