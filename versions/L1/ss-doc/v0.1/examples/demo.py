"""One-command bounded rewrite. The generator receives only the SS packet."""
import argparse
import json
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from ss_document.runtime import DocumentModel


def main():
    p=argparse.ArgumentParser();p.add_argument('--model',default=str(ROOT/'results/models/s0-c0'))
    p.add_argument('--text',default='太郎が花子を助けた。その後、花子が健太を褒めた。その後、健太が由紀を訪ねた。')
    p.add_argument('--order',choices=['preserve','reverse'],default='reverse');a=p.parse_args()
    model=DocumentModel.load(a.model);read=model.read(a.text)
    if read['status']!='read':print(json.dumps(read,ensure_ascii=False,indent=2));raise SystemExit(2)
    output=model.generate(read['packet'],a.order)
    print(json.dumps({'input':a.text,'output':output.get('text'),'status':output['status'],
                      'transport':'SS numerical packet only','eligible_for_inference':False},ensure_ascii=False,indent=2))
    if output['status']!='generated':raise SystemExit(2)


if __name__=='__main__':main()
