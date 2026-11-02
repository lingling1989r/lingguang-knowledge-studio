#!/bin/zsh
set -e
BROWSER_SOURCE_ROOT="$(cd -- "$(dirname "$0")/../.." && pwd)"
BROWSER_DATA_ROOT="$HOME/Library/Application Support/LingguangBrowser"
if [[ "$(uname -m)" != "arm64" ]]; then
  echo "当前内测组件仅支持macOS Apple芯片。"
  read "?按回车退出。"
  exit 1
fi
if ! command -v ffmpeg >/dev/null || ! command -v ffprobe >/dev/null; then
  echo "请先安装FFmpeg和ffprobe；如已安装Homebrew，可运行 brew install ffmpeg。"
  read "?按回车退出。"
  exit 1
fi
mkdir -p "$BROWSER_DATA_ROOT"
python3 -m venv "$BROWSER_DATA_ROOT/venv"
"$BROWSER_DATA_ROOT/venv/bin/python" -m pip install -r "$BROWSER_SOURCE_ROOT/integrations/browser/requirements.txt"
cd "$BROWSER_SOURCE_ROOT"
export PYTHONPATH="$BROWSER_SOURCE_ROOT"
"$BROWSER_DATA_ROOT/venv/bin/python" -m integrations.browser.prepare_model
printf "选择浏览器：1 Chrome（默认），2 Edge："
read browser_choice
BROWSER_TARGET="chrome"
if [[ "$browser_choice" == "2" ]]; then BROWSER_TARGET="edge"; fi
"$BROWSER_DATA_ROOT/venv/bin/python" -m integrations.browser.install --browser "$BROWSER_TARGET" --model-path "$BROWSER_DATA_ROOT/models/whisper-large-v3-turbo-q4"
echo "本机组件安装完成。请重新打开浏览器插件。"
read "?按回车关闭。"
