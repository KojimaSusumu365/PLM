"""Designed event identity, presentation and directed-time schema; no language rules."""
import json
from plm_l1_v06.algebra import canonical, require
from plm_l1_v06.lexicon import ROLES, validate_meaning

IDS=('event:0','event:1')
PRESENTATIONS=(list(IDS),list(reversed(IDS)))
TIMES=({'kind':'unknown','source':None,'target':None},
       {'kind':'before','source':IDS[0],'target':IDS[1]},
       {'kind':'before','source':IDS[1],'target':IDS[0]})


def temporal(value):
    require(type(value) is dict and set(value)=={'kind','source','target'},'invalid_temporal_fields')
    require(any(value==candidate for candidate in TIMES),'unsupported_temporal_relation')
    return json.loads(canonical(value))


def presentation(value):
    require(type(value) is list and any(value==candidate for candidate in PRESENTATIONS),'invalid_presentation')
    return list(value)


def normalize(meaning,candidates):
    require(type(meaning) is dict and set(meaning)=={'events','presentation','temporal'},'invalid_document_fields')
    events=meaning['events']
    require(type(events) is list and len(events)==2,'exactly_two_events_required')
    inventory={}
    for event in events:
        require(type(event) is dict and set(event)==set(ROLES)|{'id'},'invalid_event_fields')
        identity=event['id']
        require(type(identity) is str and identity in IDS and identity not in inventory,'invalid_or_duplicate_event_id')
        slots={r:event[r] for r in ROLES}
        validate_meaning(slots,candidates)
        inventory[identity]=dict(id=identity,**slots)
    return {'events':[inventory[i] for i in IDS],
            'presentation':presentation(meaning['presentation']),'temporal':temporal(meaning['temporal'])}


def write_context(time,order):
    return {**temporal(time),'presentation':presentation(order)}


def split_document(text):
    """Designed punctuation boundary only; comma-prefix meaning is learned."""
    require(type(text) is str and 0<len(text)<=550,'invalid_document_text')
    parts=text.strip().split('。')
    require(len(parts)==3 and parts[-1]=='' and all(p.strip() for p in parts[:2]),'exactly_two_terminated_sentences_required')
    first,second=parts[0].strip(),parts[1].strip()
    require('、' not in first and second.count('、')<=1,'invalid_link_boundary')
    if '、' in second:
        prefix,second=second.split('、',1)
        require(bool(prefix) and len(prefix)<=24 and prefix==prefix.strip(),'invalid_link_marker')
        marker=prefix+'、'
    else:
        marker=''
    require(bool(second) and len(first)<=255 and len(second)<=255,'invalid_clause_length')
    return [first+'。',second+'。'],marker
