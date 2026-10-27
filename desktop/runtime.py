"""Desktop lifecycle. No cloud daemon or project-local personal state."""
import os
import platform
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
import urllib.request


def data_directory():
    if sys.platform == "darwin":
        root = Path.home() / "Library/Application Support"
    elif sys.platform == "win32":
        root = Path(os.getenv("LOCALAPPDATA", Path.home() / "AppData/Local"))
    else:
        root = Path(os.getenv("XDG_DATA_HOME", Path.home() / ".local/share"))
    return root / "LingguangKnowledge"


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def worker_command():
    if getattr(sys, "frozen", False):
        return [sys.executable, "--worker"]
    return [sys.executable, "-m", "desktop.main", "--worker"]


class LocalWorker:
    def __init__(self, directory=None):
        self.directory = Path(directory or data_directory())
        self.port = free_port()
        self.process = None
        self.log = None

    @property
    def url(self):
        return f"http://127.0.0.1:{self.port}"

    def start(self):
        self.directory.mkdir(parents=True, exist_ok=True)
        os.chmod(self.directory, 0o700)
        env = os.environ.copy()
        env.update(STUDIO_STATE_DIR=str(self.directory), STUDIO_PORT=str(self.port), STUDIO_DESKTOP="1")
        # Finder-launched macOS apps do not inherit the user's shell PATH.
        env["PATH"] = os.pathsep.join([str(Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent)) / "bin"), "/opt/homebrew/bin", "/usr/local/bin", env.get("PATH", "")])
        self.log = open(self.directory / "desktop.log", "ab", buffering=0)
        self.process = subprocess.Popen(worker_command(), env=env, stdout=self.log, stderr=self.log,
            start_new_session=sys.platform != "win32",
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0)
        try:
            deadline = time.monotonic() + 90
            while time.monotonic() < deadline:
                if self.process.poll() is not None:
                    raise RuntimeError("本机服务未能启动，请查看 desktop.log。")
                try:
                    with urllib.request.urlopen(self.url + "/api/status", timeout=1) as response:
                        if response.status == 200:
                            return self.url
                except (OSError, TimeoutError):
                    time.sleep(0.15)
            raise RuntimeError("本机服务启动超时，请查看 desktop.log。")
        except BaseException:
            self.stop()
            raise

    def stop(self):
        if self.process and self.process.poll() is None:
            if sys.platform == "win32":
                subprocess.run(["taskkill", "/PID", str(self.process.pid), "/T", "/F"], capture_output=True)
            else:
                os.killpg(self.process.pid, signal.SIGTERM)
                try:
                    self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(self.process.pid, signal.SIGKILL)
            self.process.wait(timeout=10)
        if self.log:
            self.log.close()
