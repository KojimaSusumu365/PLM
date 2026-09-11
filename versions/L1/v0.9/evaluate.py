"""Reproducible v0.9 experiment. Timing/environment are outside the result digest."""
import argparse
import json
from pathlib import Path
import platform
import sys
import time
import numpy as np
from evaluation.support import data, ROOT, interpret, text_goal, expected, parse, to_mentions, six_pairs
from evaluation.synthetic import run as run_synthetic, counts
from evaluation.integrity import verify_freeze
from plm_l1_v09.component.algebra import canonical, digest
from plm_l1_v09.component.training import fit as fit_component
from plm_l1_v09.training import fit

def write(p,value):
    with Path(p).open('x',encoding='utf-8') as f: f.write(json.dumps(value,ensure_ascii=False,indent=2)+'\n')

def single(model,rows):
    reads=[]; generated=[]
    for row in rows:
        out=model.read(row['text'])
        reads.append(model.recover(out['packet']).get('meaning') if out['status']=='read' else None)
        for goal in ('subject','object'):
            g=model.generate(model.encode(row['meaning']),goal)
            generated.append([interpret(g['text']),text_goal(g['text'])] if g['status']=='generated' else None)
    gold=[r['meaning'] for r in rows]; gen_gold=[[r['meaning'],goal] for r in rows for goal in ('subject','object')]
    return {'read':counts(reads,gold),'generation':counts(generated,gen_gold),'unique_input_texts':len({r['text'] for r in rows}),
            'unique_meanings':len({canonical(r['meaning']) for r in rows}),
            'unique_generation_tasks':len({canonical(g) for g in gen_gold})}

def inventory(model):
    learned=sum(s['projected_contexts'] for n,s in model.meta['statistics'].items() if not n.startswith('lexical_'))
    lexical=sum(s['projected_contexts'] for n,s in model.meta['statistics'].items() if n.startswith('lexical_'))
    return {'learned_associations':learned,'initial_lexicon_associations':lexical,'total_associations':learned+lexical,
            'per_memory':model.meta['statistics'],'fingerprint':model.fingerprint,
            'phase_block_bytes':sum(len(b.blob) for m in model.memories.values() for b in m.blocks),
            'fixed_cache_capacity_bytes':sum(len(m.cache) for m in model.memories.values())}

def temporal(model,rows):
    read_results=[]; round_results=[]; gold=[]; details=[]
    for i,row in enumerate(rows):
        out=model.read(row['text']); want=to_mentions(row['meaning']); gold.append(want)
        recovered=model.recover(out['packet']) if out['status']=='read' else {}
        read_results.append(recovered.get('meaning'))
        target=expected(want,('object','subject'),'reverse')
        g=model.generate(out['packet'],('object','subject'),'reverse') if out['status']=='read' else {'status':'abstain'}
        rer=model.read(g['text']) if g['status']=='generated' else {'status':'abstain'}
        rr=model.recover(rer['packet']).get('meaning') if rer['status']=='read' else None
        ok=(g['status']=='generated' and parse(g['text'])==target and rr is not None and expected(rr,('object','subject'))==target)
        round_results.append('correct' if ok else None if g['status']!='generated' or rr is None else 'wrong')
        if i<4: details.append({'input':row['text'],'generated':g.get('text'),'semantic_roundtrip_exact':ok})
        if (i+1)%216==0: print('temporal',i+1,'/',len(rows),flush=True)
    meanings={canonical(r['meaning']):r['meaning'] for r in rows}; direct=[]; dgold=[]
    for m in meanings.values():
        for order in ('preserve','reverse'):
            g=model.generate(model.encode(m),('subject','object'),order)
            direct.append(parse(g['text']) if g['status']=='generated' else None); dgold.append(expected(m,('subject','object'),order))
    return {'read':counts(read_results,gold),'direct_generation':counts(direct,dgold),
            'roundtrip':counts(round_results,['correct']*len(round_results)),
            'unique_input_texts':len({r['text'] for r in rows}),'unique_meanings':len(meanings),'examples':details,
            'time_associations':{n:s['projected_contexts'] for n,s in model.meta['training']['statistics'].items()}}

def judge(result):
    checks=[]
    def add(name,passed): checks.append({'name':name,'passed':bool(passed)})
    for method in ('ss','symbolic','id3','ss_six'):
        for stage in ('read','generation'):
            c=result['language'][method][stage]; add(method+'/'+stage,c['correct']==c['requests'])
    for stage in ('read','direct_generation','roundtrip'):
        c=result['temporal'][stage]; add('temporal/'+stage,c['correct']==c['requests'])
    for r in result['synthetic']:
        for stage in ('symbolic_projection','phase_retrieval'):
            c=r[stage]; add(r['task_id']+'/'+r['method']+'/'+str(r['dimension'])+'/'+r['seed']+'/'+str(r['selection_enabled'])+'/'+stage+'/accounting', c['requests']==c['correct']+c['wrong']+c['abstained'])
        if not r['selection_enabled']:
            add(r['task_id']+'/zero-H',r['fallback_full_context'] and not any(t['eligible'] for t in r['selection']['trials']))
    add('synthetic_train_test_disjoint',result['synthetic_train_test_disjoint'])
    add('SS_and_symbolic_global_scaffold_blocks_equal',result['language']['ss']['inventory']['phase_block_bytes']==result['language']['symbolic']['inventory']['phase_block_bytes'])
    add('inference_not_opened',result['eligible_for_inference'] is False)
    return checks

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--out',required=True); ap.add_argument('--development',action='store_true'); a=ap.parse_args()
    out=Path(a.out).resolve(); out.mkdir(parents=True,exist_ok=False)
    protocol=json.loads((ROOT/'evaluation'/'PROTOCOL.json').read_text(encoding='utf-8'))
    freeze='development_unfrozen' if a.development else verify_freeze()
    split='development' if a.development else 'evaluation'; tasks=data('dependencies_'+split)
    result={'schema':'plm-l1-v09-results','freeze_hash':freeze,'eligible_for_inference':False,'synthetic':[], 'language':{},'selection_audits':{}}
    perf={'environment':{'python':sys.version,'numpy':np.__version__,'platform':platform.platform(),'linux_execution_performed':False},'synthetic':[],'language':{}}
    disjoint=True
    for task in tasks:
        disjoint &= not ({canonical(r['context']) for r in task['train']} & {canonical(r['context']) for r in task['test']})
        standard=task['train_count']==24 and task['flipped_labels']==0
        dimensions=protocol['selector_dimensions'] if standard else [2048]
        seeds=protocol['selector_seeds'] if standard else protocol['selector_seeds'][:1]
        for dimension in dimensions:
            for seed in seeds:
                for method in protocol['methods']:
                    r,p=run_synthetic(task,method,dimension,seed); result['synthetic'].append(r); perf['synthetic'].append(p)
        if standard:
            r,p=run_synthetic(task,'ss',2048,protocol['selector_seeds'][0],enabled=False)
            result['synthetic'].append(r); perf['synthetic'].append(p)
        print('synthetic',task['id'],flush=True)
    result['synthetic_train_test_disjoint']=bool(disjoint)
    for method in ('ss','symbolic','id3','full','ss_disabled','ss_six'):
        actual='ss' if method.startswith('ss') else method
        started=time.perf_counter()
        model=fit_component(six_pairs() if method=='ss_six' else data('component_train'),data('lexicon'),
                            selector=actual,selection_enabled=method!='ss_disabled',seed=protocol['component_seed'],selection_seed=protocol['selector_seeds'][0])
        fit_seconds=time.perf_counter()-started; started=time.perf_counter()
        result['language'][method]=single(model,data('single_'+split))
        result['language'][method]['inventory']=inventory(model)
        audits=model.selection_audit
        timing={name:audit.pop('wall_seconds') for name,audit in audits.items()}
        result['selection_audits'][method]=audits
        perf['language'][method]={'fit_seconds':fit_seconds,'test_seconds':time.perf_counter()-started,'selector_seconds':timing,
                                  'owned_memory_heap_bytes':sum(m.storage()['owned_heap_bytes'] for m in model.memories.values())}
        print('language',method,result['language'][method]['read'],flush=True)
    started=time.perf_counter()
    model=fit(data('component_train'),data('temporal_train'),data('lexicon'),seed=protocol['temporal_seed'],selection_seed=protocol['selector_seeds'][0])
    result['temporal']=temporal(model,data(split)); result['model_fingerprint']=model.fingerprint
    result['component_fingerprint']=model.component.fingerprint; perf['temporal_seconds']=time.perf_counter()-started
    model.save(out/'model')
    result['checks']=judge(result); result['all_checks_passed']=all(c['passed'] for c in result['checks'])
    result['result_digest']=digest(result)
    write(out/'EVALUATION.json',result); write(out/'PERFORMANCE.json',perf)
    print(json.dumps({'digest':result['result_digest'],'checks':len(result['checks']),'passed':result['all_checks_passed']},ensure_ascii=False),flush=True)
    return 0 if result['all_checks_passed'] else 1

if __name__=='__main__': raise SystemExit(main())
