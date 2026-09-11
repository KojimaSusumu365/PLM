"""Verify frozen results, all eight releases, isolated pair training and generation."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from evaluate import verify_freeze,judge
from evaluation_support import ROOT,VERSIONS,data,parse
from plm_l1_v06.algebra import digest
from plm_l1_v08.runtime import TemporalModel,PACKET_FIELDS


def run(args,cwd,output,label,expected=0):
    env=dict(os.environ,OPENBLAS_NUM_THREADS='1',PYTHONIOENCODING='utf-8',PYTHONDONTWRITEBYTECODE='1',PYTHONNOUSERSITE='1')
    env.pop('PYTHONPATH',None)
    r=subprocess.run([sys.executable,'-B',*args],cwd=cwd,env=env,text=True,encoding='utf-8',capture_output=True,timeout=600)
    log=r.stdout+r.stderr
    (output/(label+'.log')).write_text(log,encoding='utf-8')
    if r.returncode!=expected: raise ValueError(label+': '+log[-4000:])
    return r.stdout,log


def copy_packages(target,excluded=()):
    for name in ('plm_l1_v08','plm_l1_v06'):
        (target/name).mkdir(parents=True)
        for p in sorted((ROOT/name).glob('*.py')):
            if p.name not in excluded: shutil.copyfile(p,target/name/p.name)


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--out',required=True); parser.add_argument('--preflight',action='store_true'); a=parser.parse_args()
    output=Path(a.out).resolve()
    if output.exists(): raise ValueError('fresh verification directory required')
    output.mkdir(parents=True)
    p=json.loads((ROOT/'evaluation'/'PROTOCOL.json').read_text(encoding='utf-8'))
    if a.preflight:
        from plm_l1_v08.training import fit
        model=fit(data('component_train'),data('temporal_train'),data('lexicon'))
        freeze,claimed,checks='preflight_not_frozen',None,[]
    else:
        freeze=verify_freeze(); result=json.loads((ROOT/'results'/'EVALUATION.json').read_text(encoding='utf-8'))
        claimed=result.pop('result_digest')
        if digest(result)!=claimed or result['freeze_hash']!=freeze: raise ValueError('result integrity failure')
        checks=judge(result,p)
        if checks!=result['checks'] or not all(c['passed'] for c in checks): raise ValueError('acceptance failure')
        model=TemporalModel.load(ROOT/'results'/'model')
        if model.fingerprint!=result['standard'][0]['fingerprint']: raise ValueError('model differs from evaluation')
    counts={}
    if not a.preflight:
        for label,cwd in [('NEW_TESTS',ROOT)]+[(f'V0{7-i}_TESTS',path) for i,path in enumerate(VERSIONS)]:
            _,log=run(['-m','unittest','discover','-s','tests','-v'],cwd,output,label)
            counts[label]=int(re.search(r'Ran (\d+) tests',log).group(1))
    training=output/'pair-training-only'; copy_packages(training,{'reader.py'})
    for name in ('component_train','temporal_train','lexicon'): shutil.copyfile(ROOT/'data'/(name+'.json'),training/(name+'.json'))
    assertion="from pathlib import Path; import importlib.util; assert not Path('vendor').exists(); assert not Path('evaluation.json').exists(); assert all(importlib.util.find_spec(n) is None for n in ('evaluation_support','plm_l1_v08.reader','plm_l1_v06.reader','plm_l1')); print('only explicit pair corpora and lexicon; no reader, teacher, old weights or evaluation corpus')"
    run(['-c',assertion],training,output,'PAIR_TRAIN_BOUNDARY')
    stdout,_=run(['-m','plm_l1_v08','train','--component-pairs','component_train.json','--temporal-pairs','temporal_train.json','--lexicon','lexicon.json','--seed',model.meta['seed'],'--dimension',str(model.meta['dimension']),'--mode',model.meta['mode'],'--out','model'],training,output,'PAIR_TRAIN')
    if json.loads(stdout)['fingerprint']!=model.fingerprint: raise ValueError('isolated training differs')
    reading=output/'reading-only'; copy_packages(reading,{'training.py'}); shutil.copytree(training/'model',reading/'model')
    generation=output/'generation-only'; copy_packages(generation,{'reader.py','training.py'}); shutil.copytree(training/'model',generation/'model')
    assertion="from pathlib import Path; import importlib.util; assert all(importlib.util.find_spec(n) is None for n in ('plm_l1_v08.reader','plm_l1_v08.training','plm_l1_v06.reader','plm_l1_v06.training','evaluation_support','plm_l1')); assert not Path('temporal_train.json').exists(); print('no reader/trainer/oracle/source corpus; shared learned weights and structural helpers remain')"
    run(['-c',assertion],generation,output,'GENERATION_BOUNDARY')
    texts=(
        '太郎が花子を助けた。その後、花子が健太を褒めた。',
        '花子が健太を褒めた。その前に、太郎が花子を助けた。',
        '太郎が花子を助けた。花子が健太を褒めた。',
        'もし太郎が花子を助けなかったら。その後、花子が健太を褒めた。',
        '太郎が花子を助けた。その後、太郎が花子を助けた。',
        '太郎が花子を助けた。その前に、太郎が美咲を訪ねた。')
    demos=[]
    for index,text in enumerate(texts):
        name=f'packet-{index}.json'
        run(['-m','plm_l1_v08','read','--model','model','--text',text,'--out',name],reading,output,f'READ_{index}')
        packet=json.loads((reading/name).read_text(encoding='utf-8'))
        if set(packet)!=PACKET_FIELDS or any(type(v) not in (int,float) for k in ('real','imag') for v in packet[k]): raise ValueError('non-numeric transfer')
        shutil.copyfile(reading/name,generation/name)
        stdout,_=run(['-m','plm_l1_v08','generate','--model','model','--packet',name,'--order','reverse','--goals','object','subject'],generation,output,f'GENERATE_{index}')
        out=json.loads(stdout); target=parse(text)
        target['events'].reverse(); target['goals']=['object','subject']
        if target['relation']!='unknown': target['relation']='after' if target['relation']=='before' else 'before'
        if out['status']!='generated' or parse(out['text'])!=target: raise ValueError('isolated temporal generation failed')
        demos.append({'input_for_verifier_only':text,'output':out['text'],'events_time_and_reversed_presentation_exact':True})
    assertion="import json; from unittest.mock import patch; from plm_l1_v08.runtime import TemporalModel; m=TemporalModel.load('model'); p=json.load(open('packet-0.json',encoding='utf-8')); guard=patch('plm_l1_v06.banked.dependency_leaves',side_effect=AssertionError('runtime training')); guard.start(); assert m.generate(p,order='reverse')['status']=='generated'; print('no runtime feature learning')"
    run(['-c',assertion],generation,output,'NO_RUNTIME_TRAINING')
    run(['-m','plm_l1_v08','read','--model','model','--text','太郎が花子を助けた。その後、彼が太郎を助けた。','--out','must-not-exist.json'],reading,output,'ATOMIC_ABSTAIN',expected=2)
    if (reading/'must-not-exist.json').exists(): raise ValueError('partial packet emitted')
    checked=False; manifest_path=ROOT/'RELEASE_MANIFEST.json'
    if manifest_path.exists():
        actual={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in ROOT.rglob('*') if p.is_file() and p!=manifest_path and '__pycache__' not in p.parts and p.relative_to(ROOT).parts[0]!='work'}
        if actual!=json.loads(manifest_path.read_text(encoding='utf-8'))['files']: raise ValueError('release inventory changed')
        checked=True
    report={'status':'passed','preflight_boundary_only':a.preflight,'source_freeze':freeze,'result_digest':claimed,'acceptance_checks':len(checks),
            'test_counts':counts,'component_pairs':432,'temporal_pairs':216,'model_fingerprint':model.fingerprint,
            'component_fingerprint':model.component.fingerprint,'isolated_training_without_reader_or_oracle':True,
            'isolated_training_fingerprint_equal':True,'generation_without_both_reader_and_training_entrypoints':True,
            'single_numeric_packet_only_transfer':True,'reversed_presentation_without_reversing_time':True,
            'atomic_abstention':True,'no_runtime_feature_learning':True,'isolated_roundtrips':demos,
            'release_manifest_checked':checked,'full_numeric_rerun_in_this_command':False,'python':sys.version,
            'scope':'Designed graph/bindings/boundaries; six full temporal contexts per direction learned; local IDs not cross-document identity; shared component model/helpers remain.'}
    (output/'VERIFICATION.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__': main()
