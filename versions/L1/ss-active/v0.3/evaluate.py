"""Frozen passive comparison with raw scores, actual states and evaluator-only evidence."""
import argparse
import json
import time
from pathlib import Path
import numpy as np
from ss_multicode.algebra import digest
from ss_trace.runtime import State, choice, context_id
from ss_trace.learning import teach
from evaluation.cases import make_case, teaching, probes
from evaluation.integrity import ROOT, write, verify_freeze
from evaluation.metrics import measure


def run(out):
    freeze = verify_freeze(); out = Path(out); out.mkdir(parents=True, exist_ok=False)
    protocol = json.loads((ROOT/'evaluation/PROTOCOL.json').read_text(encoding='utf-8'))
    rows = []; plans = []; arrays = {}; runtimes = []; actual = 0; plan_teachers = 0
    cases = [make_case(seed,size) for size in protocol['sizes'] for seed in protocol['data_seeds']]
    write(out/'CASES.json', cases)
    start = time.perf_counter()
    for ci, case in enumerate(cases):
        pp = probes(case); contexts = [r['context'] for r in pp]; pool = case['pool']; pool_ids = {r['id'] for r in pool}
        original = {r['id']:r['label'] for g in 'ABCDE' for r in case['groups'][g]}
        base_events = teaching(case,'ABC',4); de = teaching(case,'D',2); ee = teaching(case,'E',2)
        for si, seed in enumerate(protocol['code_seeds']):
            bid = f'b{ci:02d}c{si}'; reference = State('main512',seed)
            for e in base_events: teach(reference, **e, kind='background')
            chosen = []; todo = list(pool)
            for qi in range(32):
                if qi == 16:
                    for e in de: teach(reference, **e, kind='background')
                raw = reference.raw([r['context'] for r in todo])[0]; margin = choice(raw)['margin']
                j = min(range(len(todo)), key=lambda j:(float(margin[j]),digest(['active3-plan',case['seed'],seed,todo[j]['id']])))
                r = todo.pop(j); chosen.append(r)
                teach(reference,r['context'],original[r['id']])
            plan_teachers += reference.step
            changed = [r['id'] for r in chosen[:8]] + [r['id'] for r in sorted(pool,key=lambda r:digest(['active3-drift',r['id']])) if r['id'] not in {x['id'] for x in chosen[:16]}][:8]
            plans.append({'base_id':bid,'data_seed':case['seed'],'size':case['size'],'code_seed':seed,'requests':chosen,
                          'changed_ids':changed,'reference_teacher_presentations':reference.step})
            for arm in protocol['arms']:
                base = State(arm,seed)
                for e in base_events: teach(base,**e,kind='background')
                actual += base.step
                for world in protocol['worlds']:
                    t0 = time.perf_counter(); state = base.clone(); rid = f'{bid}_{arm}_{world}'
                    last = {}; taught_correct = set(); corrected = set(); trace = []; checkpoints = []
                    truth = dict(original)

                    def checkpoint(name):
                        main, aux = state.raw(contexts); key = f'{rid}_{name}'
                        arrays[key+'_main'] = main; arrays[key+'_aux'] = aux
                        rel = 'states/'+key; state.save(out/rel)
                        cp = {'name':name,'array':key,'state':rel,'fingerprint':state.fingerprint,
                              'step':state.step,'last_teacher':dict(last),'taught_correct':sorted(taught_correct),
                              'first_corrected':sorted(corrected), 'world_truth':dict(truth)}
                        cp['metrics'] = measure(main,aux,pp,state.ledger,state.step,last,truth,corrected,taught_correct,case['size'],pool_ids)
                        checkpoints.append(cp)

                    checkpoint('base')
                    for qi, r in enumerate(chosen):
                        if qi == 16:
                            checkpoint('q16')
                            if world == 'drift_after_q16':
                                for key in changed: truth[key] = str((int(truth[key])+1)%4)
                            checkpoint('drift_only')
                            for e in de: teach(state,**e,kind='background')
                            checkpoint('post_D')
                        before = state.raw([r['context']])[0]
                        teacher_label = truth[r['id']]
                        teach(state,r['context'],teacher_label)
                        after = state.raw([r['context']])[0]
                        pre = int(choice(before)['tentative'][0]); post = int(choice(after)['tentative'][0])
                        last[r['id']] = teacher_label
                        if post == int(teacher_label): taught_correct.add(r['id'])
                        if qi < 16 and pre >= 0 and pre != int(teacher_label) and post == int(teacher_label): corrected.add(r['id'])
                        trace.append({'context':r['context'],'id':r['id'],'teacher_label':teacher_label,
                                      'before':before.tolist(),'after':after.tolist(),'step':state.step})
                    checkpoint('q32')
                    for e in ee: teach(state,**e,kind='background')
                    checkpoint('post_E')
                    actual += state.step-base.step
                    rows.append({'run_id':rid,'base_id':bid,'data_seed':case['seed'],'size':case['size'],
                                 'code_seed':seed,'arm':arm,'world':world,'plan_digest':digest(chosen),
                                 'trace':trace,'checkpoints':checkpoints,'storage':state.storage()})
                    runtimes.append({'run_id':rid,'seconds':time.perf_counter()-t0})
            print(f'Completed {bid}: {len(rows)} trajectories',flush=True)
    np.savez_compressed(out/'SCORES.npz',**arrays)
    write(out/'PLANS.json', plans)
    result = {'experiment':protocol['experiment'],'freeze':freeze,'runs':rows,
              'actual_teacher_presentations':actual,'reference_planning_teacher_presentations':plan_teachers,
              'total_teacher_presentations':actual+plan_teachers,'observation_only':True,'eligible_for_inference':False}
    write(out/'EVALUATION.json',result)
    write(out/'PERFORMANCE.json',{'total_seconds':time.perf_counter()-start,'runs':runtimes})
    print(json.dumps({k:v for k,v in result.items() if k!='runs'},indent=2),flush=True)


if __name__ == '__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',required=True);a=p.parse_args();run(a.out)
