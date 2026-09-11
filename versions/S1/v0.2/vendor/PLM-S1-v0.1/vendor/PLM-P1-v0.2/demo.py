import os
os.environ.setdefault("OPENBLAS_NUM_THREADS","1")
from pathlib import Path
import plm_p1_v02
from plm_p1.core import PhaseCodebook,encode,channel
from plm_p1.__main__ import write_json
from plm_p1.adapter import source_refs
from plm_p1.packet import to_packet
from plm_p1_v02.fixtures import make_frames,entity_candidates,public_catalogue,DOC
from plm_p1_v02.recovery import Receiver
from plm_p1_v02.sync import pilot_frame,to_pilot_packet,synchronize

ROOT=Path(__file__).resolve().parent


def main():
    out=ROOT/"examples"
    out.mkdir(exist_ok=True)
    book=PhaseCodebook(2048,"plm-p1-v02-demo")
    frames=make_frames(4)
    memory=encode(frames,book)
    y,mask=channel(memory,seed=6600,keep_fraction=.25,noise_std=.15,jitter_std=.1)
    query={"document_id":DOC,"event_id":"event-000","role":"subject","candidates":entity_candidates()}
    catalogue=public_catalogue()
    recovered=Receiver(y,mask,book,catalogue).scores(**query)
    tx,config=pilot_frame(memory,book)
    rotated,rmask=channel(tx,seed=6600,keep_fraction=.25,noise_std=.15,phase_offset=1.4,jitter_std=.1)
    packet=to_pilot_packet(rotated,rmask,book,config)
    aligned,pmask,b,sync=synchronize(packet,expected_book=book)
    result=Receiver(aligned,pmask,b,catalogue).scores(**query)
    for name,value in {"INPUT_FRAMES":frames,"QUERY":query,"PUBLIC_CATALOGUE":catalogue,"CODEBOOK":book.spec,
                       "OBSERVATION_PACKET":to_packet(y,mask,book,source_refs=source_refs(frames)),"RECOVERY_RESULT":recovered,
                       "PILOT_PACKET":packet,"PILOT_RECOVERY_RESULT":result,"PILOT_SYNC_DIAGNOSTICS":sync}.items():
        write_json(out/(name+".json"),value)
    print("direct",recovered["status"],"pilot",sync["status"],result["status"])


if __name__=="__main__": main()
