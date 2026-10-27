"""Test the frozen backend and bundled Agent using only a local fake model API."""
import argparse
import json
import tempfile
import threading
import urllib.request
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from desktop import runtime


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("binary", type=Path)
    args = parser.parse_args()
    requests = []
    class Model(BaseHTTPRequestHandler):
        def log_message(self, *args): pass
        def do_POST(self):
            request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests.append(request)
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            for delta, finish in [({"role":"assistant","content":'{"ok":true}'},None),({},"stop")]:
                chunk = {"id":"test","object":"chat.completion.chunk","choices":[{"index":0,"delta":delta,"finish_reason":finish}]}
                self.wfile.write(("data: " + json.dumps(chunk) + "\n\n").encode())
            self.wfile.write(b"data: [DONE]\n\n")
    mock = ThreadingHTTPServer(("127.0.0.1",0), Model)
    threading.Thread(target=mock.serve_forever, daemon=True).start()
    runtime.worker_command = lambda: [str(args.binary.resolve()), "--worker"]
    try:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "ai.json").write_text(json.dumps({"api_key":"fake-smoke-key", "api_base":f"http://127.0.0.1:{mock.server_port}/v1", "model":"mock-model"}))
            (root / "agent.json").write_text('{"mode":"openclacky"}')
            service = runtime.LocalWorker(root)
            try:
                service.start()
                token = json.load(urllib.request.urlopen(service.url + "/api/status"))["request_token"]
                import http.cookiejar
                opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
                def post(path, value):
                    request = urllib.request.Request(service.url + path, data=json.dumps(value).encode(), headers={"Content-Type":"application/json","X-Request-Token":token})
                    with opener.open(request, timeout=45) as response:
                        return json.load(response)
                post("/api/admin/setup", {"password":"smoke-only-password"})
                result = post("/api/admin/test", {})
                assert result["ok"], result
                assert requests and all(not req.get("tools") for req in requests)
                print("PASS: frozen backend -> bundled Ruby/OpenClacky -> local mock model -> valid JSON; tools disabled")
            finally:
                service.stop()
    finally:
        mock.shutdown()
        mock.server_close()


if __name__ == "__main__":
    main()
