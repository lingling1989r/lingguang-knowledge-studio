"""Native messaging protocol -> real loopback worker, entirely in disposable state."""
import io
import json
import os
from pathlib import Path
import signal
import struct
import subprocess
import sys
import tempfile
from integrations.browser.install import extension_id


def main():
    with tempfile.TemporaryDirectory() as directory:
        root=Path(directory);data=root/'bridge';data.mkdir()
        import socket
        with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        origin='chrome-extension://'+extension_id()+'/'
        (data/'bridge.json').write_text(json.dumps({'port':port,'allowed_origins':[origin]}))
        env=os.environ.copy();env.update(LINGGUANG_BROWSER_DATA=str(data),HOME=str(root))
        processes=[]
        try:
            def call(value):
                body=json.dumps(value).encode()
                process=subprocess.Popen([sys.executable,'-m','integrations.browser.native',origin],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env)
                processes.append(process)
                result,error=process.communicate(struct.pack('=I',len(body))+body,timeout=30)
                assert process.returncode==0,error.decode()
                size=struct.unpack('=I',result[:4])[0]
                return json.loads(result[4:4+size])
            status=call({'id':1,'operation':'status'})
            assert status['result']['ready'] is True,status
            assert 'request_token' not in status['result']
            assert call({'id':2,'operation':'jobs'})['result']==[]
            rejected=call({'id':3,'operation':'create','url':'http://127.0.0.1/private'})
            assert rejected.get('error'),rejected
            print('PASS: native frames, origin pairing, real worker startup, private token, history and URL rejection')
        finally:
            for process in processes:
                if process.poll() is None:process.terminate();process.wait(timeout=10)
            pid=data/'worker.pid'
            if pid.exists():
                try:os.killpg(int(pid.read_text()),signal.SIGTERM)
                except ProcessLookupError:pass

if __name__=='__main__':main()
