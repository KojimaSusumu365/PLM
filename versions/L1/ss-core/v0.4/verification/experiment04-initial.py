"""Independent annotated evaluation. Oracle and diagnostics are outside Core."""
import argparse,copy,json,time
from pathlib import Path
import numpy as np
from ss_core_v03.runtime import load as reader_load
from ss_core_v03.waveform import Engine,ArrayPort,PILOT
from ss_core_v04.runtime import load
from ss_core_v04.memory import WorkingMemory
from ss_core_v04.boundary import controls,teacher,observe,from_observation
from ss_partial.contract import from_meaning,cell
from .oracle import localize,scored,render
from .integrity import read,write
from .verify04 import verify

ROOT=Path(__file__).resolve().parents[1]
STYLES=[('preserve',['subject','subject']),('reverse',['object','subject'])]

def score(meaning,result,order='preserve',goals=('subject','subject')):
    ids=list(meaning['presentation']);ids=ids[::-1] if order=='reverse' else ids
    checks=scored(localize(meaning,ids,goals),result.get('text'))
    correct=result['status']=='generated' and all(checks.values())
    return {'correct':correct,'wrong_text':result['status']=='generated' and not correct,'checks':checks}

def source(case):
    reader=reader_load(ROOT);result=reader.document.read(case['text'])
    assert result['status']=='read',result
    return result['packet'],reader.engine.trace

def main_trials(out):
    corpus=read(ROOT/'data/WORKING04_CORPUS.json');baseline={(r['case'],r['style']):r for r in read(ROOT/'data/V03_MAIN.json') if r['method']=='integrated'}
    rows=[];core=load(ROOT)
    for i,case in enumerate(corpus['regression']+corpus['extended']):
        packet,read_trace=source(case);write(out/f'traces/read-{i}.json',read_trace)
        wm=WorkingMemory.from_document(packet,core.schema,core.engine)
        for style,(order,goals) in enumerate(STYLES):
            start=len(core.engine.trace);r=core.generate(wm,*controls(core,order,goals))
            old=baseline.get((case['id'],style))
            rows.append({'case':case['id'],'style':style,'input':case['text'],'result':r,
                         'baseline_text_equal':r.get('text')==old['result']['text'] if old else None,
                         **score(case['meaning'],r,order,goals)})
            write(out/f'traces/main-{i}-{style}.json',core.engine.trace[start:])
            if i==0 and style==1:
                wm.save(out/'cold/wm');order_signal,goal_signals=controls(core,order,goals)
                np.savez_compressed(out/'cold/controls.npz',order=order_signal,goals=goal_signals)
                write(out/'cold/EXPECTED.json',{'text':r['text']})
        print(json.dumps({'suite':'main','done':i+1,'of':40}),flush=True)
    write(out/'MAIN.json',rows)
    return {'requests':len(rows),'correct':sum(r['correct'] for r in rows),'wrong_text':sum(r['wrong_text'] for r in rows),
            'held':sum(r['result']['status']!='generated' for r in rows),'regression_text_equal':sum(r['baseline_text_equal'] is True for r in rows),
            'generation_ticks':sum(r['result']['cost']['ticks'] for r in rows),
            'generation_windows':sum(r['result']['cost']['windows'] for r in rows),
            'generation_products':sum(r['result']['cost']['candidate_channel_tick_products'] for r in rows),
            'reader_ticks_once_per_document':sum(read(out/f'traces/read-{i}.json')[j]['ticks'] for i in range(40) for j in range(len(read(out/f'traces/read-{i}.json')))),
            'baseline':'v03 archived output, not a new live baseline run'}

def expected_update(meaning,name,value):
    m=copy.deepcopy(meaning)
    if name=='presentation':m['presentation']=['event:0','event:1'] if value=='order:0' else ['event:1','event:0']
    elif name.startswith('time/'):
        m['relations']=[{'pair':['event:0','event:1'],'kind':'unknown' if value=='unspecified' else 'before',
                         'source':None if value=='unspecified' else 'event:'+str(0 if value=='before' else 1),
                         'target':None if value=='unspecified' else 'event:'+str(1 if value=='before' else 0)}]
    else:
        event,role=name.split('/');next(e for e in m['events'] if e['id']==event)[role]=value
    return m

def update_trials(out):
    case=read(ROOT/'data/WORKING04_CORPUS.json')['regression'][0];packet,_=source(case);core=load(ROOT)
    io=read(ROOT/'bundle04/IO.json');wm=WorkingMemory.from_document(packet,core.schema,core.engine);original=observe(wm,ROOT);rows=[]
    for i,name in enumerate(io['addresses']):
        value=next(v for v in io['domains'][i] if v not in original[name]['candidates'])
        start=len(core.engine.trace);new,r=core.revise_and_generate(wm,*teacher(core,ROOT,name,value),*controls(core))
        expected=expected_update(case['meaning'],name,value);after=observe(new,ROOT)
        same=sum(after[k]==original[k] for k in original if k!=name)
        target=after[name]=={'state':'known','candidates':[value]}
        saved=out/f'updates/wm-{i}';new.save(saved);reloaded=WorkingMemory.load(saved,core.schema,core.engine)
        reread=core.generate(reloaded,*controls(core,'reverse',['object','subject']))
        rows.append({'target':name,'teacher':value,'before_input':case['text'],'result':r,'non_targets_equal':same,'target_retained':target,
                     'reload_hash_equal':new.fingerprint==reloaded.fingerprint,'reload_result':reread,
                     'checks':score(expected,r),'reload_checks':score(expected,reread,'reverse',['object','subject']),
                     'total_cost':core.engine.stats(start)})
        write(out/f'traces/update-{i}.json',core.engine.trace[start:])
        print(json.dumps({'suite':'updates','done':i+1,'of':12}),flush=True)
    write(out/'UPDATES.json',rows)
    return {'requests':len(rows),'updated':sum(r['result'].get('update',{}).get('status')=='updated' for r in rows),
            'target_retained':sum(r['target_retained'] for r in rows),'non_targets_equal':sum(r['non_targets_equal'] for r in rows),
            'correct_generated':sum(r['checks']['correct'] for r in rows),'correct_reload_generated':sum(r['reload_checks']['correct'] for r in rows),
            'write_ticks':sum(r['result']['update'].get('write_ticks',0) for r in rows),
            'total_ticks_including_external_diagnostics':sum(r['total_cost']['ticks'] for r in rows)}

def partial_trials(out):
    from ss_partial.runtime import PartialModel
    old=PartialModel.load(ROOT/'model');case=read(ROOT/'data/WORKING04_CORPUS.json')['regression'][0];rows=[]
    for state in ('unobserved','unreadable','ambiguous','conflict'):
        core=load(ROOT);obs=from_meaning(case['meaning'],old.codec.candidates);name='event:1/subject'
        values=[] if state in ('unobserved','unreadable') else ['entity:太郎','entity:花子']
        obs['cells'][name]=cell(state,values);wm=from_observation(core,ROOT,obs)
        before=observe(wm,ROOT);r=core.generate(wm,*controls(core))
        value=case['meaning']['events'][1]['subject'];new,updated=core.revise_and_generate(wm,*teacher(core,ROOT,name,value),*controls(core))
        after=observe(new,ROOT)
        rows.append({'state':state,'held_result':r,'before_candidates':before[name],'retained_before':before[name]==cell(state,sorted(values)),
                     'update_result':updated,'non_targets_equal':sum(before[k]==after[k] for k in before if k!=name),
                     'checks':score(case['meaning'],updated)})
        write(out/f'traces/partial-{state}.json',core.engine.trace)
        print(json.dumps({'suite':'partial','state':state}),flush=True)
    write(out/'PARTIAL.json',rows)
    return {'requests':4,'held_before':sum(r['held_result']['status']=='held' for r in rows),'correct_after':sum(r['checks']['correct'] for r in rows),
            'states_retained':sum(r['retained_before'] for r in rows),'non_targets_equal':sum(r['non_targets_equal'] for r in rows)}

def fault_trials(out):
    case=read(ROOT/'data/WORKING04_CORPUS.json')['regression'][0];packet,_=source(case);rows=[]
    for kind in read(ROOT/'PROTOCOL.json')['faults']:
        def port(source,pilots,tag):
            for tick,y,mask in ArrayPort(source,pilots,tag):
                if kind=='truncate' and tick==source.shape[1]+2*PILOT-1:return
                if kind=='phase':y*=np.exp(.73j)
                yield tick,y,mask
        core=load(ROOT,Engine(port));wm=WorkingMemory.from_document(packet,core.schema,core.engine)
        if kind=='zero_content':wm.signal[0]=0
        if kind=='zero_status':wm.signal[1]=0
        if kind=='extra_candidate':
            a,v=teacher(core,ROOT,'event:1/subject','entity:太郎');wm.signal[0]+=a*v
        if kind.startswith('zero_') and kind[5:] in core.maps:core.maps[kind[5:]].weights[:]=0
        if kind=='zero_domain':core.schema.allowed[:]=0
        r=core.generate(wm,*controls(core));check=score(case['meaning'],r)
        rows.append({'fault':kind,'result':r,'expected_response':check['correct'] if kind=='phase' else r['status']=='held',**check})
        write(out/f'traces/fault-{kind}.json',core.engine.trace)
    # Supplied teacher has a real code but the wrong role-domain. No old text allowed.
    core=load(ROOT);wm=WorkingMemory.from_document(packet,core.schema,core.engine)
    a,_=teacher(core,ROOT,'event:1/subject','entity:太郎');_,v=teacher(core,ROOT,'event:0/predicate','predicate:help')
    new,r=core.revise_and_generate(wm,a,v,*controls(core));rows.append({'fault':'wrong_domain_teacher','result':r,
            'expected_response':r['status']=='held' and r['text'] is None and new.fingerprint==wm.fingerprint,'correct':False,'wrong_text':False})
    write(out/'FAULTS.json',rows)
    return {'requests':len(rows),'expected_response':sum(r['expected_response'] for r in rows),'wrong_text':sum(r['wrong_text'] for r in rows)}

def run(out,suite):
    freeze=verify();out=Path(out);out.mkdir(parents=True,exist_ok=True);started=time.perf_counter();summary={}
    functions={'main':main_trials,'updates':update_trials,'partial':partial_trials,'faults':fault_trials}
    for name,fn in functions.items():
        if suite in ('all',name):summary[name]=fn(out)
    write(out/f'SUMMARY-{suite}.json',{'freeze':freeze,**summary})
    write(out/f'TIMING-{suite}.json',{'seconds':round(time.perf_counter()-started,3)})
    verify();print(json.dumps(summary,ensure_ascii=False),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);p.add_argument('--suite',choices=('main','updates','partial','faults','all'),default='all')
    a=p.parse_args();run(a.output,a.suite)
