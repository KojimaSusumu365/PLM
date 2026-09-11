"""Explicit text/teacher/diagnostic boundary. Not imported by the numeric core."""
import json
from pathlib import Path
import numpy as np
from plm_l1_v09.component.algebra import require
from .memory import WorkingMemory

def controls(core,order='preserve',goals=('subject','subject')):
    require(order in ('preserve','reverse') and len(goals)==2 and all(g in ('subject','object') for g in goals),'controls')
    return core.order_signals[('preserve','reverse').index(order)],np.array([core.goal_signals[('subject','object').index(g)] for g in goals])

def teacher(core,root,address,value):
    io=json.loads((Path(root)/'bundle04/IO.json').read_text(encoding='utf-8'))
    i=io['addresses'].index(address)
    require(value in io['domains'][i],'teacher_domain')
    return core.schema.addresses[i].copy(),core.schema.values[io['values'].index(value)].copy()

def from_observation(core,root,observation):
    """External annotated input only; no reading of a WM's hidden true values."""
    io=json.loads((Path(root)/'bundle04/IO.json').read_text(encoding='utf-8'));s=core.schema
    require(type(observation) is dict and set(observation)=={'count','presentation','cells'},'observation_fields')
    require(type(observation['count']) is int and observation['count']==2,'two_events')
    require(observation['presentation'] in (['event:0','event:1'],['event:1','event:0']),'presentation')
    require(type(observation['cells']) is dict,'observation_cells')
    cells=dict(observation['cells']);cells['presentation']={'state':'known','candidates':['order:'+str(0 if observation['presentation']==['event:0','event:1'] else 1)]}
    require(set(cells)==set(io['addresses']),'observation_addresses')
    content=s.header.copy();status=np.zeros(s.width,complex)
    for i,name in enumerate(io['addresses']):
        c=cells[name]
        require(type(c) is dict and set(c)=={'state','candidates'} and c['state'] in io['states'],'observation_cell')
        values=c['candidates'];si=io['states'].index(c['state'])
        require(type(values) is list and all(type(v) is str for v in values),'observation_candidates')
        require(len(set(values))==len(values) and all(v in io['domains'][i] for v in values),'observation_values')
        require(len(values)<len(s.arities),'arity_limit')
        content+=s.addresses[i]*sum((s.values[io['values'].index(v)] for v in values),np.zeros(s.width,complex))
        status+=s.addresses[i]*(s.states[si]+s.arities[len(values)])
    wm=WorkingMemory(np.array([content,status]),s,core.engine);wm.validate();return wm

def observe(wm,root):
    """Evaluator-only label decoder. Generation never calls this function."""
    io=json.loads((Path(root)/'bundle04/IO.json').read_text(encoding='utf-8'));out={}
    for i,name in enumerate(io['addresses']):
        c=wm.probe(wm.schema.addresses[i]);labels=[]
        for signal in c.candidates:
            labels.append(io['values'][next(j for j,v in enumerate(wm.schema.values) if np.array_equal(v,signal))])
        out[name]={'state':io['states'][c.state_number],'candidates':sorted(labels)}
    return out
