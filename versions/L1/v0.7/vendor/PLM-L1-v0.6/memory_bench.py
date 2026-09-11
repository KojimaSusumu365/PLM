"""Isolated address/label association; never a larger language task."""
import hashlib
import sys
import tracemalloc
from plm_l1_v06.algebra import canonical
from plm_l1_v06.banked import fit_banked, route, META_BYTES
from measurements import count, empty_counts


def deep_size(value, seen=None):
    seen = set() if seen is None else seen
    if id(value) in seen:
        return 0
    seen.add(id(value))
    total = sys.getsizeof(value)
    if isinstance(value, dict):
        total += sum(deep_size(k,seen)+deep_size(v,seen) for k,v in value.items())
    elif isinstance(value, (tuple,list)):
        total += sum(deep_size(v,seen) for v in value)
    return total


def addresses(load, scenario):
    if scenario == "ordinary":
        return ["known:"+str(i) for i in range(load)]
    result, i = [], 0
    while len(result) < load:
        key = "collision:"+str(i)
        if route({"address":key},8) == 0:
            result.append(key)
        i += 1
    return result


def measure(dimension, load, seed, modes, missing_count, scenario="ordinary"):
    observations = [({"address":key},"label:"+str(i%8)) for i,key in enumerate(addresses(load,scenario))]
    missing = [({"address":"missing:"+str(i)},None) for i in range(missing_count)]
    methods, telemetry = {}, {}
    for mode in modes:
        memory,stats = fit_banked(observations,dimension,seed,partial=False,mode=mode,cache_slots=0)
        c,records = empty_counts(("known","missing")),[]
        for context,expected in observations+missing:
            out = memory.recall(context)
            accepted = out["value"] is not None
            prefix = "known" if expected is not None else "missing"
            count(c,prefix,accepted,accepted and expected is not None and out["value"]==expected)
            records.append({"query":context,"expected":expected,"recalled":out["value"],"projections":out["projections"]})
        c["missing_correct_rejection"] = c["missing_abstained"]
        methods[mode] = {"counts":c,"statistics":stats,"records":records,"weight_digest":hashlib.sha256(b"".join(b.blob[META_BYTES:] for b in memory.blocks)).hexdigest()}
        tracemalloc.start()
        memory.recall(missing[0][0])
        _,peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        telemetry[mode] = {"traced_peak_query_allocation_bytes":peak,"scope":"One uncached missing query; Python/NumPy traced allocations, not process RSS or hard upper bound."}
    table = {canonical(c):v for c,v in observations}
    return {"dimension":dimension,"load":load,"seed":seed,"scenario":scenario,"methods":methods,
            "table_reference":{"known_exact":sum(table.get(canonical(c))==v for c,v in observations),"known_requests":load,
                               "missing_correct_rejection":sum(table.get(canonical(c)) is None for c,_ in missing),"missing_requests":missing_count,"owned_heap_bytes":deep_size(table),"budget_matched":False}},telemetry
