from plm_l1_v09.component.algebra import digest,require
from ss_retention.context import key as legacy_key

def scope_key(scope,observation):
    require(type(scope) is dict and set(scope)=={'episode','mutable'},'scope_fields')
    require(type(scope['episode']) is str and 1<=len(scope['episode'])<=128,'episode_id')
    targets=scope['mutable']
    require(type(targets) is list and 1<=len(targets)<=2 and all(type(t) is str and t in observation['cells'] for t in targets),'mutable_targets')
    require(len(set(targets))==len(targets),'duplicate_target')
    nonmutable={t:c for t,c in observation['cells'].items() if t not in targets}
    require(all(c['state']=='known' for c in nonmutable.values()),'fixed_context_incomplete')
    root=digest({'schema':'revision-scope-04','episode':scope['episode'],'mutable':sorted(targets),
                 'count':observation['count'],'presentation':observation['presentation'],'fixed_cells':nonmutable})
    return root,tuple(sorted(targets))

def address(policy,root,target,revision,scope=None,observation=None,prepared_legacy=None):
    if policy=='context':
        return prepared_legacy if prepared_legacy is not None else legacy_key(scope['episode'],observation,target)
    fields={'schema':'revision-address-04','root':root,'target':target}
    if policy=='versioned':fields['revision']=revision
    return digest(fields)

def hexadecimal(value):
    return type(value) is str and len(value)==64 and all(c in '0123456789abcdef' for c in value)
