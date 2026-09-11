"""Bounded evaluation grammar, independent of model decoding (not human gold)."""
import copy
import json
from pathlib import Path
from .oracle import interpret, PREDICATES, PATTERNS

ROOT = Path(__file__).resolve().parents[1]
IDS = ('event:0','event:1')

def data(name):
    return json.loads((ROOT/'data'/(name+'.json')).read_text(encoding='utf-8'))

def text_goal(text):
    return next((g for g,p in zip(('subject','object'),PATTERNS) if p.fullmatch(text)),None)

def render_event(event,goal):
    a,b=(event[r].split(':',1)[1] for r in ('subject','object'))
    stem={v:k for k,v in PREDICATES.items()}[event['predicate'].split(':',1)[1]]
    prefix='もし' if event['modality']=='modality:hypothetical' else ''
    suffix='なかった' if event['polarity']=='polarity:negative' else 'た'
    if prefix: suffix+='ら'
    return prefix+(a+'が'+b+'を' if goal=='subject' else b+'を'+a+'が')+stem+suffix+'。'

def local_relation(m,order):
    if m['temporal']['kind']=='unknown': return 'unknown'
    return 'before' if m['temporal']['source']==order[0] else 'after'

def expected(m,goals,order='preserve'):
    ids=m['presentation'] if order=='preserve' else list(reversed(m['presentation']))
    inventory={e['id']:{k:v for k,v in e.items() if k!='id'} for e in m['events']}
    return {'events':[inventory[i] for i in ids],'relation':local_relation(m,ids),'goals':list(goals)}

def parse(text):
    if type(text) is not str or text.count('。')!=2 or not text.endswith('。'): return None
    a,b,_=text.split('。'); relation='unknown'
    for marker,value in (('その後、','before'),('その前に、','after')):
        if b.startswith(marker): relation=value; b=b[len(marker):]; break
    events=[interpret(a+'。'),interpret(b+'。')]
    return {'events':events,'relation':relation,'goals':[text_goal(a+'。'),text_goal(b+'。')]} if all(e is not None for e in events) else None

def to_mentions(meaning):
    m=copy.deepcopy(meaning); rename=dict(zip(m['presentation'],IDS))
    for e in m['events']: e['id']=rename[e['id']]
    m['events']=sorted(m['events'],key=lambda e:e['id']); m['presentation']=list(IDS)
    if m['temporal']['kind']=='before':
        for f in ('source','target'): m['temporal'][f]=rename[m['temporal'][f]]
    return m

SIX_TEXTS = ('太郎が花子を助けた。','花子を太郎が助けた。','太郎が花子を助けなかった。',
             'もし太郎が花子を助けたら。','もし花子を太郎が助けたら。','もし太郎が花子を助けなかったら。')

def six_pairs():
    rows={r['text']:r for r in data('component_train')}
    return [rows[t] for t in SIX_TEXTS]
