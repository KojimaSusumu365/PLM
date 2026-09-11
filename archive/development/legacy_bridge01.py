import subprocess,sys,time
from pathlib import Path
W=Path(__file__).resolve().parent.parent;R=W/'outputs/PLM-L1-P1-S1-v0.1';sys.path.insert(0,str(R))
from evaluation.integrity import write,preserve
rows=[]
for name,count in (('PLM-L1-SS-doc-v0.6',116),('PLM-S1-v0.2',71),('PLM-P1-v0.2',88)):
    start=time.perf_counter();p=subprocess.run([sys.executable,'-B','-m','unittest','discover','-s','tests','-v'],cwd=W/'outputs'/name,capture_output=True,text=True,encoding='utf-8')
    assert p.returncode==0 and f'Ran {count} tests' in p.stderr,p.stderr
    rows.append({'release':name,'test_count':count,'returncode':p.returncode,'stdout':p.stdout,'stderr':p.stderr,'seconds':time.perf_counter()-start})
    print({'release':name,'tests':count,'passed':True},flush=True)
write(R/'verification/LEGACY_TESTS.json',{'passed':True,'test_count':sum(r['test_count'] for r in rows),'runs':rows,
       'scope':'Original release directories, own test suites only; not all nested historical suites. Their full test suites are not duplicated in the bridge ZIP.'})
write(R/'verification/FINAL_PRESERVATION.json',preserve())
