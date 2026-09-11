"""Post-primary implementation audit; no parameter changes or score replacement."""
import copy
import json
import math
import sys
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from evaluation.integrity import read,write,verify
from evaluation.experiment import generation,vector,signal_hash
from ss_document.runtime import DocumentModel


def main():
    verify();cases=read(ROOT/'results/CASES.json')
    case=next(c for c in cases if len(c['meaning']['events'])==3 and c['meaning']['relations'][0]['kind']=='before')
    rows=[];signals={}
    for seed in range(3):
        model=DocumentModel.load(ROOT/f'results/models/s{seed}-c0');p=model.read(case['text'])['packet'];m=model.recover(p)['meaning']
        r=m['relations'][0];pair=tuple(r['pair']);c=model.codec;i=c.relation_values[pair].index(r);assert i in (1,2)
        j=3-i;v=vector(p)+(c.relations[pair][j]-c.relations[pair][i])/math.sqrt(3.)
        expected=copy.deepcopy(m);expected['relations'][0]=copy.deepcopy(c.relation_values[pair][j])
        result=generation(model,model.packet(v),expected,'reverse',['subject']*3)
        assert result['score']['semantic_equal'] and result['reread']['semantic_equal']
        assert model.recover(model.packet(v))['meaning']==expected
        signals[f's{seed}-before']=vector(p);signals[f's{seed}-after']=v
        rows.append({'model':f's{seed}-c0','source_case':case['id'],'original_text':case['text'],'expected_meaning':expected,
                     'result':result,'before_sha256':signal_hash(p),'after_sha256':signal_hash(model.packet(v))})
    np.savez_compressed(ROOT/'verification/EDGE_REVERSAL_SIGNALS.npz',**signals)
    write(ROOT/'verification/EDGE_REVERSAL.json',{'passed':True,'post_primary_supplement':True,'rows':rows,
          'reason':'The frozen main clean_edge_edit selects the first three-event case whose initial link is unknown, so its actual operation is unknown->before, not reversal. Here an explicitly known before edge is reversed; report separately, keep original results and source freeze unchanged.'})
    ev=read(ROOT/'results/EVALUATION.json');summary=read(ROOT/'verification/SUMMARY.json')
    primary=[r for r in summary['rows'] if r['stage']=='primary']
    assert sum(r['inputs'] for r in primary)==432
    assert sum(r['generated_correct'] for r in primary)==2592
    assert sum(r['reread_semantic_correct'] for r in primary)==2592
    # Independent bookkeeping: input arrays and output requests, without treating seeds/goals as distinct texts.
    assert len(cases)==len({r['text'] for r in cases})==144
    assert len(ev['rows'])==684 and len(ev['models'])==24
    assert sum(len(r['outputs'])+1 for r in ev['rows'])==3528
    write(ROOT/'verification/AUDIT.json',{'passed':True,'unique_primary_texts':144,'primary_input_seed_pairs':432,
          'primary_connected_requests':2592,'primary_direct_requests':432,'all_input_records':684,
          'all_nonlegacy_generation_requests_including_reader_blocked':3528,
          'supplementary_known_edge_reversals':3,'note':'No final thresholds, code dimensions or model coefficients changed.'})
    print(json.dumps({'passed':True,'edge_reversals':3,'unique_primary_texts':144}))


if __name__=='__main__':main()
