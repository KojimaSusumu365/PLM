import argparse,json
from pathlib import Path
from ss_core_v03.runtime import load as load_reader
from .runtime import load
from .memory import WorkingMemory
from .boundary import controls,teacher
p=argparse.ArgumentParser();p.add_argument('--root',default=str(Path(__file__).resolve().parents[1]));p.add_argument('--text',required=True)
p.add_argument('--order',choices=('preserve','reverse'),default='preserve');p.add_argument('--focus',choices=('subject','object'),default='subject')
p.add_argument('--update',nargs=2,metavar=('ADDRESS','VALUE'),help='External teacher, e.g. event:1/subject entity:花子')
a=p.parse_args();reader=load_reader(a.root);read=reader.document.read(a.text)
if read['status']!='read':
    print(json.dumps(read,ensure_ascii=False));raise SystemExit(2)
core=load(a.root);wm=WorkingMemory.from_document(read['packet'],core.schema,core.engine)
if a.update:
    try:address,value=teacher(core,a.root,*a.update)
    except ValueError as e:
        print(json.dumps({'status':'held','text':None,'reason':str(e)},ensure_ascii=False));raise SystemExit(2)
    wm,r=core.revise_and_generate(wm,address,value,*controls(core,a.order,[a.focus,a.focus]))
else:r=core.generate(wm,*controls(core,a.order,[a.focus,a.focus]))
print(json.dumps(r,ensure_ascii=False,indent=2));raise SystemExit(0 if r['status']=='generated' else 2)
