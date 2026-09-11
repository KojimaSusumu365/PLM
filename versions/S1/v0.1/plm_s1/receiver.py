"""Pilot acquisition -> integer alignment/CFO/phase correction -> despread -> frozen P1."""
import math
from copy import deepcopy
import numpy as np
from plm_p1.core import address,require,ROLES,signal_array,observation_mask
from plm_p1_v02.recovery import Receiver,candidate_list,validate_catalogue
from .link import pilots,despread_aligned,shifted
from .packet import from_packet

MIN_PILOTS_PER_BLOCK=16
MIN_COHERENCE=.70
MIN_DELAY_GAP=.15


def synchronize(samples,mask,book,link,normalization):
    """Receiver sees only chips/public framing. No true delay, phase, frequency or frames."""
    y=signal_array(samples,link.frame_length)
    m=observation_mask(mask,link.frame_length)
    patterns=pilots(book,link)
    hypotheses=[]
    for delay in range(-link.max_delay_chips,link.max_delay_chips+1):
        correlations=[]
        for start,pattern in zip((link.guard_length,link.tail_start),patterns):
            ix=np.arange(start,start+link.pilot_length)+delay
            observed=m[ix]
            count=int(observed.sum())
            if count<MIN_PILOTS_PER_BLOCK: break
            ref=pattern[observed]*normalization["pilot_amplitude"]
            received=y[ix[observed]]
            cross=np.vdot(ref,received)
            product=float(np.vdot(ref,ref).real*np.vdot(received,received).real)
            require(math.isfinite(product) and np.isfinite(cross),"Pilot overflow")
            coherence=float(abs(cross)/math.sqrt(product)) if product>0 else 0.
            correlations.append((cross,coherence,float(ix[observed].mean()),count))
        if len(correlations)==2:
            quality=min(c[1] for c in correlations)
            hypotheses.append((quality,delay,correlations))
    base={"status":"abstain","reason":"insufficient_pilot_observations","estimated_delay_chips":None,
          "estimated_cfo_hz":None,"estimated_phase_rad":None,"pilot_coherence":None,"delay_score_gap":None,
          "pilot_observed_per_block":None,"eligible_for_inference":False,"scope":"bounded_integer_delay_and_small_constant_cfo"}
    empty=np.zeros(link.frame_length,complex)
    empty_mask=np.zeros(link.frame_length,bool)
    if not hypotheses: return empty,empty_mask,base
    hypotheses.sort(key=lambda row:(-row[0],row[1]))
    quality,delay,corr=hypotheses[0]
    gap=quality-(hypotheses[1][0] if len(hypotheses)>1 else 0.)
    base.update(pilot_coherence=round(quality,8),delay_score_gap=round(gap,8),pilot_observed_per_block=[c[3] for c in corr])
    if quality<MIN_COHERENCE: return empty,empty_mask,dict(base,reason="pilot_coherence_too_low")
    if gap<MIN_DELAY_GAP: return empty,empty_mask,dict(base,reason="ambiguous_integer_delay")
    separation=corr[1][2]-corr[0][2]
    cfo=float(np.angle(corr[1][0]*np.conj(corr[0][0])))*link.chip_rate_hz/(2*np.pi*separation)
    if abs(cfo)>link.max_abs_cfo_hz:
        return empty,empty_mask,dict(base,reason="estimated_cfo_outside_prior")
    terms=[]
    for start,pattern in zip((link.guard_length,link.tail_start),patterns):
        ix=np.arange(start,start+link.pilot_length)+delay
        obs=m[ix]
        terms.extend((y[ix[obs]]*pattern[obs]*np.exp(-2j*np.pi*cfo*ix[obs]/link.chip_rate_hz)).tolist())
    phase=float(np.angle(np.sum(terms)))
    corrected=y*np.exp(-1j*(phase+2*np.pi*cfo*np.arange(link.frame_length)/link.chip_rate_hz))
    aligned=shifted(corrected,-delay)
    aligned_mask=shifted(m,-delay)
    aligned[~aligned_mask]=0
    require(np.isfinite(aligned).all(),"Synchronization overflow")
    return aligned,aligned_mask,dict(base,status="aligned",reason="pilot_estimate_only_not_a_truth_guarantee",
                                  estimated_delay_chips=delay,estimated_cfo_hz=round(cfo,10),estimated_phase_rad=round(phase,10))


class Session:
    def __init__(self,packet,catalogue,*,expected_book,expected_link):
        require(expected_book is not None and expected_link is not None,"Actual receiver requires separately pinned codebook and link")
        y,m,book,link,norm=from_packet(packet,expected_book=expected_book,expected_link=expected_link)
        validate_catalogue(catalogue)
        self.book,self.link=book,link
        aligned,observed,self.synchronization=synchronize(y,m,book,link,norm)
        self.values,self.mask,self.despreading=despread_aligned(aligned,observed,book,link,norm)
        self.receiver=Receiver(self.values,self.mask,book,catalogue)

    def query(self,query):
        require(type(query) is dict and set(query)=={"document_id","event_id","role","candidates"},"Query must not contain gold/offsets/assignments")
        address(query["document_id"],query["event_id"])
        require(query["role"] in ROLES,"Unknown query role")
        candidate_list(query["candidates"])
        if self.synchronization["status"]!="aligned":
            result={"status":"abstain","selected":None,"reason":"synchronization_failed","eligible_for_inference":False}
        else:
            result=self.receiver.scores(**query)
        return dict(result,synchronization=deepcopy(self.synchronization),
                    despreading={k:v for k,v in self.despreading.items() if k!="chips_per_coordinate"},
                    ss_demodulation_implemented=True,spreading_applied=self.link.mode=="spread",
                    implementation_scope="synthetic_discrete_complex_baseband_only")
