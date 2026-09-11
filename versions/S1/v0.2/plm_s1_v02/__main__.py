import argparse
import json
from plm_p1.core import PhaseCodebook,encode,digest,require
from plm_p1.adapter import from_r1_envelope
from plm_p1.__main__ import load_json,write_json
from .link import Link,transmit
from .packet import to_packet,from_packet
from .receiver import Session


def main():
    parser=argparse.ArgumentParser(description="PLM-S1 v0.2 explicit baseband chip link")
    sub=parser.add_subparsers(dest="command",required=True)
    enc=sub.add_parser("encode")
    enc.add_argument("--input",required=True)
    enc.add_argument("--kind",choices=["frames","r1-envelope"],default="frames")
    enc.add_argument("--codebook",required=True)
    enc.add_argument("--link",required=True)
    enc.add_argument("--out",required=True)
    dec=sub.add_parser("decode")
    dec.add_argument("--packet",required=True)
    dec.add_argument("--catalogue",required=True)
    dec.add_argument("--query",required=True)
    dec.add_argument("--expected-codebook",required=True)
    dec.add_argument("--expected-link",required=True)
    dec.add_argument("--out",required=True)
    chk=sub.add_parser("validate-packet")
    chk.add_argument("--packet",required=True)
    args=parser.parse_args()
    try:
        if args.command=="encode":
            spec=load_json(args.codebook)
            book=PhaseCodebook(spec["dimension"],spec["seed"])
            require(book.spec==spec,"Invalid codebook spec")
            link=Link(**load_json(args.link)).validate()
            frames=load_json(args.input)
            if args.kind=="r1-envelope": frames=from_r1_envelope(frames)
            frame,norm=transmit(encode(frames,book),book,link)
            packet=to_packet(frame,None,book,link,norm,source_digest=digest(frames))
            write_json(args.out,packet)
            result={"packet_written":True,"frame_chips":link.frame_length,"tx_energy":norm["total_tx_energy"],"inference_enabled":False}
        elif args.command=="validate-packet":
            y,m,book,link,norm=from_packet(load_json(args.packet))
            result={"packet_valid":True,"frame_chips":len(y),"observed_chips":int(m.sum()),"inference_enabled":False}
        else:
            spec=load_json(args.expected_codebook)
            book=PhaseCodebook(spec["dimension"],spec["seed"])
            require(spec==book.spec,"Invalid pinned codebook")
            link=Link(**load_json(args.expected_link)).validate()
            session=Session(load_json(args.packet),load_json(args.catalogue),expected_book=book,expected_link=link)
            result=session.query(load_json(args.query))
            write_json(args.out,result)
        print(json.dumps(result,ensure_ascii=True,indent=2))
    except (ValueError,TypeError,KeyError,OSError) as error:
        parser.exit(2,"Rejected: "+str(error)+"\n")


if __name__=="__main__": main()


