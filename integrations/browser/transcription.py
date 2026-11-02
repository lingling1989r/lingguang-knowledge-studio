"""Local-only transcription path, preserving ASR segments rather than summarizing."""
import html
import json
import math
import os
from pathlib import Path
import platform
import subprocess
from app import store, pipeline, limits
from app.exports import save_transcript


def model_path():
    configured = os.getenv('WHISPER_MODEL_PATH')
    candidates = [Path(configured).expanduser()] if configured else []
    # Desktop and browser entries share the user's external model installation.
    # Only a local directory is recorded; weights are never copied into the app.
    registry = store.STATE / 'workbench' / 'media.json'
    if registry.is_file():
        try:
            saved = json.loads(registry.read_text()).get('model_path')
            if isinstance(saved,str): candidates.append(Path(saved).expanduser())
        except (ValueError,OSError): pass
    candidates += [store.STATE / 'models/whisper-large-v3-turbo-q4']
    candidates += [store.ROOT / '.models/whisper-large-v3-turbo-q4']
    candidates += list((Path.home()/'.cache/huggingface/hub').glob('models--mlx-community--whisper-large-v3-turbo-q4/snapshots/*'))
    return next((p for p in candidates if (p/'weights.npz').is_file()), None)


def recognize(audio, duration, output_dir, progress=lambda *a: None, cancelled=lambda: None):
    """Checkpoint every two minutes so completed recognition survives interruption."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    if platform.system() == 'Darwin':
        import mlx_whisper
        model = model_path()
        if not model:
            raise RuntimeError('请先准备本地语音模型，或在桥接配置中填写模型目录。')
        def run(path):
            return mlx_whisper.transcribe(str(path), path_or_hf_repo=str(model), language='zh', verbose=False,
                temperature=0.0, condition_on_previous_text=False)['segments']
    else:
        from faster_whisper import WhisperModel
        model = WhisperModel(os.getenv('WHISPER_MODEL_PATH', 'small'), device='cpu', compute_type='int8', local_files_only=True)
        def run(path):
            segments, _ = model.transcribe(str(path), language='zh', vad_filter=True, condition_on_previous_text=False)
            return [dict(start=s.start,end=s.end,text=s.text) for s in segments]
    segments = []
    count = math.ceil(duration/120)
    for index in range(count):
        cancelled()
        checkpoint = output_dir / f'chunk-{index:04d}.json'
        if checkpoint.exists():
            chunk = json.loads(checkpoint.read_text())
        else:
            part = output_dir / 'part.wav'
            subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-ss',str(index*120),'-i',str(audio),'-t','120','-ar','16000','-ac','1','-y',str(part)],check=True,capture_output=True,timeout=180)
            chunk = []
            for s in run(part):
                text = s['text'].strip()
                if text:
                    chunk.append({'start':round(s['start']+index*120,2),'end':round(min(s['end']+index*120,duration),2),'text':text})
            checkpoint.write_text(json.dumps(chunk,ensure_ascii=False))
            part.unlink(missing_ok=True)
        segments += chunk
        progress(index+1,count)
    if not segments:
        raise RuntimeError('没有识别到语音，不能生成转录文本。')
    return segments


def write_readable(directory, title, url, segments):
    directory = Path(directory)
    directory.mkdir(parents=True,exist_ok=True)
    def clock(s):
        s=int(s); return f'{s//3600:02}:{s//60%60:02}:{s%60:02}'
    body = '\n\n'.join(f'[{clock(s["start"])}] {s["text"]}' for s in segments)
    text = f'# {title}\n\n来源：{url}\n\n> 完整机器转录，未经逐字人工校对；保留ASR识别结果，不是摘要。\n\n'+body+'\n'
    (directory/'article.md').write_text(text)
    (directory/'article.html').write_text('<!doctype html><meta charset="utf-8"><title>完整机器转录</title><style>body{max-width:860px;margin:40px auto;padding:20px;line-height:1.9;font-family:system-ui}pre{white-space:pre-wrap}</style><pre>'+html.escape(text)+'</pre>')


def process(job_id):
    try:
        job = pipeline.progress(job_id,'download',3,'正在读取视频音频')
        raw = store.job_dir(job_id)/'raw'
        raw.mkdir(exist_ok=True)
        import yt_dlp
        def hook(data): pipeline.check_cancel(job_id)
        with yt_dlp.YoutubeDL({'quiet':True,'no_warnings':True,'noplaylist':True,'format':'worstaudio/best',
            'outtmpl':str(raw/'source.%(ext)s'),'progress_hooks':[hook],'retries':2,'socket_timeout':30,
            'max_filesize':limits.current().max_file_mb*1024**2}) as downloader:
            info=downloader.extract_info(job['url'],download=False)
            limits.duration(info.get('duration'))
            pipeline.progress(job_id,'download',10,'正在下载音频',title=info.get('title',''))
            downloader.process_info(info)
        audio=next((p for p in raw.glob('source.*') if p.suffix in ('.m4a','.mp4','.webm','.mp3','.mkv')),None)
        if not audio: raise RuntimeError('未获取到可用音频。')
        parts=store.job_dir(job_id)/'recognition'
        def update(done,total):
            pipeline.progress(job_id,'transcribe',20+int(75*done/total),f'正在转录（{done}/{total}）')
        segments=recognize(audio,info['duration'],parts,update,lambda:pipeline.check_cancel(job_id))
        save_transcript(job_id,segments,info)
        write_readable(store.job_dir(job_id)/'output',info.get('title',job['bvid']),job['url'],segments)
        pipeline.check_cancel(job_id)
        store.update(job_id,status='complete',stage='transcribe',progress=100,message='完整机器转录已完成',duration=info['duration'],image_count=0,error=None)
    except pipeline.Cancelled:
        pass
    except Exception as exc:
        store.update(job_id,status='failed',message='转录未完成，已完成内容仍保留',error=pipeline.friendly(exc))
