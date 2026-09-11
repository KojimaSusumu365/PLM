import argparse,json
from ss_multicode.algebra import digest
from .integrity import ROOT,write,verify_development


def choose(result,protocol):
    rows=[]
    for i,cfg in enumerate(protocol['configuration_grid']):
        runs=[r for r in result['runs'] if r['config_index']==i and r['strategy']=='mixed_revisit'];parts=[]
        for r in runs:
            groups=r['checkpoints'][-1]['metrics']['groups'];g=r['size'];old=groups['old_all'];unknown=groups['never_taught'];protected=groups['protected_old']
            parts.append((old['accepted_correct']-4*old['accepted_wrong'])/(2*g)-unknown['unseen_false_accept']/128+.5*protected['accepted_correct']/g)
        assert len(parts)==4
        rows.append({'config_index':i,'config':cfg,'utility':sum(parts)/len(parts),'per_size_world_utilities':parts})
    best=max(r['utility'] for r in rows);ties=[r for r in rows if best-r['utility']<=1e-12]
    selected=sorted(ties,key=lambda r:(-r['config']['explore_every'],-r['config']['drop_margin'],r['config_index']))[0]
    return {'config':selected['config'],'config_index':selected['config_index'],'development_rows':rows,'development_result_digest':result['result_digest'],
            'selection_rule':protocol['configuration_selection'],'eligible_for_inference':False}


def main():
    p=argparse.ArgumentParser();p.add_argument('--development',required=True);a=p.parse_args();verify_development()
    result=json.loads((__import__('pathlib').Path(a.development)/'EVALUATION.json').read_text(encoding='utf-8'));d=dict(result);claimed=d.pop('result_digest');assert digest(d)==claimed and len(result['runs'])==80
    selected=choose(result,json.loads((ROOT/'evaluation/PROTOCOL.json').read_text(encoding='utf-8')));write(ROOT/'evaluation/SELECTED.json',selected);print(json.dumps(selected,indent=2))


if __name__=='__main__':main()
