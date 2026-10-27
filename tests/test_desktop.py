import json
import subprocess
import urllib.request
from desktop.runtime import LocalWorker


def test_desktop_worker_uses_isolated_state_and_closes(tmp_path):
    service = LocalWorker(tmp_path)
    try:
        url = service.start()
        with urllib.request.urlopen(url + "/api/status") as response:
            status = json.load(response)
        assert status["request_token"]
        assert status["desktop"] is True
        with urllib.request.urlopen(url + "/") as response:
            assert b"<html" in response.read().lower()
        request = urllib.request.Request(url + "/api/settings", data=json.dumps({"author":"Desktop Test","wechat":"test","folder":""}).encode(), headers={"Content-Type":"application/json","X-Request-Token":status["request_token"]})
        with urllib.request.urlopen(request) as response:
            assert response.status == 200
        assert json.loads((tmp_path / "preferences.json").read_text())["author"] == "Desktop Test"
    finally:
        service.stop()
    assert service.process.poll() is not None
