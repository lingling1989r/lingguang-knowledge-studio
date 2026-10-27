"""Isolated, tool-free OpenClacky CLI writer. Model secrets never enter argv."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from . import store


def runtime_root():
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "vendor" / "openclacky"
    return store.ROOT / ".desktop-vendor" / "openclacky"


def command():
    root = runtime_root()
    ruby = root / "bin" / ("ruby.exe" if sys.platform == "win32" else "ruby")
    runner = store.ROOT / "desktop" / "openclacky_runner.rb"
    if ruby.is_file():
        return [str(ruby), str(runner)]
    ruby_path = shutil.which("ruby")
    if ruby_path and shutil.which("openclacky"):
        return [ruby_path, str(runner)]
    raise RuntimeError("未找到内置 OpenClacky 运行时，请重新安装完整桌面包。")


def ready():
    try:
        command()
        return bool(store.ai_config().get("api_key"))
    except RuntimeError:
        return False


def parse_events(stdout):
    messages = []
    done = False
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if event.get("type") == "assistant_message":
            messages.append(event.get("content", ""))
        if event.get("type") == "done":
            done = True
    if not done or not messages:
        raise RuntimeError("OpenClacky未返回完整文章，请检查模型响应与额度。")
    content = messages[-1].strip()
    if content.startswith("```json") and content.endswith("```"):
        content = content[7:-3].strip()
    value = json.loads(content)
    if not isinstance(value, dict):
        raise RuntimeError("OpenClacky返回格式无效，应为JSON对象。")
    return json.dumps(value, ensure_ascii=False)


def complete(payload, schema):
    config = store.ai_config()
    with tempfile.TemporaryDirectory(prefix="lingguang-writer-") as directory:
        env = os.environ.copy()
        # An empty HOME prevents loading personal Clacky plugins, sessions and hooks.
        env.update(HOME=directory, USERPROFILE=directory, CLACKY_TELEMETRY="0")
        for key in list(env):
            if key.startswith(("CLACKY_", "CLAUDE_", "ANTHROPIC_", "OPENAI_")) and key != "CLACKY_TELEMETRY":
                env.pop(key, None)
        root = runtime_root()
        if root.exists():
            env.update(GEM_HOME=str(root / "gems"), GEM_PATH=str(root / "gems"),
                RUBYLIB=os.pathsep.join(str(x) for x in (root / "ruby-lib", root / "ruby-lib" / "arm64-darwin24")))
            # Runtime arch directory varies with Ruby and build host.
            env["RUBYLIB"] = os.pathsep.join([str(root / "ruby-lib")] + [str(p) for p in (root / "ruby-lib").glob("*-*") if p.is_dir()])
        body = {"api_base":config["api_base"], "api_key":config["api_key"], "model":config["model"], "schema":schema, "messages":payload["messages"]}
        try:
            result = subprocess.run(command(), input=json.dumps(body, ensure_ascii=False), text=True,
                capture_output=True, cwd=directory, env=env, timeout=600)
        except subprocess.TimeoutExpired:
            raise RuntimeError("OpenClacky写稿超时，请稍后重试。") from None
        if result.returncode:
            raise RuntimeError("OpenClacky执行失败，请检查模型、API Key与本机运行时。")
        return parse_events(result.stdout)
