"""Download public model weights, verify SHA-256, and install outside protected folders."""
import hashlib
import json
from pathlib import Path
import urllib.request
from .native import DATA

SHA256='862bbc832b05f3f4ec19dd632b701d61a6d3f5c7906360a10d72a79870642a80'
CONFIG={'n_mels':128,'n_audio_ctx':1500,'n_audio_state':1280,'n_audio_head':20,'n_audio_layer':32,'n_vocab':51866,'n_text_ctx':448,'n_text_state':1280,'n_text_head':20,'n_text_layer':4,'quantization':{'group_size':64,'bits':4},'model_type':'whisper'}
REPO='mlx-community/whisper-large-v3-turbo-q4'
REVISION='660c343bbf4e52ac257f0b7d952e5388e6f93bef'


def valid(path):
    if not path.is_file():return False
    digest=hashlib.sha256()
    with path.open('rb') as stream:
        while chunk:=stream.read(1024*1024):digest.update(chunk)
    return digest.hexdigest()==SHA256


def main():
    target=DATA/'models/whisper-large-v3-turbo-q4';target.mkdir(parents=True,exist_ok=True)
    weights=target/'weights.npz'
    if not valid(weights):
        temporary=target/'weights.download'
        urls=[f'https://huggingface.co/{REPO}/resolve/{REVISION}/weights.npz',f'https://hf-mirror.com/{REPO}/resolve/main/weights.npz']
        for url in urls:
            try:
                print('准备下载语音模型，约443MiB：',url,flush=True)
                request=urllib.request.Request(url,headers={'User-Agent':'LingguangBrowser/0.1'})
                with urllib.request.urlopen(request,timeout=30) as response,temporary.open('wb') as output:
                    size=0;next_notice=16*1024**2
                    while chunk:=response.read(1024*1024):
                        output.write(chunk);size+=len(chunk)
                        if size>=next_notice:
                            print(f'已下载 {size//1024**2} MiB',flush=True);next_notice+=16*1024**2
                if not valid(temporary):raise RuntimeError('模型校验失败')
                temporary.replace(weights);break
            except Exception as exc:
                temporary.unlink(missing_ok=True)
                print('此下载源暂不可用：',type(exc).__name__,flush=True)
        else:raise SystemExit('模型未下载完成，请检查网络后重新运行安装脚本。')
    (target/'config.json').write_text(json.dumps(CONFIG,indent=2))
    config=DATA/'bridge.json'
    values=json.loads(config.read_text()) if config.exists() else {}
    values['model_path']=str(target)
    config.write_text(json.dumps(values,indent=2));config.chmod(0o600)
    print('语音模型已校验并准备好：',target,flush=True)

if __name__=='__main__':main()
