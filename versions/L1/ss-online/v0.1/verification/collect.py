from collections import Counter
import json
import statistics
import sys
import time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from ss_online.algebra import canonical
from ss_online.learning import Learner
from evaluation.integrity import sha,verify,write
from evaluation.cases import stream,make_case
from evaluate import feedback


def main():
    other=Path(sys.argv[1]).resolve();matches=[]
    for p in sorted((ROOT/'results').rglob('*')):
        if p.is_file() and p.name!='PERFORMANCE.json':
            rel=p.relative_to(ROOT/'results');h=sha(p);rh=sha(other/rel);assert h==rh
            matches.append({'file':rel.as_posix(),'sha256':h,'repeat_sha256':rh})
    write(ROOT/'verification/REPEATABILITY.json',{'freeze_hash':verify(),'all_equal':True,'files':matches,'excluded':['PERFORMANCE.json']})
    old=json.loads((ROOT/'verification/BASELINE.json').read_text(encoding='utf-8'))
    changed=[n for n,h in old['previous_files'].items() if sha(ROOT.parent/n)!=h];assert not changed
    write(ROOT/'verification/PRESERVATION.json',{'previous_files':len(old['previous_files']),'all_unchanged':True,'changed':changed})
    result=json.loads((ROOT/'results/EVALUATION.json').read_text(encoding='utf-8'))
    snapshots={};blocks={};costs={};forget={}
    for run in result['runs']:
        head=(run['scenario'],run['method'],run['dimension'])
        for b in run['blocks']:
            key=head+(b['phase'],b['epoch']);blocks.setdefault(key,Counter()).update(b['metrics'])
        for s in run['snapshots']:
            key=head+(s['phase'],s['epoch'])
            for g in s['groups']:snapshots.setdefault(key+(g['group'],),Counter()).update(g['metrics'])
            forget.setdefault(key,Counter()).update({k:v for k,v in s['forgetting'].items() if type(v) is int})
            costs.setdefault(key,[]).append(s['storage'])
    fields=('scenario','method','dimension','phase','epoch')
    summary={'trajectories':len(result['runs']),'teacher_presentations':sum(len(r['trace']) for r in result['runs']),
             'snapshots':[dict(zip(fields+('group',),k),**v) for k,v in snapshots.items()],
             'blocks':[dict(zip(fields,k),**v) for k,v in blocks.items()],
             'forgetting':[dict(zip(fields,k),**v) for k,v in forget.items()],
             'costs':[dict(zip(fields,k),**{name:{'min':min(x[name] for x in vs),'median':statistics.median(x[name] for x in vs),'max':max(x[name] for x in vs)}
                                                for name in ('weight_bytes','warm_atom_bytes','replay_utf8_bytes','learner_state_utf8_bytes','replay_entries','replay_unique_contexts','numerical_or_exact_updates')}) for k,vs in costs.items()]}
    write(ROOT/'verification/SUMMARY.json',summary)
    # Single-process, no evaluation probes, after both full runs.
    cases=make_case('online-benchmark');events=[e for b in stream(cases,'clean') for e in b['events']][:256]
    bench=[]
    for d,method in [(d,m) for d in (128,512) for m in ('accumulate','delta','delta5','replay32','exact')]:
        times=[];last=None
        for trial in range(3):
            learner=Learner.start(method,d);start=time.perf_counter()
            for e in events:
                req=learner.question(e['context'])['request'];learner,_=learner.answer(req,feedback(req,e['teacher_label']))
            times.append(time.perf_counter()-start);last=learner.storage()
        bench.append({'dimension':d,'method':method,'presentations':len(events),'seconds':times,
                      'median_ms_per_feedback':statistics.median(times)/len(events)*1000,'final_storage':last})
    write(ROOT/'verification/BENCHMARK.json',{'scope':'Single process after both evaluations. First256 teachers of independent benchmark stream, three fresh repeats. End-to-end question+transaction including fingerprints/copying/replay. Not pure kernel time, power, peak RSS, or matched total compute/RAM.', 'rows':bench})
    case=json.loads((ROOT/'data/CASES.json').read_text(encoding='utf-8'))['evaluation'][0]
    events=[e for b in stream(case,'clean') for e in b['events']]
    learner=Learner.load(ROOT/'results/delta-A');event=events[256];req=learner.question(event['context'])['request'];fb=feedback(req,event['teacher_label'])
    updated,audit=learner.answer(req,fb)
    ex=ROOT/'examples';ex.mkdir()
    write(ex/'context.json',event['context']);write(ex/'queries.json',[event['context']]);write(ex/'request.json',req);write(ex/'feedback.json',fb)
    write(ex/'EXPECTED.json',{'scope':'Artificial teacher answer, separate from prediction/request. API source is a declaration, not authentication.',
                              'before':audit['before'],'after':audit['after'],'next_state_fingerprint':updated.fingerprint})
    print(json.dumps({'equal_files':len(matches),'previous_files':len(old['previous_files']),'trajectories':len(result['runs'])}),flush=True)
    for r in summary['snapshots']:
        if r['scenario']=='clean' and r['dimension']==128 and r['phase'] in ('A','B','C','review_A') and r['group']=='A' and (r['epoch']==4 or r['phase']=='review_A'):
            print(r,flush=True)


if __name__=='__main__':main()
