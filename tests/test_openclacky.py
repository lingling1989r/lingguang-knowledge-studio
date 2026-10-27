import json
import subprocess
import pytest
from app import openclacky, store


def test_ndjson_extracts_final_object():
    text = '\n'.join(json.dumps(x) for x in [{"type":"system"},{"type":"assistant_message","content":"{\"ok\":true}"},{"type":"done"}])
    assert json.loads(openclacky.parse_events(text)) == {"ok":True}
    with pytest.raises(RuntimeError):
        openclacky.parse_events('{"type":"assistant_message","content":"{}"}')


def test_writer_secrets_are_stdin_only_and_home_is_isolated(monkeypatch):
    monkeypatch.setattr(store, "ai_config", lambda:{"api_key":"TEST-SECRET", "api_base":"https://example.invalid/v1", "model":"test"})
    monkeypatch.setattr(openclacky, "command", lambda:["ruby", "runner.rb"])
    def run(command, **kwargs):
        assert "TEST-SECRET" not in str(command)
        assert "TEST-SECRET" in kwargs["input"]
        assert kwargs["env"]["HOME"] == kwargs["cwd"]
        assert kwargs["env"]["CLACKY_TELEMETRY"] == "0"
        return subprocess.CompletedProcess(command, 0, '{"type":"assistant_message","content":"{}"}\n{"type":"done"}', '')
    monkeypatch.setattr(subprocess, "run", run)
    assert openclacky.complete({"messages":[]}, {}) == '{}'


def test_real_bundled_cli_against_local_mock_model(monkeypatch):
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    import threading
    if not (openclacky.runtime_root() / "bin/ruby").is_file():
        pytest.skip("Stage pinned OpenClacky runtime to run this integration test")
    received = []
    class Model(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass
        def do_POST(self):
            request = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            received.append(request)
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream')
            self.end_headers()
            for delta, finish in [({'role':'assistant','content':'{"ok":true}'},None),({},'stop')]:
                chunk={'id':'test','object':'chat.completion.chunk','choices':[{'index':0,'delta':delta,'finish_reason':finish}]}
                self.wfile.write(('data: '+json.dumps(chunk)+'\n\n').encode())
            self.wfile.write(b'data: [DONE]\n\n')
    server = ThreadingHTTPServer(('127.0.0.1',0), Model)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setattr(store, "ai_config", lambda:{"api_key":"mock-key", "api_base":f"http://127.0.0.1:{server.server_port}/v1", "model":"mock-model"})
    try:
        result = openclacky.complete({"messages":[{"role":"user","content":"Return JSON"}]}, {"type":"object"})
        assert json.loads(result) == {"ok":True}
        assert received and all(not req.get("tools") for req in received)
    finally:
        server.shutdown()
        server.server_close()


def test_local_model_url_allows_only_loopback_http():
    from app.admin import model_url
    from fastapi import HTTPException
    assert model_url('http://127.0.0.1:11434/v1') == 'http://127.0.0.1:11434/v1'
    for url in ['http://evil.test/v1','http://localhost.evil.test/v1','http://user:secret@localhost/v1']:
        with pytest.raises(HTTPException):model_url(url)
