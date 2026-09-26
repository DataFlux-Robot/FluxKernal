from __future__ import annotations
import io
import json
import os
import re
import uuid
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from .models import Request
from .pipeline import execute, write_json, normalize_image
from .vision import health

STATIC=Path(__file__).parent/'static'
DATA=Path(os.getenv('FK_DEMO_DATA',str(Path(__file__).resolve().parents[2]/'.demo/runs'))).resolve()
DATA.mkdir(parents=True,exist_ok=True)
app=FastAPI(title='FluxKernel Studio',docs_url=None,redoc_url=None)
app.mount('/static',StaticFiles(directory=STATIC),name='static')
WORKER=ThreadPoolExecutor(max_workers=1,thread_name_prefix='fk-design')


def directory(id):
    if not re.fullmatch('[a-f0-9]{16}',id): raise HTTPException(404,'Unknown run')
    path=DATA/id
    if not path.is_dir(): raise HTTPException(404,'Unknown run')
    return path


@app.get('/')
def index(): return FileResponse(STATIC/'index.html')


@app.get('/api/health')
def status():
    import shutil
    return {'model':health(),'lean':bool(shutil.which('lake')),'service':'FluxKernel Studio'}


@app.get('/api/examples')
def examples():
    return [{'id':id,'name':name,'image':f'/static/references/{id}.jpg'}
        for id,name in [('phone','手机'),('car','汽车'),('aircraft','飞机')]]


@app.get('/api/jobs')
def history():
    out=[]
    for p in sorted(DATA.iterdir(),key=lambda p:p.stat().st_mtime,reverse=True)[:30]:
        if (p/'result.json').exists():
            r=json.loads((p/'result.json').read_text())
            out.append({k:r[k] for k in ['id','title','family','status','duration_s','model']})
    return out


@app.post('/api/jobs')
async def create(image: UploadFile | None=File(default=None),brief: str=Form(default=''),
        mode: str=Form(default='live'),reference: str=Form(default=''),
        equipment_depth: int=Form(default=1),parent: str=Form(default='')):
    try:
        req=Request(brief=brief or '根据图片拆解产品，生成标准件、打印件与一轮加工设备设计。',
            mode=mode,reference=reference or None,equipment_depth=equipment_depth,parent=parent or None)
    except ValueError as exc: raise HTTPException(422,str(exc))
    previous=None
    if parent:
        prior=directory(parent)
        if not (prior/'design.json').exists(): raise HTTPException(400,'Parent design is unavailable')
        previous=json.loads((prior/'design.json').read_text())
    if image:
        data=await image.read(15*1024*1024+1)
    elif reference:
        data=(STATIC/'references'/f'{req.reference}.jpg').read_bytes()
    elif parent:
        data=(directory(parent)/'image.png').read_bytes()
    else: raise HTTPException(400,'请上传图片或选择参考图片')
    try: normalize_image(data)
    except Exception as exc: raise HTTPException(400,'无法读取图片或图片超出限制') from exc
    if mode=='live' and not health()['available']: raise HTTPException(503,'视觉模型未配置；可明确选择参考回放')
    id=uuid.uuid4().hex[:16];run=DATA/id;run.mkdir()
    write_json(run/'status.json',{'id':id,'state':'queued','stage':'queued','events':[]})
    WORKER.submit(execute,run,req,data,previous)
    return {'id':id,'state':'queued'}


@app.get('/api/jobs/{id}')
def job(id: str):
    p=directory(id);s=json.loads((p/'status.json').read_text())
    if (p/'result.json').exists(): s['result']=json.loads((p/'result.json').read_text())
    return s


@app.get('/api/jobs/{id}/files/{name:path}')
def artifact(id: str,name: str):
    root=directory(id);p=(root/name).resolve()
    if root not in p.parents or not p.is_file() or name.startswith('.'):
        raise HTTPException(404,'Unknown artifact')
    return FileResponse(p,filename=p.name if p.suffix in ('.step','.stl','.lean') else None)


@app.get('/api/jobs/{id}/bundle')
def bundle(id: str):
    root=directory(id)
    if not (root/'manifest.json').exists(): raise HTTPException(409,'Run not complete')
    buf=io.BytesIO()
    with zipfile.ZipFile(buf,'w',zipfile.ZIP_DEFLATED) as z:
        names=list(json.loads((root/'manifest.json').read_text()))+['manifest.json']
        for name in names:
            p=(root/name).resolve()
            if root not in p.parents or not p.is_file(): raise HTTPException(409,'Invalid artifact manifest')
            z.write(p,arcname=name)
    return Response(buf.getvalue(),media_type='application/zip',headers={'Content-Disposition':f'attachment; filename="fluxkernel-{id}.zip"'})


def main():
    import argparse,uvicorn
    parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=8740)
    parser.add_argument('--host',default='127.0.0.1');args=parser.parse_args()
    uvicorn.run(app,host=args.host,port=args.port)

if __name__=='__main__': main()
