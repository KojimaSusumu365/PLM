import copy
import random
from ss_partial.contract import from_meaning, cell
from .integrity import ROOT, read
from .prior_cases import scene, exclusions
from .oracle import render

PAIRS = [('event:0/subject','event:1/object'), ('event:0/object','event:1/subject'),
         ('event:0/predicate','event:1/polarity'), ('event:0/polarity','event:1/modality'),
         ('time/event:0,event:1','event:1/subject'), ('event:0/object','event:1/predicate')]

def build():
    lex = read(ROOT/'data/lexicon.json')['slot_candidates']
    seen = exclusions()
    seen.update(c['scene_fingerprint'] for rows in read(ROOT/'data/BRIDGE_CORPUS.json')['splits'].values() for c in rows)
    prior_count = len(seen)
    splits = {}
    for split, count in (('development',4), ('evaluation',12)):
        rng = random.Random('ss-core-01/'+split)
        rows = []
        for kind in ('focal','background'):
            for i in range(count):
                while True:
                    events = []
                    for j in range(2):
                        a,b = rng.sample(lex['subject'],2)
                        events.append({'id':f'event:{j}', 'subject':a, 'object':b,
                                       **{r:rng.choice(lex[r]) for r in ('predicate','polarity','modality')}})
                    v = rng.randrange(3)
                    meaning = {'events':events, 'presentation':['event:0','event:1'], 'relations':[
                        {'pair':['event:0','event:1'], 'kind':'unknown' if v==0 else 'before',
                         'source':None if v==0 else 'event:0' if v==1 else 'event:1',
                         'target':None if v==0 else 'event:1' if v==1 else 'event:0'}]}
                    fingerprint = scene(meaning)
                    if fingerprint not in seen:
                        seen.add(fingerprint)
                        break
                targets = list(PAIRS[i%len(PAIRS)])
                known = from_meaning(meaning, lex)
                query = copy.deepcopy(known)
                for target in targets:
                    query['cells'][target] = cell('unobserved',[])
                ident = split+'/'+kind+'/'+str(i)
                rows.append({'id':ident, 'kind':kind, 'scope':{'episode':'ss-core01/'+ident,'mutable':targets},
                             'meaning':meaning, 'known':known, 'query':query, 'scene_fingerprint':fingerprint,
                             'text':render(meaning,['subject','subject'])})
        splits[split] = rows
    return {'schema':'ss-core-corpus-01', 'prior_excluded_scenes':prior_count, 'unique_new_scenes':32,
            'splits':splits, 'known_vocabulary_and_grammar_only':True, 'eligible_for_inference':False}
