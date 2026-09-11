"""Audit all recorded budgets, local edits and inference outputs, without tuning."""
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from evaluation.integrity import read,write,verify

def run():
    index=read(ROOT/'results/INDEX.json');data=read(ROOT/'data/RECONFIRM_DATASETS.json')
    primary=cold=answers=generated=wrong=nonmutable=known_changes=0;capacities=set();reasons={}
    for cid in index['conditions']:
        r=read(ROOT/'results/conditions'/(cid+'.json'));used=0
        cases={c['id']:c for c in data['splits'][r['split']]['cases']};capacities.add(r['cost']['total_coefficient_bytes'])
        for row in r['primary']:
            primary+=1;c=cases[row['case_id']];targets=set(c['scope']['mutable'])
            assert row['budget_remaining_before']==r['budget_cap']-used
            assert row['confirmations_used']==len(row['answers'])
            for answer in row['answers']:
                q=answer['question'];receipt=answer['receipt'];answers+=1
                assert q['target'] in targets and 'value' not in q and receipt['target']==q['target']
                assert receipt['revision']==q['base_revision']+1 and receipt['local_audit']['other_cells_unchanged']
                assert receipt['local_audit']['local_numeric_delta_only']
                assert answer['external_value']==c['final']['cells'][q['target']]['candidates'][0]
                reasons[q['reason']]=reasons.get(q['reason'],0)+1
            used+=row['confirmations_used'];assert used<=r['budget_cap']
            assert set(row['final']['session_confirmed_targets'])=={a['question']['target'] for a in row['answers']}
        assert used==r['actual_confirmations']
        for row in r['cold']:
            cold+=1;assert row['no_session_receipts'] and row['session_confirmed_targets']=={}
        for f in [x['final'] for x in r['primary']]+r['cold']:
            nonmutable+=f['nonmutable_changed'];known_changes+=f['known_changed_by_ss']
            if f['correct'] or f['wrong']:assert len(f['outputs'])==2
            else:assert f['outputs']==[]
            for o in f['outputs']:
                if o['generation']['status']=='generated':
                    generated+=1;wrong+=not o['score']['semantic_equal']
                    assert o['reread_equal']==o['score']['semantic_equal']
    assert primary==864 and cold==864 and capacities=={94208}
    assert nonmutable==known_changes==0
    result={'passed':True,'all_primary_episodes_audited':primary,'all_cold_probes_audited':cold,'teacher_answers_audited':answers,
       'generated_outputs':generated,'wrong_generated_outputs':wrong,'teacher_reason_counts':reasons,
       'nonmutable_changes':nonmutable,'known_cells_silently_changed_by_ss':known_changes,
       'coefficient_bytes_each_method':94208,'frozen_digest':verify(),'eligible_for_inference':False}
    write(ROOT/'verification/LOG_AUDIT.json',result);print(result);return result

if __name__=='__main__':run()
