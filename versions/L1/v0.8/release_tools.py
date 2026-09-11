"""Non-overwriting freeze, preservation, demos and packaging."""
import argparse
import hashlib
import json
import zipfile
from evaluate import ROOT,source_files,hashes,verify_freeze
from evaluation_support import V07
from plm_l1_v06.algebra import digest
from plm_l1_v08.runtime import TemporalModel


def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x',encoding='utf-8') as f: f.write(json.dumps(value,ensure_ascii=False,indent=2)+'\n')


def main():
    p=argparse.ArgumentParser(); p.add_argument('command',choices=('freeze','check-baseline','demo','pack')); a=p.parse_args()
    if a.command=='freeze':
        m={'schema':'plm-l1-v08-source-freeze-v1','files':hashes(source_files(),ROOT)}
        write(ROOT/'SOURCE_MANIFEST.json',m); print(json.dumps({'files':len(m['files']),'digest':digest(m)}))
    elif a.command=='check-baseline':
        expected=json.loads((ROOT/'verification'/'PRESERVED_BASELINE.json').read_text(encoding='utf-8'))
        for name,h in expected.items():
            with (ROOT.parent/name).open('rb') as f:
                if hashlib.file_digest(f,'sha256').hexdigest()!=h: raise ValueError('old artifact changed: '+name)
        old=ROOT.parent/'PLM-L1-v0.7'
        if hashes([p for p in old.rglob('*') if p.is_file()],old)!=hashes([p for p in V07.rglob('*') if p.is_file()],V07): raise ValueError('vendor changed')
        for p in (ROOT/'plm_l1_v06').glob('*.py'):
            if p.read_bytes()!=(V07/'plm_l1_v06'/p.name).read_bytes(): raise ValueError('component code changed')
        print(json.dumps({'status':'unchanged','preserved_files':len(expected),'vendor_files':411,'component_python_files':10}))
    elif a.command=='demo':
        model=TemporalModel.load(ROOT/'results'/'model'); rows=[]
        texts=('太郎が花子を助けた。その後、花子が健太を褒めた。','花子が健太を褒めた。その前に、太郎が花子を助けた。',
               '太郎が花子を助けた。花子が健太を褒めた。','もし太郎が花子を助けなかったら。その後、花子が健太を褒めた。',
               '太郎が花子を助けた。その後、太郎が花子を助けた。','太郎が花子を助けた。だから、花子が健太を褒めた。')
        for i,text in enumerate(texts):
            r=model.read(text); row={'input_for_human_only':text,'read_status':r['status'],'reason':r.get('reason')}
            if r['status']=='read':
                row['meaning']=model.recover(r['packet'])['meaning']; row['preserve']=model.generate(r['packet']); row['reverse']=model.generate(r['packet'],order='reverse')
                if i==0: write(ROOT/'examples'/'MEANING.json',row['meaning']); write(ROOT/'examples'/'MEANING_PACKET.json',r['packet'])
            rows.append(row)
        write(ROOT/'examples'/'ROUNDTRIPS.json',{'scope':'human audit only, not generator input','demos':rows})
    else:
        verify_freeze()
        repeat=json.loads((ROOT/'verification'/'REPRODUCIBILITY.json').read_text(encoding='utf-8'))
        if repeat['status']!='passed' or repeat['complete_numeric_runs']!=2: raise ValueError('numeric reproduction required')
        checks=json.loads((ROOT/'verification'/'VERIFICATION.json').read_text(encoding='utf-8'))
        if checks['status']!='passed' or checks['preflight_boundary_only']: raise ValueError('full verification required')
        archive=ROOT.parent/(ROOT.name+'.zip'); checksum=ROOT.parent/(ROOT.name+'.sha256')
        if archive.exists() or checksum.exists(): raise ValueError('existing archive')
        # Historical release manifests are part of vendor; exclude only our own.
        paths=sorted(p for p in ROOT.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.relative_to(ROOT).parts[0]!='work' and p!=ROOT/'RELEASE_MANIFEST.json')
        write(ROOT/'RELEASE_MANIFEST.json',{'schema':'plm-l1-v08-release-v1','files':hashes(paths,ROOT)})
        with zipfile.ZipFile(archive,'x',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
            for p in paths+[ROOT/'RELEASE_MANIFEST.json']: z.write(p,ROOT.name+'/'+p.relative_to(ROOT).as_posix())
        with archive.open('rb') as f: h=hashlib.file_digest(f,'sha256').hexdigest()
        with checksum.open('x',encoding='utf-8') as f: f.write(h+'  '+archive.name+'\n')
        print(json.dumps({'archive':str(archive),'sha256':h,'bytes':archive.stat().st_size,'files':len(paths)+1}))


if __name__=='__main__': main()
