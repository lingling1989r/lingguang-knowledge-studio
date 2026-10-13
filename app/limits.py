"""Single-process capacity controls, shared by submission and media download."""
import shutil
from fastapi import HTTPException
from pydantic import BaseModel, Field
from . import store

class Limits(BaseModel):
    concurrency: int = Field(default=1,ge=1,le=4)
    queue_limit: int = Field(default=10,ge=0,le=100)
    max_video_minutes: int = Field(default=240,ge=1,le=240)
    max_file_mb: int = Field(default=3072,ge=50,le=3072)
    min_free_disk_gb: int = Field(default=5,ge=1,le=100)
    accepting_jobs: bool = True

def current():
    import json
    path=store.STATE/'limits.json'
    return Limits.model_validate_json(path.read_text()) if path.exists() else Limits()

def capacity():
    jobs=store.all_jobs(); limits=current()
    return {'running':sum(j['status']=='running' for j in jobs),'queued':sum(j['status']=='queued' for j in jobs),'concurrency':limits.concurrency,'free_disk_gb':round(shutil.disk_usage(store.STATE).free/1024**3,1)}

def admission():
    limits=current(); live=sum(j['status'] in ('queued','running') for j in store.all_jobs())
    if not limits.accepting_jobs:raise HTTPException(503,'服务暂时停止接收新任务，请稍后再试。')
    if live>=limits.concurrency+limits.queue_limit:raise HTTPException(429,'处理队列已满，请稍后再提交。')
    if shutil.disk_usage(store.STATE).free<limits.min_free_disk_gb*1024**3:raise HTTPException(503,'服务器剩余存储不足，暂时不能接收新任务。')

def duration(seconds):
    maximum=current().max_video_minutes
    if not seconds or seconds<=0 or seconds>maximum*60:raise RuntimeError(f'当前视频时长上限为{maximum}分钟，请选择范围内的视频。')
