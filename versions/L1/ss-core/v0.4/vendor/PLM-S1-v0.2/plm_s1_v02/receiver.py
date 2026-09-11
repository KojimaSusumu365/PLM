"""Joint public-pilot acquisition with frequency competitor / residual rejection."""
from copy import deepcopy
import math
import numpy as np
from plm_p1.core import require, signal_array, observation_mask, address, ROLES
from plm_p1_v02.recovery import Receiver, candidate_list, validate_catalogue
from .link import pilots, shifted, despread_aligned
from .packet import from_packet

THRESHOLDS={"min_observed_per_block":8,"min_joint_coherence":.80,"min_delay_gap":.12,
            "min_frequency_gap":.12,"frequency_competitor_separation_hz":.40,
            "min_block_signed_coherence":.65,"max_block_residual_energy_ratio":.50,
            "coarse_step_hz":.125,"refinement_divisor":8,"refinement_stages":3}


def synchronize(samples,mask,book,link,normalization):
    link.validate()
    require(book.dimension==link.dimension,"Codebook dimension mismatch")
    y=signal_array(samples,link.frame_length)
    m=observation_mask(mask,link.frame_length)
    amp=normalization["pilot_amplitude"]
    require(type(amp) in (int,float) and math.isfinite(amp) and amp>0,"Invalid pilot amplitude")
    t=THRESHOLDS
    grid=np.arange(-link.acquisition_max_abs_cfo_hz,link.acquisition_max_abs_cfo_hz+t["coarse_step_hz"]/2,t["coarse_step_hz"])
    patterns=pilots(book,link)
    hypotheses=[]
    for delay in range(-link.max_delay_chips,link.max_delay_chips+1):
        blocks=[]
        for indexes,p in zip(link.pilot_indices,patterns):
            ix=indexes+delay
            obs=m[ix]
            if int(obs.sum())<t["min_observed_per_block"]: break
            blocks.append((ix[obs]/link.chip_rate_hz,y[ix[obs]]*p[obs]/amp))
        if len(blocks)!=len(patterns): continue
        times=np.concatenate([a for a,b in blocks])
        z=np.concatenate([b for a,b in blocks])
        energy=float(np.vdot(z,z).real)
        require(math.isfinite(energy),"Pilot overflow")
        denominator=math.sqrt(len(z)*energy)
        scores=np.abs(np.exp(-2j*np.pi*grid[:,None]*times)@z)/denominator if denominator>0 else np.zeros(len(grid))
        ix=int(np.argmax(scores))
        hypotheses.append({"quality":float(scores[ix]),"delay":delay,"frequency":float(grid[ix]),
                           "scores":scores,"times":times,"z":z,"blocks":blocks,"denominator":denominator})
    base={"status":"abstain","reason":"insufficient_distributed_pilots","estimated_delay_chips":None,
          "estimated_cfo_hz":None,"estimated_phase_rad":None,"joint_coherence":None,"delay_score_gap":None,
          "frequency_score_gap":None,"pilot_observed_per_block":None,"block_signed_coherence":None,
          "block_residual_energy_ratio":None,"eligible_for_inference":False,
          "scope":"bounded_synthetic_integer_delay_constant_cfo_not_authentication"}
    def abstain(reason): return np.zeros(link.frame_length,complex),np.zeros(link.frame_length,bool),dict(base,reason=reason)
    if not hypotheses: return abstain(base["reason"])
    hypotheses.sort(key=lambda h:(-h["quality"],h["delay"]))
    best=hypotheses[0]
    frequency=best["frequency"]
    step=t["coarse_step_hz"]
    quality=best["quality"]
    if best["denominator"]>0:
        for _ in range(t["refinement_stages"]):
            local=np.linspace(frequency-step,frequency+step,2*t["refinement_divisor"]+1)
            local=local[np.abs(local)<=link.acquisition_max_abs_cfo_hz]
            scores=np.abs(np.exp(-2j*np.pi*local[:,None]*best["times"])@best["z"])/best["denominator"]
            ix=int(np.argmax(scores))
            frequency,quality=float(local[ix]),float(scores[ix])
            step/=t["refinement_divisor"]
    delay_gap=quality-(hypotheses[1]["quality"] if len(hypotheses)>1 else 0.)
    competitors=best["scores"][np.abs(grid-frequency)>=t["frequency_competitor_separation_hz"]]
    frequency_gap=quality-float(np.max(competitors))
    base.update(joint_coherence=quality,delay_score_gap=delay_gap,frequency_score_gap=frequency_gap,
                pilot_observed_per_block=[len(b) for a,b in best["blocks"]])
    if quality<t["min_joint_coherence"]: return abstain("pilot_coherence_too_low")
    if delay_gap<t["min_delay_gap"]: return abstain("ambiguous_integer_delay")
    if frequency_gap<t["min_frequency_gap"]: return abstain("ambiguous_frequency_candidates")
    if abs(frequency)>link.max_abs_cfo_hz: return abstain("estimated_cfo_outside_acceptance_range")
    corrected_pilots=best["z"]*np.exp(-2j*np.pi*frequency*best["times"])
    phase=float(np.angle(np.sum(corrected_pilots)))
    coherences,residuals=[],[]
    for times,z in best["blocks"]:
        corrected=z*np.exp(-1j*(phase+2*np.pi*frequency*times))
        energy=float(np.vdot(z,z).real)
        coherences.append(float(np.sum(corrected).real/math.sqrt(len(z)*energy)) if energy>0 else 0.)
        residuals.append(float(np.mean(abs(corrected-1)**2)))
    base.update(block_signed_coherence=coherences,block_residual_energy_ratio=residuals)
    if min(coherences)<t["min_block_signed_coherence"] or max(residuals)>t["max_block_residual_energy_ratio"]:
        return abstain("inconsistent_corrected_pilot_blocks")
    corrected=y*np.exp(-1j*(phase+2*np.pi*frequency*np.arange(link.frame_length)/link.chip_rate_hz))
    aligned=shifted(corrected,-best["delay"])
    observed=shifted(m,-best["delay"])
    aligned[~observed]=0
    require(np.isfinite(aligned).all(),"Synchronization overflow")
    return aligned,observed,dict(base,status="aligned",reason="bounded_pilot_estimate_not_truth_or_authentication",
                                  estimated_delay_chips=best["delay"],estimated_cfo_hz=frequency,estimated_phase_rad=phase)


class Session:
    def __init__(self,packet,catalogue,*,expected_book,expected_link):
        require(expected_book is not None and expected_link is not None,"Separately pinned book/link required")
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
        result=self.receiver.scores(**query) if self.synchronization["status"]=="aligned" else {
            "status":"abstain","selected":None,"reason":"synchronization_failed","eligible_for_inference":False}
        return dict(result,synchronization=deepcopy(self.synchronization),
                    despreading={k:v for k,v in self.despreading.items() if k!="chips_per_coordinate"},
                    ss_demodulation_implemented=True,spreading_applied=self.link.mode=="spread",
                    implementation_scope="synthetic_discrete_complex_baseband_only")
