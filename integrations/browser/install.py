"""Register a native messaging host for this extension, without admin privileges."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import sys
from .native import DATA, ROOT, HOST_NAME


def extension_id():
    manifest=json.loads((ROOT/'integrations/browser/extension/manifest.json').read_text())
    public=base64.b64decode(manifest['key'])
    return ''.join(chr(97+int(c,16)) for c in hashlib.sha256(public).hexdigest()[:32])


def stage_runtime():
    runtime=DATA/'runtime'
    if ROOT.resolve()==runtime.resolve():return runtime
    for name in ['__init__.py','store.py','pipeline.py','exports.py','limits.py','agent.py','schemas.py','publishing.py','rendering.py','logging.py','admin.py','sources.py','bilibili.py','openclacky.py']:
        target=runtime/'app'/name;target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(ROOT/'app'/name,target)
    target=runtime/'integrations/browser';target.mkdir(parents=True,exist_ok=True)
    (runtime/'integrations/__init__.py').write_text('')
    for path in (ROOT/'integrations/browser').glob('*.py'):
        shutil.copy2(path,target/path.name)
    shutil.copytree(ROOT/'assets',runtime/'assets',dirs_exist_ok=True)
    runner=ROOT/'desktop/openclacky_runner.rb'
    if runner.exists():
        (runtime/'desktop').mkdir(exist_ok=True);shutil.copy2(runner,runtime/'desktop/openclacky_runner.rb')
    vendor=ROOT/'.desktop-vendor/openclacky'
    if vendor.is_dir():shutil.copytree(vendor,runtime/'.desktop-vendor/openclacky',dirs_exist_ok=True)
    return runtime


def install(browser='chrome',directory=None,python_executable=None):
    if sys.platform=='win32':raise RuntimeError('当前安装器仅在macOS/Linux提供；Windows原生宿主安装尚未实现。')
    DATA.mkdir(parents=True,exist_ok=True);os.chmod(DATA,0o700)
    runtime=stage_runtime()
    launcher=DATA/'native-host.sh'
    launcher.write_text('#!/bin/sh\nexport LINGGUANG_BROWSER_DATA='+shlex.quote(str(DATA))+'\nexport PYTHONPATH='+shlex.quote(str(runtime))+'\nexec 2>> '+shlex.quote(str(DATA/'native.log'))+'\ncd '+shlex.quote(str(runtime))+' || exit 1\nexec '+shlex.quote(str(python_executable or sys.executable))+' '+shlex.quote(str(runtime/'integrations/browser/native.py'))+' "$@"\n')
    launcher.chmod(0o700)
    origin='chrome-extension://'+extension_id()+'/'
    config=DATA/'bridge.json'
    previous=json.loads(config.read_text()) if config.exists() else {}
    previous.update(port=previous.get('port',18766),allowed_origins=[origin])
    config.write_text(json.dumps(previous,indent=2));config.chmod(0o600)
    if directory is None:
        if sys.platform=='darwin':
            names={'chrome':'Google/Chrome','chromium':'Chromium','chrome-testing':'Google/ChromeForTesting','edge':'Microsoft Edge'}
            directory=Path.home()/'Library/Application Support'/names[browser]/'NativeMessagingHosts'
        else:
            names={'chrome':'google-chrome','chromium':'chromium','chrome-testing':'google-chrome-for-testing','edge':'microsoft-edge'}
            directory=Path.home()/'.config'/names[browser]/'NativeMessagingHosts'
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    target=directory/(HOST_NAME+'.json')
    target.write_text(json.dumps({'name':HOST_NAME,'description':'Lingguang local Bilibili collector','path':str(launcher),'type':'stdio','allowed_origins':[origin]},indent=2))
    print('注册完成：',target,'\n扩展ID：',extension_id(),'\n数据目录：',DATA)
    return target


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--browser',choices=['chrome','edge','chromium','chrome-testing'],default='chrome')
    parser.add_argument('--model-path',type=Path)
    args=parser.parse_args()
    install(args.browser)
    if args.model_path:
        model=args.model_path.expanduser().resolve()
        if not (model/'weights.npz').is_file():raise SystemExit('模型目录缺少weights.npz')
        path=DATA/'bridge.json';config=json.loads(path.read_text());config['model_path']=str(model);path.write_text(json.dumps(config,indent=2));path.chmod(0o600)

if __name__=='__main__':main()
