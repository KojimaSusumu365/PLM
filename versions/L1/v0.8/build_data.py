"""Build before evaluation: new temporal pair labels, old controlled event grammar."""
import copy
import importlib.util
import json
from plm_l1_v06.algebra import canonical,digest
from evaluation_support import ROOT,V07,legacy,CATEGORIES,GOALS,IDS,TIME_VALUES,render,parse,expected


def write(path,value):
    with path.open('x',encoding='utf-8') as f: f.write(json.dumps(value,ensure_ascii=False,indent=2)+'\n')


def pair_key(events):
    return canonical(sorted(events,key=canonical))


def pool(split):
    # The inherited corpus constructor requires its own evaluator module globals.
    path=V07/'build_data.py'
    spec=importlib.util.spec_from_file_location('old_event_builder',path)
    module=importlib.util.module_from_spec(spec)
    # Execute with aliases supplied explicitly; avoid importing it through a
    # name that could select this new evaluator's ROOT or data directory.
    source=path.read_text(encoding='utf-8')
    source=source.replace('from evaluation_support import ROOT,data,render,CATEGORIES,GOAL_PAIRS,parse_document', '')
    module.ROOT=V07; module.data=legacy.data; module.render=legacy.render
    module.CATEGORIES=CATEGORIES; module.GOAL_PAIRS=legacy.GOAL_PAIRS; module.parse_document=legacy.parse_document
    exec(compile(source,str(path),'exec'),module.__dict__)
    return module.build(split)


def main():
    used=set(); bases={}; all_rows={}; audits={}
    for split in ('train','development','evaluation'):
        selected=[]
        candidates=pool(split)
        for category in CATEGORIES:
            count=0; local=set()
            for row in candidates:
                key=pair_key(row['meaning']['events'])
                if row['category']!=category or key in used or key in local: continue
                selected.append(row); local.add(key); count+=1
                if count==4: break
            if count!=4: raise ValueError('not enough disjoint pairs: '+split+'/'+category)
        keys={pair_key(r['meaning']['events']) for r in selected}
        assert len(keys)==36 and not keys&used
        used|=keys; bases[split]=keys; rows=[]
        for index,row in enumerate(selected):
            events=[dict(id=i,**event) for i,event in zip(IDS,row['meaning']['events'])]
            for ti,time in enumerate(TIME_VALUES):
                for pi,order in enumerate((list(IDS),list(reversed(IDS)))):
                    meaning={'events':events,'presentation':order,'temporal':time}
                    for gi,goals in enumerate([GOALS[0]] if split=='train' else GOALS):
                        text=render(meaning,goals)
                        assert parse(text)==expected(meaning,goals)
                        rows.append({'id':f'{split}-{index}-{ti}-{pi}-{gi}','category':row['category'],
                                     'text':text,'meaning':copy.deepcopy(meaning),'input_goals':goals})
        all_rows[split]=rows
        audits[split]={'base_event_pairs':36,'documents':len(rows),'unique_texts':len({r['text'] for r in rows}),
                       'unique_meanings':len({canonical(r['meaning']) for r in rows}),'digest':digest(rows),
                       'categories':{c:sum(r['category']==c for r in rows) for c in CATEGORIES}}
    assert all(not bases[a]&bases[b] for a,b in (('train','development'),('train','evaluation'),('development','evaluation')))
    write(ROOT/'data'/'temporal_train.json',[{'text':r['text'],'meaning':r['meaning']} for r in all_rows['train']])
    for split in ('development','evaluation'): write(ROOT/'data'/(split+'.json'),all_rows[split])
    write(ROOT/'data'/'TEMPORAL_SPLIT_AUDIT.json',{'schema':'plm-temporal-splits-v1','splits':audits,
          'unordered_event_pair_overlap_between_splits':0,'component_training_pairs':432,'temporal_training_pairs':len(all_rows['train']),
          'temporal_training_word_orders':[['subject','subject']],'heldout_word_order_pairs':GOALS[1:],
          'scope':'Synthetic new relation labels and combinations using old fixed grammar and lexical splits. Not human-independent or unknown grammar. Local event IDs are alpha-renamable; duplicate surface texts counted explicitly.'})
    print(json.dumps(audits,ensure_ascii=False))


if __name__=='__main__': main()
