# 灵光 · B站浏览器插件 0.1 内测版

打开B站视频页，点击插件，即可使用自己的设备下载音频并转录全文；可选使用自己的模型生成图文、保存到自己的飞书。当前验证环境为 **macOS Apple芯片 + Chrome for Testing**；支持Chrome/Edge的Manifest V3扩展形式，Windows/Linux本机组件尚未完成适配，未上架应用商店。

## 安装包怎么用

1. 解压安装包。在Chrome打开 `chrome://extensions`（Edge为 `edge://extensions`），手动开启开发者模式，点击“加载已解压的扩展程序”，选择包内的 **浏览器插件** 文件夹。
2. 准备Apple芯片版Python 3.11+、FFmpeg和ffprobe；如果使用Homebrew，可安装 `ffmpeg`。图文配图的PNG转换另需Cairo。纯转录无需写作API Key。
3. 双击 **本机组件/integrations/browser/安装本机组件.command**。它在用户应用数据目录创建Python环境、安装依赖、下载并校验约443MiB的语音模型，再注册本机桥接。首次安装需要网络和足够空间；下载失败可重新运行。可选择Chrome或Edge。
4. 回到B站视频页，点击插件图标，确认自动填写的视频地址，再点击“转录完整内容”。关闭弹窗后本机任务会继续，重新打开即可查看进度。
5. 完成后通过全文TXT、字幕SRT、JSON或素材包按钮下载，浏览器会询问保存位置。“生成图文”需要先在可选设置中填自己的模型/API，保存后可测试连接；测试会产生自己的模型请求费用。飞书另需自己的自建应用权限和凭据。

首次加载无需复制扩展ID。当前固定ID为 `jkklgikofmfpeoddechmkaapiomgjeng`。不要在未注册本机组件时把“插件页面能打开”当作转录已可用。Edge形式与Chrome共用源码，真实浏览器联调以测试记录为准。

## 为什么还有一个本机组件

浏览器扩展不能直接运行FFmpeg、Python和语音模型。插件负责当前链接、任务列表和下载入口；本机组件负责重任务。Chrome通过Native Messaging启动短时桥接进程，桥接只开放固定操作；组件在本机loopback端口运行自己的队列，使用启动锁避免重复进程、使用任务去重避免连续点击重复提交。无需中央转录服务器，也不需要给网站开放远程接口。

扩展仅申请 `activeTab`、`nativeMessaging`、`downloads`，没有Cookie、浏览历史、所有网站或远程代码权限。读取当前链接发生在用户打开插件之后，没有自动上传浏览记录。组件不绕过付费、登录或地区限制；公开播放和下载仍取决于来源平台。

## 数据与限制

- 只支持B站单视频的**第1分P**，不静默把其他分P改成第1集。多分P课程须分集支持后再处理，当前不会自动转录整套合集。
- 转录模式只下载平台提供的音频，不是上传者的原始视频母版；图文模式才下载画面用于截图。素材包包含当次实际下载/生成的素材。
- 机器识别不是逐字人工校对稿；保留来源与时间戳，不用摘要替代全文。短词和重复话语不因字数少被删掉。
- 默认并发1，最长240分钟，下载上限3GiB，要求至少5GiB可用空间。模型和音频还会额外占空间。历史保存在本机，弹窗显示最近30条。
- 组件数据、模型、Python环境、运行代码位于 `~/Library/Application Support/LingguangBrowser/`，不会在安装包内保存个人任务或凭据。源码移到标准应用数据目录后运行，避免浏览器读取桌面/下载文件夹的权限问题。
- 本机API和飞书密钥写在 `state/ai.json`、`state/feishu.json`（0600，父目录0700）；当前桥接配置未接系统钥匙串。不写入浏览器同步存储，不打包开发者的账号。
- 转录只用本机模型。图文会把写作材料发给用户选择的模型/API；飞书发布会上传文章和图片。可选OpenClacky适配器使用隔离HOME、关闭遥测、禁止工具调用；需具备相应运行时。
- 任务记录在重启后保留，中断任务标记失败，可重新提交；重试创建新任务，不自动混用旧识别结果。单独的 `transcribe_file` 命令可以重用同一音频输出目录中的识别检查点。
- 关闭弹窗不会取消；需要取消请点任务按钮。任务结束后可停止空闲本机组件；刷新/重新打开插件会自动启动组件。
- 全部Python/ML依赖和模型未塞进扩展JS中；首次安装会下载。当前不是无需任何前置条件的商店发行版。

## 开发与手动注册

```sh
# 在项目或独立组件目录执行；推荐使用应用数据目录内的Python环境
python3 -m pip install -r integrations/browser/requirements.txt
python3 -m integrations.browser.prepare_model
python3 -m integrations.browser.install --browser chrome
# 已有模型时可指定；模型应位于浏览器可访问的应用数据目录
python3 -m integrations.browser.install --browser edge --model-path /absolute/path/to/model
```

注册器将运行代码复制到组件目录，只允许固定扩展ID连接，不修改来源网站的CORS和登录Cookie。调试日志为组件目录中的 `native.log` 和 `worker.log`。如移动整个组件环境、修改Python位置或更换扩展ID，需要重新注册。Chrome for Testing须使用 `--browser chrome-testing`，仅测试目录注册不等于用户Chrome已安装。

## 验证

- `python3 -m pytest tests/test_browser_extension.py -q`：原生消息长度、禁止任意命令/路径、本机令牌、重复提交、无写作API转录、HTML转义。
- `node --test integrations/browser/extension/test.mjs`：链接规范化、分P限制、最小权限。
- `python3 -m tests.browser_extension_smoke`：临时Chrome测试配置，真实扩展→原生宿主→本机服务→模拟模型。测试会恢复临时宿主注册并清理自己的组件进程。
- 真实B站第1集BV1vXJkz1E8U已通过相同本地识别引擎完成81分钟转录；这不代表所有视频权限、真实写稿模型和飞书权限均已验证。

[Native Messaging官方说明](https://developer.chrome.com/docs/extensions/develop/concepts/native-messaging) · [activeTab官方说明](https://developer.chrome.com/docs/extensions/develop/concepts/activeTab) · [模型来源](https://huggingface.co/mlx-community/whisper-large-v3-turbo-q4)
