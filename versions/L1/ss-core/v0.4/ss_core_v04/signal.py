"""SS cleanup and learned numeric-code translation, with no semantic labels."""
import numpy as np
from plm_l1_v09.component.algebra import require
from plm_l1_v09.thresholds import MIN_SCORE, MIN_MARGIN

def winner(scores):
    rank=np.argsort(-scores,kind='stable')
    top=float(scores[rank[0]])
    other=max(0.,float(scores[rank[1]])) if len(rank)>1 else 0.
    require(top>=MIN_SCORE and top-other>=MIN_MARGIN,'uncertain_signal')
    return int(rank[0])

class Association:
    def __init__(self,weights,references,engine,name):
        self.weights,self.references,self.engine,self.name=weights,references,engine,name
    def query(self,signal):
        scores=self.engine.correlate(self.weights,self.references,'map04/'+self.name,signal)[0]
        return self.references[winner(scores)].copy()

class SignalProgram:
    def __init__(self,weights,actions,states,engine,name):
        self.weights,self.actions,self.states,self.engine,self.name=weights,actions,states,engine,name
        refs=np.concatenate([actions,states])
        self.refs=np.broadcast_to(refs,(2,*refs.shape))
    def start(self):return self.states[0].copy()
    def step(self,context,state):
        key=context*state
        scores=self.engine.correlate(self.weights,self.refs,'program04/'+self.name,np.broadcast_to(key,self.weights.shape))
        a=winner(scores[0,:len(self.actions)])
        s=winner(scores[1,len(self.actions):])
        return self.actions[a].copy(),self.states[s].copy()

class Terminal:
    """Only this output boundary turns an internally selected signal into text."""
    def __init__(self,surfaces,references,engine):
        self.surfaces,self.references,self.engine=surfaces,references,engine
    def emit(self,signal):
        scores=self.engine.correlate(signal,self.references,'terminal04')[0]
        return self.surfaces[winner(scores)]
