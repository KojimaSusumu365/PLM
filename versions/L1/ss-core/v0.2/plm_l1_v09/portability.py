"""Functional tolerance is NOT an artifact hash and never relaxes packet binding."""
import numpy as np
from .component.banked import META_BYTES
from .thresholds import NUMERIC_ATOL, NUMERIC_RTOL

def decision_signature(model,texts):
    result=[]
    for text in texts:
        read=model.read(text)
        row={'read_status':read['status'],'reason':read.get('reason')}
        if read['status']=='read':
            packet=read['packet']; recovered=model.recover(packet)
            row['recovered']={k:v for k,v in recovered.items() if k in ('status','meaning','eligible_for_inference')}
            row['generated']=[{k:v for k,v in model.generate(packet,('object','subject'),order).items()
                               if k in ('status','text','reason','event_order','eligible_for_inference')}
                              for order in ('preserve','reverse')]
        result.append(row)
    return result

def compare(reference,candidate,texts):
    left=dict(reference.meta); right=dict(candidate.meta)
    left.pop('component_fingerprint'); right.pop('component_fingerprint')
    contract_equal=left==right and reference.component.meta==candidate.component.meta
    headers_equal=numeric_equal=exact_weights=True
    largest=0.; block_count=0
    for first,second in ((reference.component.memories,candidate.component.memories),(reference.memories,candidate.memories)):
        if set(first)!=set(second): headers_equal=False; continue
        for name in first:
            aa,bb=first[name].blocks,second[name].blocks
            if len(aa)!=len(bb): headers_equal=False
            for a,b in zip(aa,bb):
                block_count+=1; exact_weights &= a.blob==b.blob
                headers_equal &= a.blob[:META_BYTES]==b.blob[:META_BYTES]
                x=np.frombuffer(a.blob,dtype='<c16',offset=META_BYTES)
                y=np.frombuffer(b.blob,dtype='<c16',offset=META_BYTES)
                if x.shape!=y.shape: numeric_equal=False; continue
                largest=max(largest,float(np.max(np.abs(x-y))))
                numeric_equal &= bool(np.allclose(x,y,atol=NUMERIC_ATOL,rtol=NUMERIC_RTOL,equal_nan=False))
    first=decision_signature(reference,texts); second=decision_signature(candidate,texts)
    decisions_equal=first==second
    return {'functional_passed':bool(contract_equal and headers_equal and numeric_equal and decisions_equal),
            'contract_equal':contract_equal,'headers_equal':bool(headers_equal),'coefficients_within_tolerance':bool(numeric_equal),
            'decision_signatures_equal':decisions_equal,'signature_requests':len(texts),'blocks_compared':block_count,
            'max_abs_coefficient_difference':largest,'atol':NUMERIC_ATOL,'rtol':NUMERIC_RTOL,
            'exact_weight_bytes_equal':bool(exact_weights),'exact_model_fingerprint_equal':reference.fingerprint==candidate.fingerprint,
            'scope':'These finite probes only; no proof of identical decisions for every input or cross-platform execution.'}
