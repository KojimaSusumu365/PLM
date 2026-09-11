import itertools
import json
import random
from pathlib import Path
from plm_l1_v09.component.algebra import canonical,digest
from .oracle import render

ROOT=Path(__file__).resolve().parents[1]


def scene_key(events):return canonical(sorted([{k:v for k,v in e.items() if k!='id'} for e in events],key=canonical))


def corpus(split,scenes_per_size=12):
    lex=json.loads((ROOT/'data/lexicon.json').read_text(encoding='utf-8'))['slot_candidates']
    train=json.loads((ROOT/'data/temporal_train.json').read_text(encoding='utf-8'))
    forbidden={scene_key(p['meaning']['events']) for p in train};rng=random.Random('ssdoc-v01/'+split)
    # Cross-split scenes share known components, never a complete unordered event collection.
    if split=='evaluation':forbidden|={scene_key(p['meaning']['events']) for p in corpus('development',4)}
    rows=[]
    for n in (2,3):
        scenes=[]
        while len(scenes)<scenes_per_size:
            events=[]
            for i in range(n):
                people=rng.sample(lex['subject'],2)
                events.append({'id':f'event:{i}','subject':people[0],'object':people[1],
                               **{r:rng.choice(lex[r]) for r in ('predicate','polarity','modality')}})
            key=scene_key(events)
            if key in forbidden:continue
            forbidden.add(key);scenes.append(events)
        for si,events in enumerate(scenes):
            for links in itertools.product(('unknown','before','after'),repeat=n-1):
                relations=[]
                for i,j in itertools.combinations(range(n),2):
                    value=links[i] if j==i+1 else 'unknown';a=f'event:{i}';b=f'event:{j}'
                    relations.append({'pair':[a,b],'kind':'unknown' if value=='unknown' else 'before',
                                      'source':None if value=='unknown' else a if value=='before' else b,
                                      'target':None if value=='unknown' else b if value=='before' else a})
                m={'events':events,'presentation':[f'event:{i}' for i in range(n)],'relations':relations}
                goals=[('subject','object')[(si+i)%2] for i in range(n)]
                rows.append({'id':f'{split}/{n}/{si}/'+','.join(links),'meaning':m,'text':render(m,goals),'input_goals':goals})
    return rows


INVALID=(
    '', '太郎が花子を助けた。', '太郎が花子を助けた。'*4,
    '太郎が花子を助けた。そのため、花子が健太を褒めた。',
    '太郎が花子を助けた。その後、彼女が健太を褒めた。',
    '太郎が花子を助けた。その後、花子が未知を褒めた。',
    '太郎が花子を助けた。その後、花子が健太を食べた。',
    '太郎が花子を助けた。その後、花子が健太を褒めた',
    '太郎が花子を助けた。。花子が健太を褒めた。',
    'その後、太郎が花子を助けた。花子が健太を褒めた。',
    '太郎が花子を助けた。その後、その前に、花子が健太を褒めた。',
    '太郎が花子を助けた。その後、花子が健太を褒めた。だから、健太が次郎を訪ねた。',
    '太郎が花子を助けた。その後、花子が健太を褒めた。健太が次郎を訪ねた。<EOS>',
    '太郎が花子を助けた。その後、花子が健太を褒めた。もし健太が次郎を訪ねた。',
)
