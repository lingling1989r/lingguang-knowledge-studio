import json, os, secrets, zipfile
from uuid import uuid4
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import RequestValidationError
from . import store, pipeline, agent, limits
from .schemas import JobRequest, Preferences
from .publishing import Feishu
from .logging import event

TOKEN = secrets.token_urlsafe(32)
PORT = os.getenv("STUDIO_PORT", "8765")
HOSTS = {f"127.0.0.1:{PORT}", f"localhost:{PORT}"}
ORIGINS = {f"http://{host}" for host in HOSTS}

@asynccontextmanager
async def lifespan(app):
    for job in store.all_jobs():
        if job["status"] in ("queued", "running"):
            output = store.job_dir(job["id"]) / "output" / "article.html"
            store.update(job["id"],status="complete" if output.exists() else "failed",message="服务已重启，已完成稿件仍保留。",error="上次处理因服务重启中断，请重新提交或保存飞书。")
    yield

app = FastAPI(title="灵光成稿", docs_url=None, redoc_url=None, lifespan=lifespan)

@app.middleware("http")
async def local_access(request: Request, call_next):
    if request.headers.get("host") not in HOSTS:
        return JSONResponse({"detail":"此工作台仅接受本机访问。"},status_code=403)
    origin=request.headers.get("origin")
    if origin and origin not in ORIGINS:
        return JSONResponse({"detail":"不接受其他网站发起的请求。"},status_code=403)
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        if not secrets.compare_digest(request.headers.get("x-request-token", ""),TOKEN):
            return JSONResponse({"detail":"页面会话已更新，请刷新页面再试。"},status_code=403)
    response = await call_next(request)
    if request.url.path.startswith("/api") and request.method not in ("GET","HEAD"):
        event("api",request_id=uuid4().hex,method=request.method,path=request.url.path,status=response.status_code)
    response.headers["X-Content-Type-Options"]="nosniff"
    response.headers["Referrer-Policy"]="no-referrer"
    if request.url.path.startswith("/api"):
        response.headers["Cache-Control"]="no-store"
    return response

@app.exception_handler(RequestValidationError)
async def validation_error(request, exc):
    errors=exc.errors()
    msg=errors[0].get("msg","输入无效") if errors else "输入无效"
    return JSONResponse({"detail":msg.removeprefix("Value error, ")},status_code=422)

def get_job(job_id):
    try:
        return store.read(job_id)
    except KeyError:
        raise HTTPException(404,"没有找到这个任务。")

def output_file(job_id,filename):
    get_job(job_id)
    if filename!=Path(filename).name or Path(filename).suffix not in (".png",".jpg",".svg",".html",".md"):
        raise HTTPException(404,"素材不存在。")
    path=store.job_dir(job_id)/"output"/filename
    if not path.is_file():raise HTTPException(404,"素材尚未生成。")
    return path

@app.get("/api/status")
def status():
    config=store.feishu_config()
    return {"desktop":bool(os.getenv("STUDIO_DESKTOP")),"request_token":TOKEN,"feishu_connected":bool(config.get("app_id") and config.get("app_secret")),"agent_ready":agent.ready(),"preferences":store.preferences(),"max_video_minutes":limits.current().max_video_minutes}

@app.post("/api/settings")
def settings(value: Preferences, request: Request):
    if value.app_id or value.app_secret:
        from .admin import require
        require(request)
    if bool(value.app_id)!=bool(value.app_secret):
        raise HTTPException(422,"更新飞书连接时，请同时填写App ID和App Secret。")
    if value.app_id:
        try:
            Feishu({"app_id":value.app_id,"app_secret":value.app_secret})
        except Exception:
            raise HTTPException(422,"飞书连接验证失败，请检查凭据和应用权限。")
        store.atomic_json(store.STATE/"feishu.json",{"app_id":value.app_id,"app_secret":value.app_secret})
    store.save_preferences(value.model_dump(exclude={"app_id","app_secret"}))
    return {"saved":True}

@app.post('/api/rss')
def rss_episodes(value: dict):
    from .sources import feed
    try:
        episodes=feed(str(value.get('url','')))
        return {'episodes':[{k:v for k,v in e.items() if k!='media'} for e in episodes]}
    except (ValueError,RuntimeError):raise HTTPException(422,'RSS读取失败，请提供可公开访问且包含单集音频的RSS地址。')
    except Exception:raise HTTPException(422,'RSS服务暂时无法访问，请重试。')

@app.get("/api/jobs")
def jobs():return [store.public_job(j) for j in store.all_jobs()]

@app.post("/api/jobs",status_code=202)
def create_job(value: JobRequest):
    if not agent.ready():
        raise HTTPException(503,"后台写稿服务暂时不可用，请稍后重试，管理员会处理连接。")
    config=store.feishu_config()
    if value.auto_publish and not(config.get("app_id") and config.get("app_secret")):
        raise HTTPException(422,"请先连接飞书，或取消自动保存。")
    prefs=store.preferences()
    if value.contact_card and (prefs["author"]!="作者" or prefs["wechat"]!="your-wechat"):
        raise HTTPException(422,"现有真实联系卡属于作者；更换作者时请先关闭联系卡选项。")
    with store.LOCK:
        for job in store.all_jobs():
            if job["url"]==value.url and job.get("options",{}).get("episode_id","")==value.episode_id and job["status"] in ("queued","running"):
                return store.public_job(job)
        limits.admission()
        job=store.create(value,prefs)
    pipeline.EXECUTOR.submit(pipeline.process,job["id"])
    return store.public_job(job)

@app.get("/api/jobs/{job_id}")
def job(job_id):return store.public_job(get_job(job_id))

@app.post("/api/jobs/{job_id}/cancel")
def cancel_job(job_id):
    job=get_job(job_id)
    if job["status"] not in ("queued","running"):
        raise HTTPException(409,"这个任务已经结束。")
    pipeline.cancel(job_id)
    return {"cancelled":True}

@app.post("/api/jobs/{job_id}/publish",status_code=202)
def publish_job(job_id):
    job=get_job(job_id)
    if job_id=="sample":raise HTTPException(409,"示例已经有飞书文档，可直接打开。")
    if job.get("feishu_url"):return {"url":job["feishu_url"]}
    if job["status"]!="complete":raise HTTPException(409,"请等待稿件完成后再保存。")
    store.update(job_id,status="queued",stage="publish",message="正在排队保存到飞书")
    pipeline.EXECUTOR.submit(pipeline.publish_existing,job_id)
    return {"queued":True}

@app.get("/api/jobs/{job_id}/preview")
def preview(job_id):
    # Redirect relative image paths to /files/ through a base element.
    from fastapi.responses import HTMLResponse
    path=output_file(job_id,"article.html")
    html=path.read_text().replace("<meta charset=",f'<base href="/api/jobs/{job_id}/files/"><meta charset=',1)
    return HTMLResponse(html,headers={"Content-Security-Policy":"default-src 'none'; img-src 'self'; style-src 'unsafe-inline'; base-uri 'self'; frame-ancestors 'self'"})

@app.get("/api/jobs/{job_id}/files/{filename}")
def file(job_id,filename):return FileResponse(output_file(job_id,filename))

@app.get("/api/jobs/{job_id}/download")
def download(job_id):
    get_job(job_id)
    directory=store.job_dir(job_id)/"output"
    if not (directory/"article.html").exists():raise HTTPException(409,"稿件尚未生成。")
    archive=store.job_dir(job_id)/"article-package.zip"
    with zipfile.ZipFile(archive,"w",zipfile.ZIP_DEFLATED) as bundle:
        for path in directory.iterdir():
            if path.suffix in (".html",".md",".png",".jpg",".svg"):
                bundle.write(path,path.name)
    return FileResponse(archive,filename="公众号图文包.zip",media_type="application/zip")

@app.get("/api/jobs/{job_id}/materials")
def materials(job_id):
    get_job(job_id)
    from .exports import files
    return {"files":[{"name":name,"size":path.stat().st_size,"url":f"/api/jobs/{job_id}/materials/{name}"} for name,path in files(job_id).items()]}

@app.get("/api/jobs/{job_id}/materials-package")
def materials_package(job_id):
    get_job(job_id)
    from .exports import package
    try:path=package(job_id)
    except FileNotFoundError:raise HTTPException(409,"转录与素材尚未生成。")
    return FileResponse(path,filename="视频转录与素材.zip",media_type="application/zip")

@app.get("/api/jobs/{job_id}/materials/{filename}")
def material_file(job_id,filename):
    get_job(job_id)
    from .exports import files
    path=files(job_id).get(filename)
    if path is None:raise HTTPException(404,"素材不存在。")
    return FileResponse(path,filename=filename)

from .admin import router as admin_router
app.include_router(admin_router)

@app.get("/history")
def history_page():
    return FileResponse(store.ROOT/"web"/"history.html")

@app.get("/admin")
def admin_page():
    return FileResponse(store.ROOT/"web"/"admin.html")

app.mount("/assets",StaticFiles(directory=store.ROOT/"assets"),name="assets")
app.mount("/",StaticFiles(directory=store.ROOT/"web",html=True),name="website")
