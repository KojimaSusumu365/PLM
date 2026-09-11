"""Evaluator-only synthetic grammar; never imported by the new runtime/learner."""
import copy
import importlib.util
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parent
V07=ROOT/'vendor'/'PLM-L1-v0.7'
spec=importlib.util.spec_from_file_location('temporal_legacy_support',V07/'evaluation_support.py')
legacy=importlib.util.module_from_spec(spec); spec.loader.exec_module(legacy)
VERSIONS=[V07,legacy.V06,legacy.V05,legacy.V04,legacy.V03,legacy.V02,legacy.V01]
if str(V07) not in sys.path: sys.path.append(str(V07))
render_event,interpret=legacy.render,legacy.interpret
CATEGORIES=legacy.CATEGORIES
GOALS=legacy.GOAL_PAIRS
IDS=('event:0','event:1')
TIME_VALUES=({'kind':'unknown','source':None,'target':None},
             {'kind':'before','source':IDS[0],'target':IDS[1]},
             {'kind':'before','source':IDS[1],'target':IDS[0]})


def data(name):
    return json.loads((ROOT/'data'/(name+'.json')).read_text(encoding='utf-8'))


def local_relation(meaning,order):
    time=meaning['temporal']
    if time['kind']=='unknown': return 'unknown'
    return 'before' if time['source']==order[0] else 'after'


def render(meaning,goals):
    order=meaning['presentation']; inventory={e['id']:{k:v for k,v in e.items() if k!='id'} for e in meaning['events']}
    marker={'unknown':'','before':'その後、','after':'その前に、'}[local_relation(meaning,order)]
    return render_event(inventory[order[0]],goals[0])+marker+render_event(inventory[order[1]],goals[1])


def parse(text):
    """Separate gold grammar, does not call runtime segmentation or relation memories."""
    if type(text) is not str or text.count('。')!=2 or not text.endswith('。'): return None
    first,second,_=text.split('。')
    relation='unknown'
    if second.startswith('その後、'):
        relation='before'; second=second[len('その後、'):]
    elif second.startswith('その前に、'):
        relation='after'; second=second[len('その前に、'):]
    a,b=interpret(first+'。'),interpret(second+'。')
    if a is None or b is None: return None
    return {'events':[a,b],'relation':relation,'goals':[legacy.text_goal(first+'。'),legacy.text_goal(second+'。')]}


def expected(meaning,goals,order='preserve'):
    ids=meaning['presentation'] if order=='preserve' else list(reversed(meaning['presentation']))
    inventory={e['id']:{k:v for k,v in e.items() if k!='id'} for e in meaning['events']}
    return {'events':[inventory[i] for i in ids],'relation':local_relation(meaning,ids),'goals':list(goals)}


def to_mentions(meaning):
    """Input text has no external IDs. Gold is alpha-renamed to fresh occurrence IDs."""
    m=copy.deepcopy(meaning); rename=dict(zip(m['presentation'],IDS))
    for e in m['events']: e['id']=rename[e['id']]
    m['events']=sorted(m['events'],key=lambda e:e['id']); m['presentation']=list(IDS)
    if m['temporal']['kind']=='before':
        for field in ('source','target'): m['temporal'][field]=rename[m['temporal'][field]]
    return m


def unique_meanings(rows):
    from plm_l1_v06.algebra import canonical
    by={canonical(r['meaning']):r for r in rows}
    return [by[k] for k in sorted(by)]
