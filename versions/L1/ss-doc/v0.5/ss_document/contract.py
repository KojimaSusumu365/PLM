"""Designed graph/segmentation boundaries, not learned syntax or time inference."""
import itertools
from plm_l1_v09.component.algebra import canonical, require
from plm_l1_v09.component.lexicon import ROLES, validate_meaning

IDS=('event:0','event:1','event:2')


def edge(a,b,source=None,target=None):
    pair=sorted((a,b))
    return {'pair':pair,'kind':'unknown' if source is None else 'before','source':source,'target':target}


def normalize(meaning,candidates):
    require(type(meaning) is dict and set(meaning)=={'events','presentation','relations'},'document_fields')
    events=meaning['events'];require(type(events) is list and len(events) in (2,3),'two_or_three_events_required')
    ids=IDS[:len(events)];inventory={}
    for e in events:
        require(type(e) is dict and set(e)==set(ROLES)|{'id'},'event_fields')
        require(type(e['id']) is str and e['id'] in ids and e['id'] not in inventory,'event_identity')
        slots={r:e[r] for r in ROLES};validate_meaning(slots,candidates);inventory[e['id']]=dict(id=e['id'],**slots)
    order=meaning['presentation']
    require(type(order) is list and len(order)==len(ids) and all(type(i) is str for i in order) and set(order)==set(ids),'presentation_inventory')
    expected=list(itertools.combinations(ids,2));relations=meaning['relations']
    require(type(relations) is list and len(relations)==len(expected),'complete_pair_inventory')
    by={}
    for r in relations:
        require(type(r) is dict and set(r)=={'pair','kind','source','target'},'relation_fields')
        require(type(r['pair']) is list and len(r['pair'])==2 and all(type(x) is str for x in r['pair']),'pair_fields')
        pair=tuple(r['pair']);require(pair in expected and pair not in by,'ordered_unique_pair')
        require(r['kind'] in ('unknown','before'),'explicit_before_or_unknown_only')
        if r['kind']=='unknown':require(r['source'] is None and r['target'] is None,'unknown_endpoints')
        else:require(type(r['source']) is str and type(r['target']) is str and {r['source'],r['target']}==set(pair),'directed_endpoints')
        by[pair]=dict(r)
    adjacent={tuple(sorted((a,b))) for a,b in zip(order,order[1:])}
    require(all(r['kind']=='unknown' for pair,r in by.items() if pair not in adjacent),'nonadjacent_relation_not_serializable')
    return {'events':[inventory[i] for i in ids],'presentation':list(order),'relations':[by[p] for p in expected]}


def split_document(text):
    require(type(text) is str and 0<len(text)<=850,'document_text')
    parts=text.strip().split('。')
    require(len(parts) in (3,4) and parts[-1]=='' and all(p.strip() for p in parts[:-1]),'two_or_three_terminated_sentences')
    clauses=[];markers=[]
    for i,part in enumerate(parts[:-1]):
        part=part.strip();require(part.count('、')<=1 and (i>0 or '、' not in part),'link_boundary')
        marker=''
        if '、' in part:
            prefix,part=part.split('、',1)
            require(prefix and prefix==prefix.strip() and len(prefix)<=24,'link_prefix')
            marker=prefix+'、'
        require(bool(part) and len(part)<=255,'clause_length')
        clauses.append(part+'。')
        if i:markers.append(marker)
    return clauses,markers


def pair_relation(meaning,a,b):
    return next(r for r in meaning['relations'] if r['pair']==sorted((a,b)))


def local_time(relation):
    """Rename endpoints to the existing two-event relation-memory schema."""
    if relation['kind']=='unknown':return {'kind':'unknown','source':None,'target':None}
    rename=dict(zip(relation['pair'],IDS[:2]))
    return {'kind':'before','source':rename[relation['source']],'target':rename[relation['target']]}
