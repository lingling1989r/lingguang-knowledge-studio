"""Build locally on each target OS. Never bundle .state or user credentials."""
import shutil
import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parent.parent
from desktop.vendor_openclacky import stage
stage()
command = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--windowed", "--onedir",
    "--name", "Lingguang Knowledge", "--paths", str(root),
    "--add-data", f"{root / 'LICENSE'}:.",
    "--add-data", f"{root / 'THIRD_PARTY_NOTICES.md'}:.",
    "--add-data", f"{root / 'desktop/README.md'}:desktop",
    "--add-data", f"{root / 'web'}:web", "--add-data", f"{root / 'assets'}:assets",
    "--add-data", f"{root / 'desktop/openclacky_runner.rb'}:desktop",
    "--add-data", f"{root / '.desktop-vendor/openclacky'}:vendor/openclacky",
    "--hidden-import", "desktop.runtime",
    "--collect-submodules", "app", "--collect-submodules", "uvicorn",
    "--collect-all", "yt_dlp", "--collect-all", "webview",
    "--hidden-import", "filelock", "--hidden-import", "cairosvg",
    "--exclude-module", "pytest", "--exclude-module", "tkinter", "--exclude-module", "IPython"]
if sys.platform == "darwin":
    command += ["--collect-all", "mlx_whisper", "--collect-all", "mlx"]
else:
    command += ["--collect-all", "faster_whisper"]
cairo = Path("/opt/homebrew/lib/libcairo.2.dylib")
if cairo.is_file():
    command += ["--add-binary", f"{cairo}:."]
# Use the user's FFmpeg installation. Do not redistribute arbitrary Homebrew GPL builds.
command += [str(root / "desktop/main.py")]
subprocess.run(command, cwd=root, check=True)
