"""Descriptive summaries only; no settings selected here."""
import json
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from evaluation.integrity import read,write


def empty():
    return {k:0 for k in ('inputs','read_correct','read_wrong','read_abstain','generation_requests','generated_correct','generated_wrong',
                         'generator_abstain','blocked_by_reader','goal_correct','reread_semantic_correct','direct_requests',
                         'direct_correct','direct_wrong','direct_abstain')}


def add(a,r):
    a['inputs']+=1
    a['read_abstain' if r['read_status']!='read' else 'read_correct' if r['read_semantic_equal'] else 'read_wrong']+=1
    for g in r['outputs']:
        a['generation_requests']+=1;status=g['generation']['status']
        if status=='generated':
            a['generated_correct' if g['score']['semantic_equal'] else 'generated_wrong']+=1
            a['goal_correct']+=int(g['score']['goals_equal'])
        else:a['blocked_by_reader' if status=='not_run' else 'generator_abstain']+=1
        a['reread_semantic_correct']+=int(g['reread']['semantic_equal'])
    g=r['direct_generation'];a['direct_requests']+=1
    a['direct_abstain' if g['generation']['status']!='generated' else 'direct_correct' if g['score']['semantic_equal'] else 'direct_wrong']+=1


def main():
    ev=read(ROOT/'results/EVALUATION.json');models={m['id']:m for m in ev['models']};groups={};per_seed={}
    for row in ev['rows']:
        m=models[row['model_id']];key=(m['stage'],row['count'],m['dimension'],m['mode'],m['condition'])
        add(groups.setdefault(key,empty()),row)
        add(per_seed.setdefault(key+(m['seed'],),empty()),row)
    data=[dict(zip(('stage','count','dimension','mode','condition'),key),**value) for key,value in sorted(groups.items())]
    seeds=[dict(zip(('stage','count','dimension','mode','condition','seed'),key),**value) for key,value in sorted(per_seed.items())]
    legacy=empty()
    for r in ev['legacy_regression']:add(legacy,r)
    probes=[]
    for p in ev['probes']:
        for r in p['signals']:
            probes.append({'model':p['model_id'],'name':r['name'],'controlled_edit':r['controlled_edit'],
                           'recovered_expected':r['recovered_expected'],'generation_status':r['result']['generation']['status'],
                           'semantic_equal':bool(r['result']['score'] and r['result']['score']['semantic_equal']),
                           'reason':r['result']['generation'].get('reason')})
    result={'rows':data,'per_seed':seeds,'legacy':legacy,'probes':probes,
            'invalid_inputs':sum(len(p['invalid']) for p in ev['probes']),
            'invalid_abstain':sum(r['result']['status']=='abstain' for p in ev['probes'] for r in p['invalid']),
            'caution':'Three document-code seeds share one refitted language model and the same144 texts. Repeated outputs are not independent language samples.'}
    write(ROOT/'verification/SUMMARY.json',result)
    for r in data:print(json.dumps(r,ensure_ascii=False))
    print(json.dumps({'legacy':legacy,'invalid_inputs':result['invalid_inputs'],'invalid_abstain':result['invalid_abstain'],'probes':probes},ensure_ascii=False))


if __name__=='__main__':main()
