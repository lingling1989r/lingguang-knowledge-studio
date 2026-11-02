"""Build a reviewable extension + local component bundle without personal state."""
import json
import subprocess
import zipfile
from pathlib import Path
from .native import ROOT

CORE=['__init__.py','store.py','pipeline.py','exports.py','limits.py','agent.py','schemas.py','publishing.py','rendering.py','logging.py','admin.py','sources.py','bilibili.py','openclacky.py']


def main():
    destination=Path.home()/'Desktop/灵光-B站浏览器插件-0.1内测版.zip'
    with zipfile.ZipFile(destination,'w',zipfile.ZIP_DEFLATED) as bundle:
        def add(path,name):
            bundle.write(path,name)
        bundle.writestr('安装说明.md',(ROOT/'integrations/browser/README.md').read_text())
        for path in (ROOT/'integrations/browser/extension').iterdir():
            if path.suffix in ('.js','.html','.css','.json') and path.name!='package.json':add(path,'浏览器插件/'+path.name)
        # Use committed core files. Other workbench changes in this workspace are not part of this package.
        for name in CORE:
            contents=subprocess.check_output(['git','show','HEAD:app/'+name],cwd=ROOT)
            bundle.writestr('本机组件/app/'+name,contents)
        bundle.writestr('本机组件/integrations/__init__.py','')
        for path in (ROOT/'integrations/browser').iterdir():
            if path.suffix in ('.py','.md','.txt','.command'):add(path,'本机组件/integrations/browser/'+path.name)
        for path in (ROOT/'assets').rglob('*'):
            if path.is_file():add(path,'本机组件/assets/'+str(path.relative_to(ROOT/'assets')))
        vendor=ROOT/'.desktop-vendor/openclacky'
        if vendor.is_dir():
            for path in vendor.rglob('*'):
                if path.is_file() and '__pycache__' not in path.parts:add(path,'本机组件/.desktop-vendor/openclacky/'+str(path.relative_to(vendor)))
        bundle.writestr('本机组件/desktop/__init__.py','')
        add(ROOT/'desktop/openclacky_runner.rb','本机组件/desktop/openclacky_runner.rb')
        for name in ['LICENSE','THIRD_PARTY_NOTICES.md']:add(ROOT/name,'本机组件/'+name)
    with zipfile.ZipFile(destination) as bundle:
        assert bundle.testzip() is None
        assert not any('/.state/' in name or '/state/' in name or name.endswith(('/ai.json','/feishu.json','/bridge.json')) for name in bundle.namelist())
    print(destination,round(destination.stat().st_size/1024**2,1),'MiB')

if __name__=='__main__':main()
