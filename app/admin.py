"""Local administrator authentication and platform connection management."""
import hashlib, hmac, secrets, time
from urllib.parse import urlparse
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field
from . import store, agent, pipeline, limits

router = APIRouter(prefix="/api/admin")
SESSIONS = {}
ATTEMPTS = {}
COOKIE = "studio_admin"

class Password(BaseModel):
    password: str = Field(min_length=12, max_length=200)

class Connection(BaseModel):
    mode: str = "codex"
    agent_url: str = ""
    agent_token: str = Field(default="", max_length=1000)
    api_base: str = "https://api.openai.com/v1"
    model: str = "gpt-6.1-sol"
    api_key: str = Field(default="", max_length=1000)

def require(request):
    token = request.cookies.get(COOKIE, "")
    if SESSIONS.get(token, 0) < time.time():
        SESSIONS.pop(token, None)
        raise HTTPException(401, "请先登录管理后台。")

def login_cookie(response):
    token = secrets.token_urlsafe(32)
    SESSIONS[token] = time.time() + 8*3600
    response.set_cookie(COOKIE, token, httponly=True, samesite="strict", max_age=8*3600, path="/api/admin")

def save_password(password):
    salt = secrets.token_hex(16)
    digest = hashlib.scrypt(password.encode(), salt=salt.encode(), n=16384, r=8, p=1).hex()
    store.atomic_json(store.STATE / "admin-auth.json", {"salt": salt, "digest": digest})

def secure_url(value):
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise HTTPException(422, "连接地址须为不含账号、查询参数的 HTTPS 地址。")
    return value.rstrip("/")

@router.get("/session")
def session(request: Request):
    return {"initialized": (store.STATE/"admin-auth.json").exists(), "logged_in": SESSIONS.get(request.cookies.get(COOKIE,""),0)>time.time()}

@router.post("/setup")
def setup(value: Password, response: Response):
    with store.LOCK:
        if (store.STATE/"admin-auth.json").exists(): raise HTTPException(409,"管理员已创建，请登录。")
        save_password(value.password)
    login_cookie(response)
    return {"saved": True}

@router.post("/login")
def login(value: Password, request: Request, response: Response):
    client = request.client.host if request.client else "local"
    recent = [t for t in ATTEMPTS.get(client,[]) if t>time.time()-300]
    ATTEMPTS[client] = recent
    if len(recent)>=5: raise HTTPException(429,"登录尝试过多，请五分钟后重试。")
    path = store.STATE/"admin-auth.json"
    if not path.exists(): raise HTTPException(409,"请先创建管理员。")
    import json
    config=json.loads(path.read_text())
    digest=hashlib.scrypt(value.password.encode(),salt=config["salt"].encode(),n=16384,r=8,p=1).hex()
    if not hmac.compare_digest(digest, config["digest"]):
        recent.append(time.time())
        raise HTTPException(401,"管理员密码不正确。")
    ATTEMPTS.pop(client,None)
    login_cookie(response)
    return {"logged_in":True}

@router.post("/logout")
def logout(request: Request, response: Response):
    SESSIONS.pop(request.cookies.get(COOKIE,""),None)
    response.delete_cookie(COOKIE,path="/api/admin")
    return {"logged_out":True}

@router.post("/password")
def password(value: Password, request: Request):
    require(request)
    save_password(value.password)
    SESSIONS.clear()
    return {"saved":True}

@router.get("/overview")
def overview(request: Request):
    require(request)
    a=store.agent_config(); g=store.ai_config()
    return {"mode":agent.mode(), "agent_url":a.get("url",""), "agent_token_set":bool(a.get("token")), "api_base":g.get("api_base",""), "model":g.get("model","gpt-6.1-sol"), "api_key_set":bool(g.get("api_key")), "ready":agent.ready(), "issue":store.ai_issue() if agent.mode()=="gpt" else "", "health":store.connection_health(), "feishu_app_id":store.feishu_config().get("app_id",""),"feishu_folder":store.preferences().get("folder",""), "limits":limits.current().model_dump(),"capacity":limits.capacity(), "jobs":[store.public_job(j) for j in store.all_jobs()]}

@router.post("/connection")
def connection(value: Connection, request: Request):
    require(request)
    if value.mode not in ("agent","gpt","codex"):raise HTTPException(422,"请选择 Codex CLI、Agent 或默认 GPT。")
    if any(j["status"] in ("queued","running") for j in store.all_jobs()):raise HTTPException(409,"请等待运行中的任务结束后再更新连接。")
    a=store.agent_config(); g=store.ai_config()
    if value.mode=="codex":
        store.atomic_json(store.STATE/"agent.json",{"mode":"codex","url":a.get("url",""),"token":a.get("token","")})
    elif value.mode=="agent":
        url=secure_url(value.agent_url); token=value.agent_token or a.get("token","")
        if not token:raise HTTPException(422,"请填写 Agent Token。")
        store.atomic_json(store.STATE/"agent.json",{"mode":"agent","url":url,"token":token})
    else:
        base=secure_url(value.api_base); key=value.api_key or g.get("api_key","")
        if not key or not value.model.strip():raise HTTPException(422,"请填写默认模型和 API Key。")
        store.atomic_json(store.STATE/"ai.json",{"api_base":base,"model":value.model.strip(),"api_key":key})
        store.atomic_json(store.STATE/"agent.json",{"mode":"gpt","url":a.get("url",""),"token":a.get("token","")})
    (store.STATE/"ai-health.json").unlink(missing_ok=True)
    (store.STATE/"connection-health.json").unlink(missing_ok=True)
    return {"saved":True,"message":"已保存，尚未验证；请测试连接。"}

@router.post("/test")
def test(request: Request):
    require(request)
    try:
        result=agent.complete("admin-connection-test",{"model":agent.default_model(),"messages":[{"role":"user","content":"连接测试：只返回 JSON 对象 {\"ok\":true}，不要其他文字。"}],"response_format":{"type":"json_object"},"max_tokens":32},{"type":"object","properties":{"ok":{"const":True}},"required":["ok"]})
        import json
        if json.loads(result).get("ok") is not True:raise ValueError("unexpected response")
        health={"ok":True,"message":"连接测试通过，后台可以调用写稿服务。","tested_at":time.time()}
        (store.STATE/"ai-health.json").unlink(missing_ok=True)
    except Exception:
        health={"ok":False,"message":"连接测试失败，请检查 Codex CLI 登录或所选连接的凭据与响应格式。","tested_at":time.time()}
    store.atomic_json(store.STATE/"connection-health.json",health)
    return health

@router.post("/jobs/{job_id}/retry")
def retry(job_id: str, request: Request):
    require(request)
    try:old=store.read(job_id)
    except KeyError:raise HTTPException(404,"任务不存在。")
    if old["status"] not in ("failed","cancelled"):raise HTTPException(409,"只可重试失败或取消的任务。")
    if not agent.ready():raise HTTPException(503,"请先修复并测试后台连接。")
    from .schemas import JobRequest
    with store.LOCK:
        if any(j["url"]==old["url"] and j.get("options",{}).get("episode_id","")==old["options"].get("episode_id","") and j["status"] in ("queued","running") for j in store.all_jobs()):raise HTTPException(409,"相同视频已有任务正在处理。")
        limits.admission()
        job=store.create(JobRequest(url=old["url"],**old["options"]),old["preferences"])
    pipeline.EXECUTOR.submit(pipeline.process,job["id"])
    return store.public_job(job)


@router.post("/limits")
def save_limits(value: limits.Limits, request: Request):
    require(request)
    with store.LOCK:
        old=limits.current()
        if value.concurrency!=old.concurrency:
            if any(j['status'] in ('queued','running') for j in store.all_jobs()):raise HTTPException(409,'并发数请在任务全部结束后修改。')
            from concurrent.futures import ThreadPoolExecutor
            previous=pipeline.EXECUTOR
            pipeline.EXECUTOR=ThreadPoolExecutor(max_workers=value.concurrency,thread_name_prefix='video-studio')
            previous.shutdown(wait=False)
        store.atomic_json(store.STATE/'limits.json',value.model_dump())
    return {'saved':True}


@router.post("/feishu-test")
def feishu_test(request: Request):
    require(request)
    from .publishing import publish
    from pathlib import Path
    from uuid import uuid4
    from PIL import Image
    directory=store.STATE/'feishu-tests'/uuid4().hex
    directory.mkdir(parents=True)
    Image.new('RGB',(320,100),'#e7eee1').save(directory/'test.png')
    entries=[{'kind':'text','text':'灵光成稿飞书配置测试：正文与图片上传核验。'},{'kind':'image','file':'test.png'},{'kind':'link','text':'点击观看原视频','url':'https://www.bilibili.com/'}]
    try:
        url=publish(directory,'灵光成稿 · 飞书配置测试',entries,store.preferences().get('folder',''))
        return {'ok':True,'url':url,'message':'创建、正文、图片上传与读回核验通过。请打开文档确认你的账号有权限；此测试不代表其他用户也能访问。'}
    except Exception as exc:
        message=str(exc) if isinstance(exc,RuntimeError) else '飞书请求失败，请检查连接或应用权限。'
        return {'ok':False,'message':message}


class FeishuSettings(BaseModel):
    app_id: str = Field(min_length=1,max_length=100)
    app_secret: str = Field(default='',max_length=300)
    folder: str = Field(default='',max_length=300)

@router.post('/feishu')
def feishu_save(value: FeishuSettings, request: Request):
    require(request)
    from .publishing import Feishu
    old=store.feishu_config()
    if value.app_id!=old.get('app_id') and not value.app_secret:raise HTTPException(422,'更换 App ID 时请同时提供 App Secret。')
    config={'app_id':value.app_id,'app_secret':value.app_secret or old.get('app_secret','')}
    try:Feishu(config)
    except Exception:raise HTTPException(422,'飞书凭据验证失败，请检查 App ID 和 App Secret。')
    store.atomic_json(store.STATE/'feishu.json',config)
    prefs=store.preferences(); prefs['folder']=value.folder;store.save_preferences(prefs)
    return {'saved':True,'message':'凭据已保存，请继续测试文档与图片权限。'}
