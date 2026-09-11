import hashlib,itertools,json
import numpy as np

def require(ok,message):
    if not ok:raise ValueError(message)

def canonical(x):return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)
def digest(x):return hashlib.sha256(canonical(x).encode('utf-8')).hexdigest()

def terms(fields,representation):
    fields=tuple(sorted(fields))
    require(representation in ('additive','product','hybrid3'),'invalid_representation')
    if representation=='product':return [fields]
    return [t for n in range(1,2 if representation=='additive' else min(3,len(fields))+1) for t in itertools.combinations(fields,n)]

class Book:
    def __init__(self,dimension,seed):self.dimension=dimension;self.seed=seed;self.cache={}
    def atom(self,field,value):
        key=canonical([field,value])
        if key not in self.cache:
            rng=np.random.default_rng(int(digest(['v011-atom',self.seed,field,value])[:16],16))
            self.cache[key]=np.exp(2j*np.pi*rng.random(self.dimension))
        return self.cache[key]
    def vector(self,context,fields,representation):
        ts=terms(fields,representation);v=np.zeros(self.dimension,dtype=np.complex128);active=0
        for term in ts:
            if not all(f in context for f in term):continue
            z=np.ones(self.dimension,dtype=np.complex128)
            for f in term:z*=self.atom(f,context[f])
            v+=z;active+=1
        return v/np.sqrt(len(ts)),active

class BatchFeatures:
    """Training-only term cache. Never part of a saved model or decoder."""
    def __init__(self,rows,book):self.rows=rows;self.book=book;self.cache={};self.multiplies=0;self.additions=0
    def term(self,ts):
        if ts not in self.cache:
            if len(ts)==1:self.cache[ts]=np.array([self.book.atom(ts[0],c[ts[0]]) for c in self.rows])
            else:
                self.cache[ts]=self.term(ts[:-1])*self.term(ts[-1:]);self.multiplies+=len(self.rows)*self.book.dimension
        return self.cache[ts]
    def matrix(self,fields,representation):
        ts=terms(fields,representation);result=np.zeros((len(self.rows),self.book.dimension),dtype=np.complex128)
        for t in ts:result+=self.term(t)
        self.additions+=len(ts)*result.size
        return result/np.sqrt(len(ts))
    def payload(self):return sum(a.nbytes for a in self.cache.values())
