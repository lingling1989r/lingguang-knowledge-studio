"""User-facing machine transcription and media exports; private state stays private."""
import json, zipfile
from pathlib import Path
from . import store


def timestamp(seconds):
    ms=max(0,round(seconds*1000)); hours,ms=divmod(ms,3600000); minutes,ms=divmod(ms,60000); seconds,ms=divmod(ms,1000)
    return f"{hours:02}:{minutes:02}:{seconds:02},{ms:03}"


def save_transcript(job_id, segments, metadata):
    directory=store.job_dir(job_id)/"exports"; directory.mkdir(exist_ok=True)
    source={"title":metadata.get("title",""),"url":store.read(job_id)["url"],"duration":metadata.get("duration"),"type":"机器语音识别，可能存在漏字或误识别，未经人工逐字校对"}
    clean=[{"start":s["start"],"end":s["end"],"text":s["text"]} for s in segments]
    (directory/"transcript.txt").write_text(source["type"]+"\n来源："+source["url"]+"\n\n"+"\n".join(s["text"] for s in clean))
    (directory/"transcript.srt").write_text("\n\n".join(f"{i}\n{timestamp(s['start'])} --> {timestamp(s['end'])}\n{s['text']}" for i,s in enumerate(clean,1))+"\n")
    store.atomic_json(directory/"transcript.json",{**source,"segments":clean})
    store.update(job_id,transcript_available=True)


def files(job_id):
    root=store.job_dir(job_id)
    result={}
    for name in ("transcript.txt","transcript.srt","transcript.json"):
        path=root/"exports"/name
        if path.is_file():result[name]=path
    for name in ("source.mp4","source.mkv","source.webm","source.m4a","audio.wav"):
        path=root/"raw"/name
        if path.is_file():result[name]=path
    for path in (root/"output").glob("*"):
        if path.suffix in (".jpg",".png",".svg") and path.is_file():result[path.name]=path
    return result


def package(job_id):
    available=files(job_id)
    if not available:raise FileNotFoundError()
    archive=store.job_dir(job_id)/"source-package.zip"
    # Serialize writes to the same package; no private JSON or chunk scratch files.
    with store.LOCK:
        with zipfile.ZipFile(archive,"w",zipfile.ZIP_STORED) as bundle:
            for name,path in available.items():bundle.write(path,name)
            bundle.writestr("说明.txt","机器转录未经逐字校对。视频是服务已下载的版本，非上传者的原始母版；音频如已提取则一并提供。仅包含已成功生成的素材。\n")
    return archive
