import json, os, re, threading
from pathlib import Path
from datetime import datetime, timezone
from uuid import uuid4

ROOT = Path(__file__).resolve().parent.parent
STATE = Path(os.getenv("STUDIO_STATE_DIR") or ROOT / ".state")
STATE.mkdir(parents=True, exist_ok=True)
LOCK = threading.RLock()

def atomic_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    os.chmod(temporary, 0o600)
    temporary.replace(path)

def job_dir(job_id):
    if not re.fullmatch(r"[a-f0-9]{32}|sample", job_id):
        raise KeyError(job_id)
    return STATE / "jobs" / job_id

def read(job_id):
    with LOCK:
        path = job_dir(job_id) / "job.json"
        if not path.exists():
            raise KeyError(job_id)
        return json.loads(path.read_text())

def update(job_id, **changes):
    with LOCK:
        data = read(job_id)
        data.update(changes)
        atomic_json(job_dir(job_id) / "job.json", data)
        return data

def create(request, preferences):
    with LOCK:
        jid = uuid4().hex
        if request.source_type=='rss':
            import hashlib
            bvid='rss-'+hashlib.sha256((request.url+request.episode_id).encode()).hexdigest()[:24]
        elif 'youtube.com/watch?' in request.url:
            from .sources import youtube
            bvid='yt-'+youtube(request.url)[0]
        else:bvid=request.url.split('/video/')[1].strip('/')
        data = {"id": jid, "bvid": bvid, "url": request.url, "title": "", "created_at": datetime.now(timezone.utc).isoformat(), "status": "queued", "stage": "download", "progress": 0, "message": "已排队，稍后开始", "options": request.model_dump(exclude={"url"}), "preferences": preferences, "feishu_url": None, "error": None}
        atomic_json(job_dir(jid) / "job.json", data)
        return data

def all_jobs():
    with LOCK:
        paths = (STATE / "jobs").glob("*/job.json")
        return sorted([json.loads(p.read_text()) for p in paths], key=lambda j: j["created_at"], reverse=True)

def preferences():
    path = STATE / "preferences.json"
    defaults = {"author": "作者", "wechat": "your-wechat", "folder": ""}
    if path.exists():
        defaults.update(json.loads(path.read_text()))
    return defaults

def save_preferences(data):
    atomic_json(STATE / "preferences.json", data)

def feishu_config():
    for path in (STATE / "feishu.json", Path(os.getenv("FEISHU_CONFIG") or STATE / "not-configured")):
        if path.is_file():
            data = json.loads(path.read_text())
            if data.get("app_id") and data.get("app_secret"):
                return data
    return {"app_id": os.getenv("FEISHU_APP_ID", ""), "app_secret": os.getenv("FEISHU_APP_SECRET", "")}

def public_job(job):
    return {k: v for k, v in job.items() if k not in ("preferences", "options")}


def ai_config():
    path = STATE / "ai.json"
    if path.exists():
        return json.loads(path.read_text())
    return {"api_key":os.getenv("OPENAI_API_KEY",""),"api_base":os.getenv("OPENAI_BASE_URL","https://api.openai.com/v1"),"model":os.getenv("AI_MODEL","gpt-6.1-sol")}


def ai_issue():
    path=STATE / "ai-health.json"
    return json.loads(path.read_text()).get("issue", "") if path.exists() else ""


def agent_config():
    path=STATE/"agent.json"
    if path.exists():return json.loads(path.read_text())
    return {"mode":"agent" if os.getenv("STUDIO_AGENT_URL") else ("openclacky" if os.getenv("STUDIO_DESKTOP") else "codex"), "url":os.getenv("STUDIO_AGENT_URL",""),"token":os.getenv("STUDIO_AGENT_TOKEN","")}


def connection_health():
    path=STATE/"connection-health.json"
    return json.loads(path.read_text()) if path.exists() else {"ok":None,"message":"尚未测试连接"}
