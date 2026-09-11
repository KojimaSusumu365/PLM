import argparse
import copy
import time
from pathlib import Path
import numpy as np
from ss_partial.runtime import PartialModel
from evaluation.integrity import ROOT,read,write,verify
from evaluation.experiment import MODES,inputs,train,query,update_faults
from evaluation.numerical import run as arithmetic, difference

def summarize(rows):
    groups = []
    for condition,mode in sorted({(r['condition'],r['mode']) for r in rows}):
        rs = [r for r in rows if (r['condition'],r['mode'])==(condition,mode)]
        groups.append({'condition':condition,'mode':mode,'cases':len(rs),
                       'correct_documents':sum(r['result']['correct'] for r in rs),
                       'wrong_documents':sum(r['result']['wrong'] for r in rs),
                       'held_documents':sum(r['result']['status']=='held' for r in rs),
                       'generated_texts':sum(o['generation']['status']=='generated' for r in rs for o in r['result']['outputs']),
                       'requested_texts':2*len(rs),
                       'nonmutable_changed':sum(r['result']['nonmutable_changed'] for r in rs)})
    return groups

def acceptance(groups,numerical,paired,faults,input_records,plan):
    main = [g for g in groups if g['condition']=='main']
    hard = [g for g in groups if g['condition'] in plan['hard_query_faults']+['coefficients_zero']]
    checks = {
        'core_scores_within_tolerance':numerical['maximum_score_difference']<=plan['numerical_tolerance'],
        'core_coefficients_within_tolerance':numerical['maximum_coefficient_difference']<=plan['numerical_tolerance'],
        'core_chunk_bitwise_equal':numerical['all_chunk_fingerprints_equal'],
        'core_metadata_equal':numerical['all_metadata_equal'],
        'paired_main_within_tolerance':all(p['coefficient_max_abs_difference']<=plan['numerical_tolerance'] for p in paired),
        'paired_output_texts_equal':all(p['generated_texts_equal'] for p in paired),
        'main_correct_rate':all(g['correct_documents']/g['cases']>=plan['minimum_main_correct_rate'] for g in main),
        'main_no_wrong_generation':all(g['wrong_documents']==0 for g in main),
        'hard_queries_no_generation':all(g['generated_texts']==0 for g in hard),
        'fault_updates_atomic_hold':all(r['status']=='held' and r['original_unchanged'] and r['returned_unchanged'] for r in faults if r['expected_hold']),
        'paired_outer_received_meaning_equal':all(r['received_observation_equal'] for r in input_records),
        'paired_outer_no_measured_wrong_alignment':all(r['sync']['wrong_aligned_frames']==0 for r in input_records),
        'nonmutable_preserved':all(g['nonmutable_changed']==0 for g in groups)}
    return {'passed':all(checks.values()),'checks':checks,'eligible_for_inference':False}

def run(out,development=False):
    start = time.perf_counter()
    out = Path(out)
    out.mkdir(parents=True,exist_ok=False)
    frozen = None if development else verify()
    plan = read(ROOT/'evaluation/PROTOCOL.json')
    split = 'development' if development else 'evaluation'
    cases = read(ROOT/'data/CORPUS.json')['splits'][split]
    focal = [c for c in cases if c['kind']=='focal']
    seeds = [0] if development else plan['memory_seeds']
    model = PartialModel.load(ROOT/'model')
    packets,input_records = inputs(model,cases,split)
    write(out/'INPUTS.json',input_records)
    numerical = arithmetic(model.codec.candidates,seeds)
    write(out/'NUMERICAL.json',numerical)
    rows,paired,faults,memory_index = [],[],[],[]
    for seed in seeds:
        reference, reference_rows, stream_first = None,None,None
        for mode in MODES:
            ident = f'{seed}-{mode}'
            memory,receipts = train(model,cases,packets,seed,mode,out/'runs'/ident)
            memory_index.append({'id':ident,'seed':seed,'mode':mode,'memory_fingerprint':memory.fingerprint,'cost':memory.cost(),
                                 'teacher_documents':len(receipts),'learned_documents':sum(r['receipt']['status']=='learned' for r in receipts),
                                 'wrong_received_teachers':sum(r['receipt'].get('received_observation')!=c['known'] for r,c in zip(receipts,cases))})
            generated = [query(model,memory,c,packets[(c['id'],'query')],mode,seed) for c in focal]
            if reference is None:
                reference, reference_rows = memory, generated
            else:
                texts = lambda rs:[[o['generation'].get('text') for o in r['result']['outputs']] for r in rs]
                paired.append({'seed':seed,'mode':mode,'coefficient_max_abs_difference':difference(reference.ss,memory.ss),
                               'generated_texts_equal':texts(generated)==texts(reference_rows),
                               'stream1_fingerprint_equal':None if stream_first is None else memory.fingerprint==stream_first})
            if mode=='stream1':
                stream_first = memory.fingerprint
            rows.extend(generated)
            if mode=='stream1':
                for condition in plan['query_faults']:
                    rows.extend(query(model,memory,c,packets[(c['id'],'query')],mode,seed,condition) for c in focal[:plan['stress_cases']])
                zero = copy.deepcopy(memory)
                for p in zero.ss.parts.values():
                    p.weights[:] = 0
                for c in focal[:plan['stress_cases']]:
                    r = query(model,zero,c,packets[(c['id'],'query')],mode,seed)
                    r['condition'] = 'coefficients_zero'
                    rows.append(r)
                faults.extend(update_faults(model,memory,focal[0],packets[(focal[0]['id'],'teacher')]['packet'],seed))
            print({'seed':seed,'mode':mode,'main_correct':sum(r['result']['correct'] for r in generated),'queries_so_far':len(rows)},flush=True)
    groups = summarize(rows)
    decision = acceptance(groups,numerical,paired,faults,input_records,plan)
    for name,value in [('ROWS.json',rows),('SUMMARY.json',groups),('PAIRED.json',paired),('UPDATE_FAULTS.json',faults),
                       ('DECISION.json',decision),('INDEX.json',{'memories':memory_index,'frozen_digest':frozen,'development':development})]:
        write(out/name,value)
    write(out/'PERFORMANCE.json',{'seconds':time.perf_counter()-start,'not_hardware_throughput':True})
    print({'complete':True,'documents':len(rows),'decision':decision},flush=True)

if __name__=='__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--out',required=True)
    p.add_argument('--development',action='store_true')
    a = p.parse_args()
    run(a.out,a.development)
