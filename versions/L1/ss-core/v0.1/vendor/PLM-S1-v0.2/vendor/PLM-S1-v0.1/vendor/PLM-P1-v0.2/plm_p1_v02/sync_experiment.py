"""Matched pilot trials: same waveform/mask/noise for real, disabled, oracle paths."""
import numpy as np
from plm_p1.core import PhaseCodebook,encode,channel
from .fixtures import make_frames,entity_candidates,public_catalogue,DOC
from .recovery import Receiver
from .sync import pilot_frame,to_pilot_packet,synchronize
from .experiment import aggregates


def trial(code_seed,channel_seed):
    book=PhaseCodebook(2048,"p1-v02-code-"+str(code_seed))
    frames=make_frames(4)
    memory=encode(frames,book)
    tx,config=pilot_frame(memory,book)
    # Evaluator-only perturbation, deliberately absent from packet and receiver calls.
    phi=float(np.random.default_rng(channel_seed+470000).uniform(-np.pi,np.pi))
    y,mask=channel(tx,seed=channel_seed,keep_fraction=.25,noise_std=.15,phase_offset=phi,jitter_std=.1)
    packet=to_pilot_packet(y,mask,book,config)
    aligned,pmask,received_book,sync=synchronize(packet,expected_book=book)
    # Oracle is labelled upper reference only and NEVER used as the real sync path.
    disabled=y/config["payload_gain"]
    oracle=disabled*np.exp(-1j*phi)
    disabled[~pmask]=0
    oracle[~pmask]=0
    payload_aligned,amask=channel(tx,seed=channel_seed,keep_fraction=.25,noise_std=.15,phase_offset=0,jitter_std=.1)
    payload_aligned/=config["payload_gain"]
    payload_aligned[~pmask]=0
    signals={"pilot_estimated":aligned,"sync_disabled":disabled,"oracle_true_phase_reference":oracle,"aligned_same_pilot_budget_reference":payload_aligned}
    rows=[]
    for method,values in signals.items():
        receiver=Receiver(values,pmask,received_book,public_catalogue())
        for frame in frames:
            for role in ("subject","object"):
                truth=frame["slots"][role]
                for kind in ("present","absent_event","true_value_not_in_dictionary"):
                    candidates=[c for c in entity_candidates() if c!=truth] if kind=="true_value_not_in_dictionary" else entity_candidates()
                    event="absent-"+frame["event_id"] if kind=="absent_event" else frame["event_id"]
                    result=receiver.scores(DOC,event,role,candidates) if method!="pilot_estimated" or sync["status"]=="aligned" else {"selected":None,"reason":"pilot_synchronization_failed"}
                    outcome=("correct" if result["selected"]==truth else "abstained" if result["selected"] is None else "wrong") if kind=="present" else ("false_accept" if result["selected"] else "correct_rejection")
                    rows.append({"condition":"pilot_global_phase","method":method,"code_seed":code_seed,"channel_seed":channel_seed,
                                 "event_id":event,"role":role,"test_kind":kind,"outcome":outcome,"selected":result["selected"],"reason":result["reason"]})
    error=abs(float(np.angle(np.exp(1j*(sync["estimated_phase_rad"]-phi))))) if sync["estimated_phase_rad"] is not None else None
    audit={"code_seed":code_seed,"channel_seed":channel_seed,"evaluator_only_true_phase_rad":phi,
           "sync":sync,"absolute_wrapped_phase_error_rad":error,"payload_observed_components":int(pmask.sum()),
           "frame_dimension":2048,"pilot_length":128,"payload_length":1920,"pilot_fraction":.0625,
           "transmit_energy":round(float(np.vdot(tx,tx).real),6),"pilot_energy":3584.}
    return rows,audit


def run(codes,channels):
    rows,audits=[],[]
    for code in codes:
        for channel_seed in channels:
            r,a=trial(code,channel_seed)
            rows.extend(r)
            audits.append(a)
    errors=[a["absolute_wrapped_phase_error_rad"] for a in audits if a["absolute_wrapped_phase_error_rad"] is not None]
    return {"scope":"global phase pilot prototype, not SS demodulation", "aggregates":aggregates(rows),"rows":rows,"trials":audits,
            "phase_estimation_trials":len(audits),"phase_aligned_trials":len(errors),
            "mean_absolute_phase_error_rad":float(np.mean(errors)) if errors else None,
            "max_absolute_phase_error_rad":max(errors) if errors else None,
            "true_phase_given_to_real_receiver":False,"ss_demodulation_implemented":False}
