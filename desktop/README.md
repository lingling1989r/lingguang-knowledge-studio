# 灵光知识库桌面版（macOS Apple Silicon 内测）

原生桌面窗口启动本机处理进程。下载、切音频、语音识别、截图、素材和历史保存在用户设备；写作由用户自己的模型/API或Agent完成。没有中央转录服务。不是完全离线应用：视频来源、准备语音模型、外部模型调用、可选飞书发布仍需联网。

## 使用

1. 打开 `Lingguang Knowledge.app`。当前包为本机构建的内测版，未做开发者签名与Apple公证，不宣称可直接向所有用户分发。不要关闭系统安全机制。
2. 当前版本需要用户设备已有 FFmpeg/ffprobe（macOS可从其正规安装渠道安装）；包内不分发任意Homebrew FFmpeg构建。
3. 进入“后台管理”，首次创建自己的本机管理密码。选择“内置OpenClacky”，填写自己的模型名称、HTTPS API地址（本地模型可用localhost/127.0.0.1的HTTP接口）与API Key，保存并测试。也可选择自己的Codex CLI或HTTPS Agent。
4. 返回工作台，粘贴B站、YouTube链接，或读取播客RSS并选择单集；默认不勾选飞书发布，可先生成到本机。
5. 历史、图文包、完整转录和素材下载沿用原工作台。需要飞书时，在本机后台连接自己的应用。

当前内测版不自动下载模型权重。需事先准备本地语音模型：macOS默认识别 `~/.cache/huggingface/hub/models--mlx-community--whisper-large-v3-turbo-q4/snapshots/` 下含 `weights.npz` 的模型，或通过 `WHISPER_MODEL_PATH` 指定本地模型目录。可先在具备Hugging Face下载工具的环境执行 `hf download mlx-community/whisper-large-v3-turbo-q4`；模型权重不包含在应用包内。默认并发1，时长上限240分钟，下载上限3GiB，要求至少5GiB可用空间，可在后台调整。长视频还需要临时音频、截图和模型空间，建议保留更多余量。

关闭桌面窗口会确认退出，确认后停止本机进程和其子进程；正在处理的任务会中断，重新打开后保留记录并可重试。当前没有后台托盘常驻或自动恢复断点。

## 数据与隐私

macOS 数据目录：`~/Library/Application Support/LingguangKnowledge/`。与网站源码目录的 `.state` 分离，不自动复制原来的网站凭据或历史。设置保留在本机，密钥文件权限0600，尚未接入系统钥匙串。复制知识库/备份数据前注意其中的凭据文件。日志为此目录下 `desktop.log`。

服务使用随机loopback端口，不绑定公网；只运行一个桌面实例。本地进程同属当前用户，不是对恶意本机程序的安全隔离。Obsidian插件如需连接桌面实例，暂需从 desktop.log/系统进程获得端口，固定端口发现尚未实现。

## OpenClacky集成

固定打包OpenClacky 1.5.3、Ruby及运行依赖；并保留原项目MIT许可。来源： https://github.com/clacky-ai/openclacky 。不是把开发者的 `~/.clacky`、登录或密钥打进安装包。

应用自己的写稿入口调用非交互CLI，使用临时HOME和配置，通过stdin传模型密钥和材料；关闭 `CLACKY_TELEMETRY`。写稿专用适配器禁止工具定义和工具查找，防止非交互自动批准模式执行转录中的指令。不提供OpenClacky通用聊天、终端控制或技能市场；这些是上游能力，不等于本桌面版已集成。用户自己的模型费用照常发生。

## 源码运行和构建

```sh
python3 -m venv .venv-desktop
.venv-desktop/bin/pip install -r desktop/requirements.txt
# Ruby环境中安装固定版本，用于构建内置Agent
gem install openclacky -v 1.5.3
# 可指定所用Ruby可执行文件；不使用系统旧Ruby
STUDIO_BUILD_RUBY=/absolute/path/to/ruby .venv-desktop/bin/python -m desktop.build
# 源码启动（需相应Python依赖）
.venv-desktop/bin/python -m desktop.main
```

当前构建脚本仅在macOS Apple Silicon验证；Windows/Linux的界面、Ruby运行时和打包还需各自适配，未提供已测试安装包。构建只收集静态资源、应用模块、明确的依赖，不包括.state、个人.clacky、模型缓存。

包内提供 `--worker` 供桌面生命周期管理，`--diagnose` 检查Ruby、本地ASR模块及SVG渲染。依赖测试不代表某条长视频、某个模型API或飞书权限已成功处理。

## 分发前仍需完成

真实桌面交互与下载保存对话框、干净设备首次运行、真实模型写稿和长视频回归；正式签名公证；第三方依赖许可证及对应源码的完整分发审核；Windows版本适配。当前为可运行的内测构建，不是已完成商店审核的正式发行版。
