"""Pre-evaluation fixed cases. These annotations never enter numeric generation."""
import copy,itertools,random
from pathlib import Path
from .integrity import read,write
from .oracle import render
ROOT=Path(__file__).resolve().parents[1]

def prepare():
    old=read(ROOT/'data/WAVE03_CORPUS.json')
    states=list(itertools.product(('positive','negative'),('asserted','hypothetical')))
    rng=random.Random(90404);people=['太郎','花子','次郎','美咲','健太','由紀']
    predicates=['help','praise','visit','gaze_at'];extra=[]
    for i,pair in enumerate(itertools.product(states,repeat=2)):
        events=[]
        for j,(pol,mod) in enumerate(pair):
            a,b=rng.sample(people,2)
            events.append({'id':f'event:{j}','subject':'entity:'+a,'object':'entity:'+b,
                           'predicate':'predicate:'+rng.choice(predicates),'polarity':'polarity:'+pol,'modality':'modality:'+mod})
        relation={'pair':['event:0','event:1'],'kind':'unknown','source':None,'target':None}
        if i%3:relation.update(kind='before',source='event:'+str(0 if i%3==1 else 1),target='event:'+str(1 if i%3==1 else 0))
        m={'events':events,'relations':[relation],'presentation':['event:0','event:1']}
        extra.append({'id':f'extended/{i}','meaning':m,'text':render(m,['subject','object'])})
    prior_texts={r['text'] for split in old['splits'].values() for r in split}
    assert len({r['text'] for r in extra})==16 and not prior_texts&{r['text'] for r in extra}
    write(ROOT/'data/WORKING04_CORPUS.json',{'schema':'working04-corpus','seed':90404,
          'development':old['splits']['development'],'regression':old['splits']['evaluation'],'extended':extra,
          'state_pair_coverage':16,'all_lexical_temporal_combinations':False,'new_raw_corpus_learning':False})
    write(ROOT/'PROTOCOL.json',{'schema':'working04-protocol','score':.65,'margin':.25,'residual':.20,
          'main':{'regression_documents':24,'extended_documents':16,'styles':[['preserve',['subject','subject']],['reverse',['object','subject']]],'generation_requests':80},
          'updates':{'independent_targets':12,'non_target_checks_per_update':11,'save_reload':True},
          'partial_states':['unobserved','unreadable','ambiguous','conflict'],
          'faults':['zero_content','zero_status','extra_candidate','truncate','zero_lexical','zero_sentence_operand','zero_document_op','zero_domain','phase'],
          'main_success':'80/80 independently parsed correct; zero wrong generated text',
          'update_success':'12/12 target retained and 132/132 non-target cells unchanged, including save/reload generation',
          'partial_success':'4/4 held before teacher; 4/4 correct after supplied teacher',
          'scope':'bounded known-vocabulary two events; no statistical population guarantee',
          'repeats':2,'no_retuning_after_freeze':True})

if __name__=='__main__':prepare()
