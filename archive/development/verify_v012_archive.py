import hashlib,json,os,subprocess,sys,tempfile,zipfile
from pathlib import Path
outputs=Path(__file__).resolve().parents[1]/'outputs'
name='PLM-L1-v0.12'
archive=outputs/(name+'.zip')
record=json.loads((outputs/(name+'-ARCHIVE.json')).read_text(encoding='utf-8'))
with archive.open('rb') as f:assert hashlib.file_digest(f,'sha256').hexdigest()==record['sha256']
with tempfile.TemporaryDirectory(prefix='l12check-') as folder:
    base=Path(folder).resolve()
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        seen=set()
        for info in z.infolist():
            dest=(base/info.filename).resolve()
            assert dest.is_relative_to(base) and info.filename.startswith(name+'/') and len(str(dest))<250
            assert str(dest).casefold() not in seen
            seen.add(str(dest).casefold())
        z.extractall(base)
    env=dict(os.environ,OPENBLAS_NUM_THREADS='1',PYTHONIOENCODING='utf-8',PYTHONDONTWRITEBYTECODE='1',PYTHONNOUSERSITE='1')
    env.pop('PYTHONPATH',None)
    out=base/'verified'
    log_path=outputs/(name+'-ARCHIVE-VERIFICATION.log')
    with log_path.open('x',encoding='utf-8') as log:
        run=subprocess.run([sys.executable,'-B','verify_release.py','--mode','functional','--out',str(out)],cwd=base/name,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=300)
    assert run.returncode==0,log_path.read_text(encoding='utf-8')[-5000:]
    report=json.loads((out/'VERIFICATION.json').read_text(encoding='utf-8'))
    report.update({'archive':record,'archive_actually_extracted':True,'crc_verified':True,'platform_scope':'Same Windows host, fresh temporary directories; not Linux.',
                   'v011_own_tests_run_before_packaging':57,'older_nested_tests_repeated_this_turn':False})
    with (outputs/(name+'-VERIFICATION.json')).open('x',encoding='utf-8') as f:f.write(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'status':report['status'],'unit_tests':report['unit_tests'],'archive':record}),flush=True)
