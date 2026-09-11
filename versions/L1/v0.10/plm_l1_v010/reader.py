from .base.component.algebra import canonical,digest
from .base.component.runtime import abstain

def read(model,text):
    meanings=[]; audits=[]
    for i,member in enumerate(model.members):
        out=member.read(text)
        recovered=member.recover(out['packet']) if out['status']=='read' else {}
        meaning=recovered.get('meaning')
        meanings.append(meaning)
        audits.append({'id':model.meta['candidate_ids'][i],'status':out['status'],'reason':out.get('reason'),
                       'meaning_digest':digest(meaning) if meaning is not None else None})
    if any(m is None for m in meanings): return abstain('candidate_read_unsupported',candidate_audit=audits)
    if len({canonical(m) for m in meanings})!=1: return abstain('candidate_meaning_disagreement',candidate_audit=audits)
    if not model.meta['training']['supported']: return abstain('unsupported_or_incomplete_candidate_family',candidate_audit=audits)
    packet=model.encode(meanings[0]); recovered=model.recover(packet)
    if recovered.get('meaning')!=meanings[0]: return abstain('consensus_signal_mismatch')
    return {'status':'read','packet':packet,'candidate_audit':audits,'signal_verified':True,'decision':'complete_meaning_unanimity','eligible_for_inference':False}
