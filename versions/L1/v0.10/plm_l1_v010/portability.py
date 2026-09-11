"""Exact artifacts stay exact; finite functional tolerance is checked separately."""
from .base.portability import compare as compare_member,decision_signature

def compare(reference,candidate,texts):
    a=dict(reference.meta); b=dict(candidate.meta); a.pop('member_fingerprints'); b.pop('member_fingerprints')
    meta_equal=a==b; count_equal=len(reference.members)==len(candidate.members)
    reports=[compare_member(x,y,[]) for x,y in zip(reference.members,candidate.members)]
    decisions=decision_signature(reference,texts)==decision_signature(candidate,texts)
    return {'functional_passed':meta_equal and count_equal and all(r['functional_passed'] for r in reports) and decisions,
            'metadata_contract_equal':meta_equal,'candidate_count_equal':count_equal,'member_comparisons':reports,
            'decision_signatures_equal':decisions,'signature_requests':len(texts),'exact_fingerprint_equal':reference.fingerprint==candidate.fingerprint,
            'scope':'Finite same-machine probes; not universal equivalence or an actual Linux run.'}
