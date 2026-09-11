import statistics,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from evaluation.integrity import read,write
from evaluation.delay_experiment import run_selection
from ss_partial.runtime import PartialModel
from ss_revision.memory import RevisionMemory
from ss_select.memory import SelectorMemory

def run():
    model=PartialModel.load(ROOT/'model');ds=read(ROOT/'data/DELAY_DATASETS.json')['splits']['400'];cases=[ds['cases'][i] for i in ds['order']]
    bid='d400-c0-versioned_shared-l64';rows=[]
    for policy in ('rule','random','ss_learned'):
        samples=[];observed=[]
        for trial in range(4):
            m=RevisionMemory.load(ROOT/'results/base_memories'/bid,model.codec.candidates);s=SelectorMemory.load(ROOT/'data/selector_model');count={'content_recall_calls':0,'selector_prediction_calls':0}
            original=m.ss.recall;predict=s.predict
            def recall(*args,**kwargs):count['content_recall_calls']+=1;return original(*args,**kwargs)
            def value(*args,**kwargs):count['selector_prediction_calls']+=1;return predict(*args,**kwargs)
            m.ss.recall=recall;s.predict=value;start=time.perf_counter();trace=run_selection(model,m,cases,policy,s,6,bid);elapsed=(time.perf_counter()-start)*1000
            if trial:samples.append(elapsed);observed.append(count)
            assert trace==read(ROOT/'results/conditions'/(bid+'-'+policy+'.json'))['trace']
        assert all(c==observed[0] for c in observed)
        rows.append({'policy':policy,**observed[0],'milliseconds':samples,'median_ms':statistics.median(samples),'content_coefficient_bytes':94208,
                     'additional_selector_cost':s.cost() if policy=='ss_learned' else {'coefficient_bytes':0,'feature_basis_bytes':0,'updates':0}})
    result={'passed':True,'fixed_base':bid,'rows':rows,'scope':'One fixed12-document selection round with6 confirmations;1 warmup and3 timed runs each. Includes shared feature extraction and feedback validation, excludes loading, delayed background and text generation. Not a general speed benchmark.',
            'eligible_for_inference':False};write(ROOT/'verification/COMPUTE_COST.json',result);print(result);return result

if __name__=='__main__':run()
