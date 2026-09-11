import argparse
import copy
import hashlib
import itertools
import json
import platform
import sys
import time
from pathlib import Path
import numpy as np
from plm_l1_v013.algebra import canonical, digest
from plm_l1_v013.training import fit as original_fit
from ss_weighting.training import fit, fit_structured
from ss_weighting.memory import Memory, decide, vectors
from evaluation.weight_cases import memory_case
from evaluation.legacy_cases import queries
from evaluation.metrics import measure
from evaluation.weight_integrity import ROOT, verify, write


def metrics(scores, labels, truth, known_count):
    ps = decide(scores, labels)
    known, unknown = ps[:known_count], ps[known_count:]
    correct = sum(p['value'] == y for p, y in zip(known, truth))
    wrong = sum(p['value'] is not None and p['value'] != y for p, y in zip(known, truth))
    abstain = sum(p['value'] is None for p in known)
    false_accept = sum(p['value'] is not None for p in unknown)
    hit_counts = (scores[known_count:] >= .5).sum(axis=1)
    return {'known_requests': len(known), 'known_correct': correct, 'known_wrong': wrong, 'known_abstain': abstain,
            'unknown_requests': len(unknown), 'unknown_false_accept': false_accept, 'unknown_rejected': len(unknown)-false_accept,
            'unknown_any_hit': int(np.sum(hit_counts > 0)), 'unknown_conflicting_hits': int(np.sum(hit_counts > 1))}


def degraded_scores(model, query_vectors, condition, seed):
    d = model.metadata['dimension']
    w = model.weights
    if condition == 'erasure75':
        rng = np.random.default_rng(int(digest(['erase', seed, d])[:16], 16))
        keep = np.sort(rng.permutation(d)[:d//4])
        return (query_vectors[:, keep] @ w[:, keep].conj().T).real / len(keep)
    if condition == 'quant4':
        peak = max(float(np.abs(w.real).max()), float(np.abs(w.imag).max()))
        scale = peak / 7 if peak else 1.
        w = scale * (np.rint(w.real/scale) + 1j*np.rint(w.imag/scale))
    elif condition == 'weight_noise':
        rng = np.random.default_rng(int(digest(['noise', seed, d])[:16], 16))
        w = w + .25/np.sqrt(2)*(rng.normal(size=w.shape)+1j*rng.normal(size=w.shape))
    elif condition != 'clean':
        raise ValueError('unknown_condition')
    return (query_vectors @ w.conj().T).real / d


def structured(tasks, result, performance, out, development):
    configs = [(m, 'ss', d, s) for m, d, s in itertools.product(('uniform','positive','residual'), (128,512,2048), ('evaluation-0','evaluation-1'))]
    configs += [('exact', 'exact', 2048, 'exact')]
    if development:
        configs = [('uniform','ss',128,'evaluation-0'),('positive','ss',128,'evaluation-0'),('residual','ss',128,'evaluation-0'),('exact','exact',2048,'exact')]
        tasks = [t for t in tasks if t['family'] in ('paired_simple','paired_hidden','roles','outside_order4')]
    for task in tasks:
        original = original_fit(task['initial'], dimension=2048, seed='evaluation-0', retention='all')[0]
        request = original.select(task['pool'])
        rows = task['initial']
        prefixes = [(0, rows)]
        if request.get('status') != 'no_request':
            rows = rows + [{'context': request['context'], 'label': task['teacher_answers'][request['id']]}]
            prefixes.append((1, rows))
        prepared = queries(task)
        expected_masks = {}
        for budget, taught in prefixes:
            for method, backend, dimension, seed in configs:
                start = time.perf_counter()
                model, audits = fit_structured(taught, dimension=dimension, seed=seed, method='uniform' if method=='exact' else method, backend=backend)
                fit_time = time.perf_counter()-start
                masks = [m['mask'] for m in model.members]
                expected_masks.setdefault(budget, masks)
                assert masks == expected_masks[budget]
                all_q = [q for _, group in prepared for q in group]
                start = time.perf_counter()
                ps = model.predict_many([q['context'] for q in all_q])
                query_time = time.perf_counter()-start
                stages = []
                offset = 0
                for kind, group in prepared:
                    p = ps[offset:offset+len(group)]
                    offset += len(group)
                    stages.append({'kind': kind, 'metrics': measure([x['value'] for x in p], [q['allowed'] for q in group]),
                                   'predictions': [{'value': x['value'], 'reason': x['reason'], 'possible_labels': x['possible_labels']} for x in p]})
                    assert all(x['value'] is None or (not x['learning_insufficient'] and not x['input_insufficient'] and x['possible_labels']==[x['value']]) for x in p)
                record = {'task_id': task['id'], 'family': task['family'], 'method': method, 'backend': backend,
                          'dimension': dimension if backend=='ss' else None, 'seed': seed, 'budget': budget,
                          'actual_additional_teachers': budget, 'teacher_digest': digest(taught), 'candidate_masks': masks,
                          'unchanged_masks_and_acceptance_contract': True, 'storage': model.storage(), 'stages': stages}
                result['structured'].append(record)
                performance['structured'].append({'index':len(result['structured'])-1,'fit_seconds':fit_time,'query_seconds':query_time})
                if task['family']=='paired_hidden' and backend=='ss' and dimension==128 and seed=='evaluation-0':
                    name = f'structured-{method}-b{budget}'
                    model.save(out/name)
                    result['saved_structured'][name] = {'task_id':task['id'],'budget':budget,'method':method,'dimension':dimension,'seed':seed,'fingerprint':model.fingerprint}
        print('structured', task['id'], flush=True)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--out', required=True)
    p.add_argument('--development', action='store_true')
    a = p.parse_args()
    out = Path(a.out).resolve()
    out.mkdir(parents=True, exist_ok=False)
    protocol = json.loads((ROOT/'evaluation/WEIGHT_PROTOCOL.json').read_text(encoding='utf-8'))
    freeze_hash = 'development' if a.development else verify()
    result = {'experiment':protocol['experiment'],'freeze_hash':freeze_hash,'memory':[], 'exact':[], 'structured':[],
              'gain_controls':[], 'zero_controls':[], 'saved_models':{}, 'saved_structured':{}, 'eligible_for_inference':False}
    perf = {'environment':{'python':sys.version,'numpy':np.__version__,'platform':platform.platform()},'memory':[],'structured':[]}
    arrays = {}
    datasets = ['weight-dev-0'] if a.development else protocol['data_seeds']
    ds = [64,128] if a.development else protocol['dimensions']
    ns = [16,256] if a.development else protocol['known_key_counts']
    seeds = ['phase-dev'] if a.development else protocol['code_seeds']
    for data_seed, count in itertools.product(datasets, ns):
        case = memory_case(data_seed, count)
        teachers = case['teachers']
        contexts = [r['context'] for r in teachers]+case['unknown']
        truth = [r['label'] for r in teachers]
        assert not {canonical(r['context']) for r in teachers} & {canonical(c) for c in case['unknown']}
        exact, _ = fit(teachers, backend='exact')
        exact_metrics = metrics(exact.scores(contexts), exact.metadata['labels'], truth, count)
        assert exact_metrics['known_correct']==count and exact_metrics['unknown_false_accept']==0
        result['exact'].append({'data_seed':data_seed,'known_count':count,'metrics':exact_metrics,'storage':exact.storage()})
        for d, code_seed in itertools.product(ds, seeds):
            saved = {}
            for method in protocol['methods']:
                start = time.perf_counter()
                model, audit = fit(teachers, dimension=d, seed=code_seed, method=method)
                elapsed = time.perf_counter()-start
                qv = vectors(model.book, contexts, model.metadata['fields'])
                conditions = []
                for condition in protocol['conditions']:
                    start = time.perf_counter()
                    scores = degraded_scores(model, qv, condition, [data_seed, count, code_seed])
                    seconds = time.perf_counter()-start
                    arr_key = f's{len(arrays):04d}'
                    arrays[arr_key] = scores
                    conditions.append({'condition':condition,'scores_array':arr_key,'metrics':metrics(scores,model.metadata['labels'],truth,count)})
                    perf['memory'].append({'data_seed':data_seed,'known_count':count,'dimension':d,'code_seed':code_seed,
                                           'method':method,'condition':condition,'fit_with_diagnostics_seconds':elapsed,'correlation_seconds':seconds})
                record = {'data_seed':data_seed,'known_count':count,'dimension':d,'code_seed':code_seed,'method':method,
                          'teachers_digest':model.metadata['teachers_digest'],'storage':model.storage(),'learning':audit,'conditions':conditions}
                result['memory'].append(record)
                saved[method] = model
                if d==128 and count==256 and data_seed==datasets[0] and code_seed==seeds[0]:
                    name='memory-'+method
                    model.save(out/name)
                    write(out/(name+'-teachers.json'), teachers)
                    result['saved_models'][name]={'data_seed':data_seed,'known_count':count,'dimension':d,'code_seed':code_seed,'method':method,'fingerprint':model.fingerprint}
            u=saved['uniform']; g=saved['gain2']
            same = np.array_equal(u.weights, g.weights/2)
            assert same
            result['gain_controls'].append({'data_seed':data_seed,'known_count':count,'dimension':d,'code_seed':code_seed,
                                            'renormalized_weights_bytes_equal_uniform':same})
            assert len({m.weights.nbytes for m in saved.values()})==1
            if d==128 and count==256:
                for method, model in saved.items():
                    zero=Memory(copy.deepcopy(model.metadata),np.zeros_like(model.weights))
                    metric=metrics(zero.scores(contexts),zero.metadata['labels'],truth,count)
                    assert metric['known_abstain']==count and metric['unknown_false_accept']==0
                    result['zero_controls'].append({'data_seed':data_seed,'code_seed':code_seed,'method':method,'metrics':metric})
            print('memory',data_seed,count,d,code_seed,flush=True)
    tasks=json.loads((ROOT/'data/v013-evaluation.json').read_text(encoding='utf-8'))
    if a.development:
        from evaluation.legacy_cases import tasks as legacy_tasks
        tasks=legacy_tasks('weight-development')
    structured(tasks,result,perf,out,a.development)
    result['score_arrays']={k:{'shape':list(v.shape),'sha256':hashlib.sha256(v.astype('<f8').tobytes()).hexdigest()} for k,v in arrays.items()}
    result['all_contract_checks_passed']=True
    result['result_digest']=digest(result)
    write(out/'EVALUATION.json',result)
    write(out/'PERFORMANCE.json',perf)
    np.savez_compressed(out/'SCORES.npz',**arrays)
    print(json.dumps({'memory_models':len(result['memory']),'exact_models':len(result['exact']),'structured_models':len(result['structured']),
                      'score_arrays':len(arrays),'digest':result['result_digest']}),flush=True)


if __name__=='__main__':
    main()
