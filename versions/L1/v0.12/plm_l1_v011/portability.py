import numpy as np

def compare(a,b,contexts):
    contract=a.meta==b.meta;arrays=len(a.members)==len(b.members);largest=0.
    for x,y in zip(a.members,b.members):
        u,v=x['weights'],y['weights']
        if u.shape!=v.shape:arrays=False;continue
        if u.size:largest=max(largest,float(np.max(np.abs(u-v))))
        arrays &= bool(np.allclose(u,v,atol=1e-12,rtol=1e-12,equal_nan=False))
    def signature(m):
        return [(p['status'],p['value'],p['reason'],[x['value'] for x in p['members']]) for c in contexts for p in [m.predict(c)]]
    decisions=signature(a)==signature(b)
    return {'functional_passed':bool(contract and arrays and decisions),'metadata_equal':contract,'coefficients_within_tolerance':bool(arrays),
            'max_coefficient_difference':largest,'atol':1e-12,'rtol':1e-12,'discrete_decisions_equal':decisions,'probes':len(contexts),
            'strict_fingerprint_equal':a.fingerprint==b.fingerprint,'linux_execution_performed':False}
