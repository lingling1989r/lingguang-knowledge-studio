"""Chrome native messaging host. Fixed local actions; never accepts shell commands."""
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import sys
import time
import urllib.request
import urllib.error
from filelock import FileLock

HOST_NAME='com.lingguang.video'
ROOT=Path(__file__).resolve().parents[2]
DEFAULT_DATA = Path.home()/'Library/Application Support/LingguangBrowser' if sys.platform=='darwin' else Path.home()/'.local/share/LingguangBrowser'
DATA=Path(os.environ.get('LINGGUANG_BROWSER_DATA') or DEFAULT_DATA)
CONFIG=DATA/'bridge.json'
MAX_MESSAGE=900_000
JOB=re.compile(r'[a-f0-9]{32}')
FORMATS={'transcript.txt','transcript.srt','transcript.json','article.md','materials.zip','article-package.zip'}
HTTP=urllib.request.build_opener(urllib.request.ProxyHandler({}))


def read_message(stream):
    header=stream.read(4)
    if not header:return None
    if len(header)!=4:raise ValueError('消息头不完整')
    size=struct.unpack('=I',header)[0]
    if size>MAX_MESSAGE:raise ValueError('请求过大')
    data=stream.read(size)
    if len(data)!=size:raise ValueError('消息不完整')
    return json.loads(data)


def write_message(stream,value):
    data=json.dumps(value,ensure_ascii=False).encode()
    if len(data)>MAX_MESSAGE: data=b'{"error":"Response too large"}'
    stream.write(struct.pack('=I',len(data))+data)
    stream.flush()


def settings():
    if not CONFIG.exists():raise RuntimeError('请先运行本机桥接安装程序。')
    return json.loads(CONFIG.read_text())


def request(path,body=None,binary=False):
    url=f'http://127.0.0.1:{settings().get("port",18766)}'
    headers={}
    if body is not None:
        token=request('/status')['request_token']
        headers={'Content-Type':'application/json','X-Request-Token':token}
    req=urllib.request.Request(url+path,data=None if body is None else json.dumps(body).encode(),headers=headers)
    try:
        with HTTP.open(req,timeout=240 if path=='/test' else 15) as response:
            data=response.read(100*1024**2)
            return data if binary else json.loads(data)
    except urllib.error.HTTPError as exc:
        try:message=json.loads(exc.read()).get('detail','本机请求失败')
        except ValueError:message='本机请求失败'
        raise RuntimeError(message if isinstance(message,str) else '输入无效') from None


def ensure_worker():
    DATA.mkdir(parents=True,exist_ok=True)
    with FileLock(str(DATA/'startup.lock'),timeout=20):
        try:
            if request('/status').get('service')=='lingguang.browser.v1':return
            raise RuntimeError('本机端口被其他程序占用，请在桥接配置中更换端口。')
        except (urllib.error.URLError,ConnectionError,TimeoutError):pass
        config=settings()
        env=os.environ.copy()
        env.update(STUDIO_STATE_DIR=str(DATA/'state'),STUDIO_PORT=str(config.get('port',18766)))
        if config.get('model_path'):env['WHISPER_MODEL_PATH']=config['model_path']
        elif (ROOT/'.models/whisper-large-v3-turbo-q4/weights.npz').is_file():env['WHISPER_MODEL_PATH']=str(ROOT/'.models/whisper-large-v3-turbo-q4')
        env['DYLD_FALLBACK_LIBRARY_PATH']=os.pathsep.join(['/opt/homebrew/lib','/usr/local/lib',env.get('DYLD_FALLBACK_LIBRARY_PATH','')])
        env['PATH']=os.pathsep.join(['/opt/homebrew/bin','/usr/local/bin',env.get('PATH','')])
        log=open(DATA/'worker.log','ab',buffering=0)
        process=subprocess.Popen([sys.executable,'-m','uvicorn','integrations.browser.service:app','--host','127.0.0.1','--port',str(config.get('port',18766)),'--log-level','warning'],cwd=ROOT,env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
        log.close()
        (DATA/'worker.pid').write_text(str(process.pid))
        for _ in range(100):
            if process.poll() is not None:raise RuntimeError('本机组件启动失败，请查看worker.log。')
            try:
                if request('/status').get('service')=='lingguang.browser.v1':return
            except (OSError,ValueError):pass
            time.sleep(.1)
        raise RuntimeError('本机组件启动超时，请查看worker.log。')


def dispatch(value):
    operation=value.get('operation')
    if operation not in ('status','jobs','job','create','cancel','export','config','test','stop'):raise ValueError('不支持此操作')
    ensure_worker()
    if operation=='status':
        result=request('/status');result.pop('request_token',None);return result
    if operation=='stop':
        if any(j['status'] in ('running','queued') for j in request('/jobs')):raise RuntimeError('仍有任务在处理，请等待完成或先取消。')
        status=request('/status')
        if status.get('service')!='lingguang.browser.v1' or Path(status.get('data_dir',''))!=DATA/'state':raise RuntimeError('组件身份验证失败')
        import signal
        os.kill(int(status['pid']),signal.SIGTERM)
        return {'stopped':True}
    if operation=='jobs':return request('/jobs')
    if operation=='test':return request('/test',{})
    if operation=='create':
        return request('/jobs',{'url':value.get('url',''),'mode':value.get('mode','transcript'),'auto_publish':bool(value.get('auto_publish',False))})
    if operation=='config':return request('/config',value.get('config',{}))
    job_id=str(value.get('job_id',''))
    if not JOB.fullmatch(job_id):raise ValueError('任务编号无效')
    if operation=='job':return request('/jobs/'+job_id)
    if operation=='cancel':return request('/jobs/'+job_id+'/cancel',{})
    name=value.get('format')
    if name not in FORMATS:raise ValueError('不支持导出此文件')
    return {'download_url':f'http://127.0.0.1:{settings().get("port",18766)}/jobs/{job_id}/files/{name}',
        'filename':f'B站-{job_id[:8]}-{name}'}


def main():
    allowed=settings().get('allowed_origins',[])
    if len(sys.argv)<2 or sys.argv[1] not in allowed:raise SystemExit('Unpaired browser extension')
    value=None
    try:
        value=read_message(sys.stdin.buffer)
        if value is None:return
        result=dispatch(value)
        response={'id':value.get('id'),'result':result}
    except Exception as exc:
        response={'id':value.get('id') if isinstance(value,dict) else None,'error':str(exc) if isinstance(exc,(ValueError,RuntimeError)) else '本机连接失败，请检查安装和worker.log。'}
    write_message(sys.stdout.buffer,response)

if __name__=='__main__':main()
