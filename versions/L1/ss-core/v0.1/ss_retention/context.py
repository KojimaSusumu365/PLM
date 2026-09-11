from plm_l1_v09.component.algebra import digest,require
from plm_l1_v09.component.lexicon import ROLES
from ss_partial.contract import TIME_VALUES

def domain(target):return 'time' if target.startswith('time/') else target.rsplit('/',1)[1]

def labels(candidates):
    return [(r,v) for r in (*ROLES,'time') for v in (TIME_VALUES if r=='time' else candidates[r])]

def key(episode,observation,target):
    require(type(episode) is str and 1<=len(episode)<=128,'explicit_episode_id_required')
    require(type(target) is str and target in observation['cells'],'target')
    # No target value, candidate set, state, teacher label, or completed text enters the key.
    anchor={'count':observation['count'],'presentation':observation['presentation'],
            'other_cells':{k:v for k,v in observation['cells'].items() if k!=target}}
    return digest({'schema':'episode-correction-key-03','episode':episode,'target':target,'anchor':anchor})
