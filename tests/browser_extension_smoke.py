"""Real MV3 extension + native host + local worker + mock model, disposable profile."""
import json
import os
from pathlib import Path
import signal
import sys
import socket
import tempfile
import threading
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from playwright.sync_api import sync_playwright
from integrations.browser import install
from integrations.browser.native import HOST_NAME


def main():
    root=Path(__file__).resolve().parents[1]
    extension=root/'integrations/browser/extension'
    executable=Path(os.environ.get('CHROMIUM_EXECUTABLE',str(Path.home()/'Library/Caches/ms-playwright/chromium-1248/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing')))
    class Model(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_POST(self):
            self.rfile.read(int(self.headers['Content-Length']))
            body=json.dumps({'choices':[{'message':{'content':'{"ok":true}'}}]}).encode()
            self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
    model=ThreadingHTTPServer(('127.0.0.1',0),Model)
    threading.Thread(target=model.serve_forever,daemon=True).start()
    registry=Path.home()/'Library/Application Support/Google/ChromeForTesting/NativeMessagingHosts'/f'{HOST_NAME}.json'
    backup=registry.read_bytes() if registry.exists() else None
    original_data=install.DATA
    with tempfile.TemporaryDirectory() as directory:
        temp=Path(directory);data=temp/'bridge';install.DATA=data
        profile=temp/'profile'
        target=install.install(directory=profile/'NativeMessagingHosts',python_executable=sys._base_executable)
        registry.parent.mkdir(parents=True,exist_ok=True);registry.write_bytes(target.read_bytes())
        config=json.loads((data/'bridge.json').read_text())
        with socket.socket() as sock:sock.bind(('127.0.0.1',0));config['port']=sock.getsockname()[1]
        (data/'bridge.json').write_text(json.dumps(config))
        env={**os.environ,'LINGGUANG_BROWSER_DATA':str(data)}
        try:
            with sync_playwright() as playwright:
                context=playwright.chromium.launch_persistent_context(str(profile),executable_path=str(executable),headless=False,
                    args=[f'--disable-extensions-except={extension}',f'--load-extension={extension}'],env=env)
                try:
                    worker=context.service_workers[0] if context.service_workers else context.wait_for_event('serviceworker')
                    page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                    page.goto(worker.url.rsplit('/',1)[0]+'/popup.html')
                    try:
                        page.get_by_text('还没有记录，先转录一个视频。').wait_for(timeout=15000)
                    except Exception:
                        print('POPUP:',page.locator('body').inner_text())
                        log=data/'native.log'
                        print('HOST LOG:',log.read_text()[-4000:] if log.exists() else 'missing')
                        print('NATIVE:',worker.evaluate("() => new Promise(resolve => chrome.runtime.sendNativeMessage('com.lingguang.video',{id:991,operation:'status'},r=>resolve({reply:r,error:chrome.runtime.lastError?.message})))"))
                        raise
                    page.locator('#url').fill('https://www.bilibili.com/video/BV1vXJkz1E8U/')
                    page.locator('summary').click()
                    page.locator('[name=api_base]').fill(f'http://127.0.0.1:{model.server_port}/v1')
                    page.locator('[name=model]').fill('mock-model')
                    page.locator('[name=api_key]').fill('test-only-key')
                    page.get_by_role('button',name='保存到本机',exact=True).click()
                    page.locator('#notice').filter(has_text='已保存到本机').wait_for()
                    assert page.locator('[name=api_key]').input_value()==''
                    page.get_by_role('button',name='测试模型连接').click()
                    page.locator('#notice').filter(has_text='模型连接测试通过').wait_for(timeout=30000)
                    page.locator('summary').click()
                    page.locator('body').screenshot(path=str(Path.home()/'Desktop/B站转录插件_界面预览.png'))
                    assert not errors,errors
                    page.get_by_role('button',name='停止空闲本机组件').click()
                    page.locator('#notice').filter(has_text='本机组件已停止').wait_for()
                    print('PASS: real extension -> registered native host -> worker -> local mock model; no page errors',flush=True)
                except Exception as exc:
                    print('UI ERROR:',repr(exc),flush=True)
                    raise
                finally:
                    # The test owns this browser profile, so clean up only its process.
                    import subprocess
                    matches=subprocess.run(['pgrep','-f',str(profile)],capture_output=True,text=True)
                    for item in matches.stdout.split():
                        try:os.kill(int(item),signal.SIGTERM)
                        except ProcessLookupError:pass
                    try:context.close()
                    except Exception:pass
        finally:
            pid=data/'worker.pid'
            if pid.exists():
                try:os.killpg(int(pid.read_text()),signal.SIGTERM)
                except ProcessLookupError:pass
            if backup is None:registry.unlink(missing_ok=True)
            else:registry.write_bytes(backup)
            install.DATA=original_data
            model.shutdown();model.server_close()

if __name__=='__main__':main()
