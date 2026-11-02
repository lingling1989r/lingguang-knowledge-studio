"""One loopback worker, owned by the browser bridge, separate from other studios."""
import os
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from app import store, pipeline, limits, agent
from app.schemas import JobRequest, canonical_video
from app import exports
from . import transcription

TOKEN=secrets.token_urlsafe(32)
PORT=os.environ.get('STUDIO_PORT','18766')

@asynccontextmanager
async def lifecycle(app):
    if not (store.STATE/'agent.json').exists():store.atomic_json(store.STATE/'agent.json',{'mode':'gpt'})
    for job in store.all_jobs():
        if job['status'] in ('running','queued'):
            store.update(job['id'],status='failed',error='本机处理进程已重启，请重新提交；已有转录片段仍保留。')
    yield

app=FastAPI(lifespan=lifecycle,docs_url=None,redoc_url=None)

@app.middleware('http')
async def local(request:Request,next_call):
    if request.headers.get('host')!=f'127.0.0.1:{PORT}' or request.headers.get('origin'):
        return JSONResponse({'detail':'仅接受本机桥接访问'},status_code=403)
    if request.method!='GET' and not secrets.compare_digest(request.headers.get('x-request-token',''),TOKEN):
        return JSONResponse({'detail':'会话无效'},status_code=403)
    response=await next_call(request)
    response.headers['Cache-Control']='no-store'
    return response

class Submit(BaseModel):
    url:str
    mode:str='transcript'
    auto_publish:bool=False

@app.get('/status')
def status():
    import shutil
    return {'service':'lingguang.browser.v1','request_token':TOKEN,'ready':True,'pid':os.getpid(),'model_ready':transcription.model_path() is not None,
        'ffmpeg_ready':bool(shutil.which('ffmpeg')),'writer_ready':agent.ready(),'data_dir':str(store.STATE)}

@app.get('/jobs')
def jobs(): return [store.public_job(j) for j in store.all_jobs()]

@app.get('/jobs/{job_id}')
def job(job_id:str):
    try:return store.public_job(store.read(job_id))
    except KeyError:raise HTTPException(404,'任务不存在')

@app.post('/jobs')
def create(value:Submit):
    try:url=canonical_video(value.url)[1]
    except ValueError as exc:raise HTTPException(422,str(exc))
    if value.mode not in ('transcript','article'):raise HTTPException(422,'不支持此处理方式')
    if value.mode=='article' and not agent.ready():raise HTTPException(422,'请先配置自己的写作模型/API。')
    if value.auto_publish and not store.feishu_config().get('app_secret'):raise HTTPException(422,'请先配置自己的飞书应用。')
    import shutil
    if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):raise HTTPException(422,'请先在设备安装FFmpeg和ffprobe。')
    if transcription.model_path() is None:raise HTTPException(422,'请先准备本地语音模型；请查看安装说明。')
    with store.LOCK:
        for old in store.all_jobs():
            if old['url']==url and old.get('browser_mode')==value.mode and old['status'] in ('running','queued'):
                return store.public_job(old)
        limits.admission()
        request=JobRequest(url=url,auto_publish=value.auto_publish if value.mode=='article' else False,contact_card=False)
        new=store.create(request,store.preferences())
        store.update(new['id'],browser_mode=value.mode)
    pipeline.EXECUTOR.submit(transcription.process if value.mode=='transcript' else pipeline.process,new['id'])
    return store.public_job(store.read(new['id']))

@app.post('/jobs/{job_id}/cancel')
def cancel(job_id:str):
    old=job(job_id)
    if old['status'] not in ('running','queued'):raise HTTPException(409,'任务已经结束')
    pipeline.cancel(job_id)
    return {'cancelled':True}

@app.get('/jobs/{job_id}/files/{name}')
def file(job_id:str,name:str):
    job(job_id)
    if name=='materials.zip':
        try:return FileResponse(exports.package(job_id),filename='materials.zip')
        except FileNotFoundError:raise HTTPException(404,'素材尚未生成')
    if name=='article-package.zip':
        import zipfile
        root=store.job_dir(job_id)
        if not (root/'output/article.md').is_file():raise HTTPException(404,'文章尚未生成')
        target=root/'article-package.zip'
        with store.LOCK, zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as archive:
            for path in (root/'output').iterdir():
                if path.suffix in ('.md','.html','.png','.jpg','.svg'):archive.write(path,path.name)
        return FileResponse(target,filename='article-package.zip')
    available=exports.files(job_id)
    for filename in ('article.md','article.html'):
        path=store.job_dir(job_id)/'output'/filename
        if path.is_file():available[filename]=path
    if name not in available:raise HTTPException(404,'文件尚未生成')
    return FileResponse(available[name],filename=name)

@app.post('/config')
def config(value:dict):
    from app.admin import model_url
    base=model_url(str(value.get('api_base','https://api.openai.com/v1')))
    old=store.ai_config()
    key=str(value.get('api_key') or old.get('api_key') or '')
    model=str(value.get('model') or old.get('model') or '').strip()
    if key and model:
        store.atomic_json(store.STATE/'ai.json',{'api_base':base,'api_key':key,'model':model})
        mode=value.get('mode','gpt')
        if mode not in ('gpt','openclacky'):raise HTTPException(422,'不支持此写作模式')
        store.atomic_json(store.STATE/'agent.json',{'mode':mode})
    if value.get('app_id') and value.get('app_secret'):
        store.atomic_json(store.STATE/'feishu.json',{'app_id':str(value['app_id']),'app_secret':str(value['app_secret'])})
    return {'saved':True}

@app.post('/test')
def test_writer():
    import json
    try:
        result=agent.complete('browser-connection-test',{'model':agent.default_model(),'messages':[{'role':'user','content':'只返回JSON对象 {"ok":true}'}],'response_format':{'type':'json_object'}},{'type':'object','properties':{'ok':{'const':True}},'required':['ok']})
        if json.loads(result).get('ok') is not True:raise ValueError()
        return {'ok':True,'message':'模型连接测试通过'}
    except Exception:raise HTTPException(422,'模型连接失败，请检查地址、模型名称、API Key和额度。')
