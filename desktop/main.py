"""Run with python -m desktop.main, or use the packaged application."""
import os
import sys
from pathlib import Path


def worker():
    import uvicorn
    from app.server import app
    uvicorn.run(app, host="127.0.0.1", port=int(os.environ["STUDIO_PORT"]), log_level="warning")


def main():
    if getattr(sys, "frozen", False):
        import ctypes.util
        cairo = Path(sys._MEIPASS) / "libcairo.2.dylib"
        original_find = ctypes.util.find_library
        if cairo.exists():
            ctypes.util.find_library = lambda name: str(cairo) if name in ("cairo", "cairo-2", "libcairo-2") else original_find(name)
    if "--diagnose" in sys.argv:
        import json
        import subprocess
        import mlx.core
        import mlx_whisper
        import cairosvg
        from app.openclacky import command
        result = subprocess.run([command()[0], "--version"], text=True, capture_output=True, check=True)
        svg = b'<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"><rect width="10" height="10" fill="red"/></svg>'
        png = cairosvg.svg2png(bytestring=svg)
        print(json.dumps({"ruby":result.stdout.strip(), "local_asr_import":True,"svg_png":len(png)>0}))
        return
    if "--worker" in sys.argv:
        worker()
        return
    import webview
    from filelock import FileLock, Timeout
    from desktop.runtime import LocalWorker, data_directory
    directory = data_directory()
    directory.mkdir(parents=True, exist_ok=True)
    lock = FileLock(str(directory / "desktop.lock"))
    try:
        lock.acquire(timeout=0)
    except Timeout:
        webview.create_window("灵光知识库", html="<h2>应用已在运行</h2><p>请返回已打开的灵光知识库窗口。</p>", width=500, height=250)
        webview.start()
        return
    webview.settings["ALLOW_DOWNLOADS"] = True
    webview.settings["ALLOW_FILE_URLS"] = False
    service = LocalWorker(directory)
    try:
        url = service.start()
        webview.create_window("灵光知识库 · 本机工作台", url, width=1200, height=820,
            min_size=(900, 640), confirm_close=True)
        webview.start(private_mode=True)
    except Exception:
        webview.create_window("启动失败", html="<h2>本机服务启动失败</h2><p>请检查应用数据目录的 desktop.log。退出后重新启动。</p>", width=600, height=300)
        webview.start()
    finally:
        service.stop()
        lock.release()


if __name__ == "__main__":
    main()
