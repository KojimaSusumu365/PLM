"""Separate bounded-language oracle, not human annotation or unrestricted Japanese."""
import itertools
from .event_oracle import interpret,PREDICATES,PATTERNS,PEOPLE


def render_event(event,goal):
    a,b=(event[r].split(':',1)[1] for r in ('subject','object'))
    stem={v:k for k,v in PREDICATES.items()}[event['predicate'].split(':',1)[1]]
    hypothetical=event['modality']=='modality:hypothetical'
    suffix='なかった' if event['polarity']=='polarity:negative' else 'た'
    if hypothetical:suffix+='ら'
    return ('もし' if hypothetical else '')+(a+'が'+b+'を' if goal=='subject' else b+'を'+a+'が')+stem+suffix+'。'


def localize(meaning,ids,goals):
    inventory={e['id']:{k:v for k,v in e.items() if k!='id'} for e in meaning['events']}
    relations=[]
    for i,j in itertools.combinations(range(len(ids)),2):
        r=next(r for r in meaning['relations'] if set(r['pair'])=={ids[i],ids[j]})
        relations.append({'positions':[i,j],'relation':'unknown' if r['kind']=='unknown' else ('before' if r['source']==ids[i] else 'after')})
    return {'events':[inventory[x] for x in ids],'relations':relations,'goals':list(goals)}


def render(meaning,goals,reverse=False):
    ids=list(meaning['presentation']);ids=ids[::-1] if reverse else ids;m=localize(meaning,ids,goals);parts=[]
    for i,e in enumerate(m['events']):
        marker=''
        if i:
            relation=next(r['relation'] for r in m['relations'] if r['positions']==[i-1,i])
            marker={'unknown':'','before':'その後、','after':'その前に、'}[relation]
        parts.append(marker+render_event(e,goals[i]))
    return ''.join(parts)


def parse(text):
    if type(text) is not str or not text.endswith('。') or text.count('。') not in (2,3):return None
    parts=text.split('。')[:-1];events=[];goals=[];adjacent=[]
    for i,part in enumerate(parts):
        relation='unknown'
        if i:
            for prefix,label in (('その後、','before'),('その前に、','after')):
                if part.startswith(prefix):part=part[len(prefix):];relation=label;break
            adjacent.append(relation)
        event=interpret(part+'。')
        if event is None:return None
        goal=next((g for g,p in zip(('subject','object'),PATTERNS) if p.fullmatch(part+'。')),None)
        events.append(event);goals.append(goal)
    relations=[{'positions':[i,j],'relation':adjacent[i] if j==i+1 else 'unknown'} for i,j in itertools.combinations(range(len(parts)),2)]
    return {'events':events,'relations':relations,'goals':goals}


def scored(expected,generated):
    got=parse(generated)
    if got is None:return {'semantic_equal':False,'surface_valid':False,'event_order_equal':False,'relations_equal':False,'goals_equal':False}
    return {'semantic_equal':got['events']==expected['events'] and got['relations']==expected['relations'],
            'surface_valid':True,'event_order_equal':got['events']==expected['events'],
            'relations_equal':got['relations']==expected['relations'],'goals_equal':got['goals']==expected['goals']}
