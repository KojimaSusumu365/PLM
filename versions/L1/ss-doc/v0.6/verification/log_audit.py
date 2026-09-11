import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from evaluation.integrity import read,write,verify
from ss_select.features import validate
from ss_select.memory import SelectorMemory

def run():
    data=read(ROOT/'data/DELAY_DATASETS.json');index=read(ROOT/'results/INDEX.json');selector=SelectorMemory.load(ROOT/'data/selector_model')
    answers=required=optional=probes=outputs=wrong=nonmutable=known_changes=scores=0
    for cid in index['conditions']:
        r=read(ROOT/'results/conditions'/(cid+'.json'));cases={c['id']:c for c in data['splits'][r['split']]['cases']};seen=set()
        fp=read(ROOT/'results/baselines'/(r['base']+'.json'))['memory_fingerprint'];assert r['actual_confirmations']==len(r['trace'])==6
        for i,t in enumerate(r['trace']):
            pick=t['selection'];q=pick['question'];receipt=t['receipt'];c=cases[q['id']];target=q['target']
            assert q['memory_fingerprint']==fp and target in c['scope']['mutable'] and (q['id'],target) not in seen;seen.add((q['id'],target))
            assert 'value' not in q and t['external_answer']==c['final']['cells'][target]['candidates'][0]
            assert receipt['revision']==q['base_revision']+1 and receipt['confirmed_packet_discarded']
            assert receipt['local_audit']['old']['state']=='unobserved' and receipt['local_audit']['other_cells_unchanged'] and receipt['local_audit']['local_numeric_delta_only']
            validate(pick['features']);assert pick['candidates_scored']==24-i;scores+=pick['candidates_scored']
            if r['policy']=='ss_learned':assert pick['selector_fingerprint']==selector.fingerprint and pick['value_prediction']==selector.predict(pick['features'])
            else:assert pick['value_prediction'] is None and pick['selector_fingerprint'] is None
            fp=receipt['memory_fingerprint'];answers+=1;required+=q['required_now'];optional+=not q['required_now']
        assert fp==r['after_answers_fingerprint'] and r['required_confirmations']==sum(t['selection']['question']['required_now'] for t in r['trace'])
        assert r['cost']['total_coefficient_bytes']==94208
        for row in r['delayed']:
            probes+=1;assert row['no_session_receipts'] and row['session_confirmed_targets']=={}
            nonmutable+=row['nonmutable_changed'];known_changes+=row['known_changed_by_ss']
            if row['correct'] or row['wrong']:assert len(row['outputs'])==2
            else:assert row['outputs']==[]
            for o in row['outputs']:
                if o['generation']['status']=='generated':outputs+=1;wrong+=not o['score']['semantic_equal'];assert o['reread_equal']==o['score']['semantic_equal']
    assert answers==648 and probes==1296 and nonmutable==known_changes==0
    examples=read(ROOT/'training_results/EXAMPLES.json');assert len(examples)==576 and {r['split'] for r in examples}=={'500','501'}
    assert {r['id'] for r in examples}.isdisjoint({c['id'] for s in ('400','401') for c in data['splits'][s]['cases']})
    for e in examples:
        from evaluation.delay_experiment import utility
        assert e['reward']==utility(e['after_local'])-utility(e['baseline_local']);validate(e['features'])
    record={'passed':True,'conditions':108,'actual_answers':answers,'required_answers':required,'optional_answers':optional,
            'delayed_probes':probes,'generated_outputs':outputs,'wrong_outputs':wrong,'candidate_scores':scores,
            'nonmutable_changed':nonmutable,'known_cells_silently_changed':known_changes,'training_examples_checked':len(examples),
            'training_evaluation_ids_disjoint':True,'frozen_digest':verify(),'eligible_for_inference':False}
    write(ROOT/'verification/LOG_AUDIT.json',record);print(record);return record

if __name__=='__main__':run()
