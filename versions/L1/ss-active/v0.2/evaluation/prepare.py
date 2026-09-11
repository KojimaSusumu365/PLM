import json
from .cases import make_case,validate
from .integrity import ROOT,write


def main():
    p=json.loads((ROOT/'evaluation/PROTOCOL.json').read_text(encoding='utf-8'));data={}
    for phase in ('development','evaluation'):
        data[phase]=[make_case(seed,size) for seed in p[phase+'_seeds'] for size in p['sizes']]
        assert all(validate(c) for c in data[phase])
    write(ROOT/'data/CASES.json',data);print({k:len(v) for k,v in data.items()})


if __name__=='__main__':main()
