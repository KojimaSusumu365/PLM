import sys
from pathlib import Path
R=Path(__file__).resolve().parent.parent/'outputs/PLM-L1-SS-core-v0.2';sys.path.insert(0,str(R))
from evaluation.integrity import ROOT,read,write
from evaluation.experiment02 import prepare_inputs,historical
from ss_partial.runtime import PartialModel
model=PartialModel.load(ROOT/'model');cases=read(ROOT/'data/GUARD_CORPUS.json')['splits']['development']
packets,_=prepare_inputs(model,cases)
out=ROOT.parents[1]/'work/sscore02-historical-development'
rows=historical(model,cases,packets,out)
write(out/'RESULT.json',rows)
print([{'seed':r['seed'],'mode':r['mode'],'stage':r['stage'],
        'correct':sum(s['result']['correct'] for s in r['scores']),
        'held':sum(s['result']['status']=='held' for s in r['scores']),
        'wrong':sum(s['result']['wrong'] for s in r['scores'])} for r in rows],flush=True)
