"""Transcribe an already downloaded audio file, using the same local engine as the extension."""
import argparse
import json
import subprocess
from pathlib import Path
from .transcription import recognize, write_readable
from app.exports import timestamp


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--audio',type=Path,required=True)
    parser.add_argument('--metadata',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    metadata=json.loads(args.metadata.read_text())
    duration=float(subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration','-of','default=noprint_wrappers=1:nokey=1',str(args.audio)],text=True).strip())
    segments=recognize(args.audio,duration,args.output/'识别检查点',lambda done,total:print(f'已转录 {done}/{total} 段（每段最多2分钟）',flush=True))
    source={'title':metadata['title'],'uploader':metadata.get('uploader'),'url':metadata.get('webpage_url'),'duration':duration,'type':'完整机器语音转录，未经逐字人工校对','segments':segments}
    args.output.mkdir(parents=True,exist_ok=True)
    (args.output/'transcript.json').write_text(json.dumps(source,ensure_ascii=False,indent=2))
    (args.output/'transcript.txt').write_text(source['title']+'\n来源：'+source['url']+'\n'+source['type']+'\n\n'+'\n'.join(s['text'] for s in segments)+'\n')
    (args.output/'transcript.srt').write_text('\n\n'.join(f'{i}\n{timestamp(s["start"])} --> {timestamp(s["end"])}\n{s["text"]}' for i,s in enumerate(segments,1))+'\n')
    write_readable(args.output,source['title'],source['url'],segments)
    (args.output/'带时间戳转录.md').write_bytes((args.output/'article.md').read_bytes())
    print(json.dumps({'segments':len(segments),'characters':sum(len(s['text']) for s in segments),'duration':duration,'last_segment_end':segments[-1]['end']},ensure_ascii=False),flush=True)

if __name__=='__main__':main()
