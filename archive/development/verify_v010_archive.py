import hashlib,json,os,subprocess,sys,tempfile,zipfile
from pathlib import Path
outputs=Path(__file__).resolve().parents[1]/'outputs'
name='PLM-L1-v0.10';archive=outputs/(name+'.zip')
record=json.loads((outputs/(name+'-ARCHIVE.json')).read_text(encoding='utf-8'))
with archive.open('rb') as f:assert hashlib.file_digest(f,'sha256').hexdigest()==record['sha256']
with tempfile.TemporaryDirectory(prefix='l10check-') as folder:
    base=Path(folder).resolve()
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        seen=set()
        for info in z.infolist():
            dest=(base/info.filename).resolve()
            assert dest.is_relative_to(base) and info.filename.startswith(name+'/')
            assert str(dest).casefold() not in seen and len(str(dest))<250
            seen.add(str(dest).casefold())
        z.extractall(base)
    cwd=base/name;out=base/'verification'
    env=dict(os.environ,OPENBLAS_NUM_THREADS='1',PYTHONIOENCODING='utf-8',PYTHONDONTWRITEBYTECODE='1',PYTHONNOUSERSITE='1')
    env.pop('PYTHONPATH',None)
    log_path=outputs/(name+'-ARCHIVE-VERIFICATION.log')
    with log_path.open('x',encoding='utf-8') as log:
        r=subprocess.run([sys.executable,'-B','verify_release.py','--mode','functional','--out',str(out)],cwd=cwd,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=1500)
    assert r.returncode==0,log_path.read_text(encoding='utf-8')[-5000:]
    report=json.loads((out/'VERIFICATION.json').read_text(encoding='utf-8'))
    legacy=json.loads((cwd/'verification/legacy/VERIFICATION.json').read_text(encoding='utf-8'))
    report.update({'archive':record,'archive_actually_extracted':True,'crc_verified':True,'post_extraction_mode':'functional',
                   'platform_scope':'Windows, fresh temporary directories; not a Linux execution',
                   'legacy_tests_executed_before_packaging_this_release':legacy['unit_tests']+sum(legacy['vendor']['test_counts'].values()),
                   'legacy_tests_repeated_by_post_extraction_command':False})
    with (outputs/(name+'-VERIFICATION.json')).open('x',encoding='utf-8') as f:f.write(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'status':report['status'],'archive':record,'unit_tests':report['unit_tests'],'previously_run_old_own_tests':report['legacy_tests_executed_before_packaging_this_release']},ensure_ascii=False),flush=True)
