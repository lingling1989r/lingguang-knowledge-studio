# Lingguang Knowledge Studio / 灵光知识工作台

Open-source local workbench: Bilibili / YouTube / podcast RSS → transcription → structured notes / article → SVG assets → Feishu documents.

## Current release

MIT license for application code. Runs on your own computer or private environment; media processing uses your resources. Bring your own API credentials or Agent endpoint; optional local Codex CLI mode remains available for testing. No platform-hosted free inference is included.

Local single-user prototype. Feishu Wiki OAuth, browser extension, packaged desktop app, MCP server and managed subscriptions are **not implemented**. Public multi-user hosting requires additional authentication, tenant isolation and durable scheduling. The project does not yet ship an installer or Docker image.

Personal QR contact cards and third-party example screenshots have been removed. New requests do not append a contact card; you may customize rendering with your own assets. Empty history is expected on a fresh installation.

## Quick start

Install Python 3.11+ (original tested on macOS Python 3.13), FFmpeg/ffprobe, Cairo and a Chinese font. Run `pip install -r requirements.txt`. Install/download the matching speech model: MLX model on Apple Silicon, CTranslate2/faster-whisper model on Linux; set WHISPER_MODEL_PATH. Linux also needs STUDIO_FONT_PATH pointing to a Chinese font. The model must be present locally.

Start `python3 -m uvicorn app.server:app --host 127.0.0.1 --port 8765` (macOS can use 启动网站.command). Open http://127.0.0.1:8765/admin, create an admin password and select GPT API or your Agent. Fill your own credentials, then test the connection. Configure your own Feishu application and run the document/image test. Read .env.example for environment settings; it is an example, not automatically loaded.

The legacy defaults favor the author's Chinese article style; customize app/pipeline.py and rendering for your own learning workflow. Public release removed personal assets but does not claim full personalization or production readiness.

## Design and commercialization

See docs/开源私有交付与商业化调研.md for local/private/hybrid/MCP/extension options. Research proposals are separate from delivered code.

---

## Original engineering notes (sanitized)

# 当前测试环境：本机 Codex CLI

当前默认写稿模式为 **Codex CLI**，不通过 api.develop.cc/v1，也不读取网站保存的 API 地址或 API Key。管理员无需配置 API，用户只需提交 B站链接。后台入口 http://127.0.0.1:8765/admin 可查看并测试 Codex CLI 模式。

服务调用本机 `codex exec`，沿用当前操作系统用户的 CLI 登录、默认模型与 CLI 自身配置。不传模型覆盖参数；子进程移除 OPENAI_API_KEY、OPENAI_BASE_URL、AI_MODEL 环境变量，避免旧网关环境污染。需确保启动网站的用户执行 `codex login status` 显示已登录，且 `codex` 在 PATH 中。若 CLI 自身另行配置了服务商，实际路由由 CLI 配置决定。

任务通过标准输入传递内容，使用 JSON Schema 约束输出；在临时目录、read-only 沙箱和 ephemeral 会话中执行。网站负责视频下载、语音识别、截图、SVG 排版与飞书保存，CLI 只负责写稿。单次 CLI 最长等待10分钟，失败时保留任务，可从后台重试。运行会消耗当前 Codex 账号可用额度；这是本机测试方案，生产环境再接入管理系统 Agent。

保存后台接入方式为 Codex CLI 后即时生效，无需填密钥。其他 GPT API / Agent 模式保留供未来切换，当前未启用。以下旧版 API 说明仅适用于显式切换到相应模式。

# 灵光成稿 · B站到飞书

输入B站视频URL或BV号，读取公开视频音频，生成原创公众号稿、原视频截图、开头知识图谱、毛笔小标题与微信联系卡，保存为可编辑的飞书文档。

## 当前运行

本机网站：http://127.0.0.1:8765

双击 `启动网站.command` 可以再次启动。运行期间保持终端窗口打开；使用 Ctrl+C 关闭。当前版本仅接受本机访问。

配置在页面右上角“飞书已连接”/“发布设置”：作者、微信号、飞书文件夹与飞书应用。凭据不回传浏览器，不写进源代码或Git；本机 `.state/` 中的配置文件权限为600。

当前已有的AI网关实测返回额度不足。由管理员恢复平台 GPT 连接，或接入后台 Agent 后，可以继续生成新稿件；真实完成示例可直接查看、下载与打开飞书。示例不是新请求的自动生成结果。

## 能力

- 接受单个视频的第一分P，最多4小时；只访问校验后的B站视频页。
- yt-dlp 下载音视频；本机MLX Whisper或faster-whisper识别。
- AI根据内容输出原创摘要与结构化文章；不提供第三方视频的全文逐字转录。
- 自动生成SVG和PNG小标题、知识图谱，提取五张原视频截图。
- 飞书图片真实上传并核验；保存失败保留图文包，可在原文档上重试。
- 单个任务串行执行，任务历史保存在本机，重复处理中请求会复用同一任务。
- 图文包包含Markdown、HTML、SVG/PNG与截图；不包含内部识别文本、凭据或发布状态。
- 暂存默认使用作者的真实微信联系卡；更换作者时需关闭该卡，避免误用身份。

## 安装到另一台电脑

需要 Python 3.11+、ffmpeg、中文字体，以及已下载的语音识别模型。

```bash
python3 -m pip install -r requirements.txt
python3 -m uvicorn app.server:app --host 127.0.0.1 --port 8765
```

macOS安装Cairo后，通过DYLD_FALLBACK_LIBRARY_PATH指定动态库目录。Linux设置STUDIO_FONT_PATH到中文字体路径，WHISPER_MODEL_PATH到本机模型路径。

可用环境变量见 `.env.example`；程序不会自动加载该文件，部署时用进程环境或页面配置。可通过FEISHU_CONFIG读取原有飞书应用配置，不必复制秘密到代码。

## 验证

```bash
python3 -m pytest -q
node --check web/app.js
```

已验证：视频URL校验、跨网站请求保护、秘密不回传、重复任务去重、取消、内部识别文件不进入下载包、真实示例预览及配图加载。实际新稿件生成在AI写稿阶段因账户额度不足中断；未声称已经生成新稿并自动发布。

## 上线范围

本版本是个人本机工作台。静态网站托管不能运行ffmpeg和本机语音模型；面向团队或客户的版本需要独立的视频处理服务、账户隔离及每个用户自己的飞书授权。当前没有把个人飞书凭据、AI密钥或处理接口公开到互联网。


## 后台默认 GPT 与 Agent 接入

用户侧没有模型、API 地址或密钥设置。平台默认 GPT 由服务端 OPENAI_BASE_URL、OPENAI_API_KEY 和 AI_MODEL 配置（现有私有 ai.json 仍兼容）。网站不使用桌面 ChatGPT 会话作为 API。

管理系统提供 HTTPS 接口后，在服务端设置 STUDIO_AGENT_URL 与 STUDIO_AGENT_TOKEN，重启服务即可。Agent 优先于旧 GPT 网关，旧网关的额度故障不会阻挡 Agent 任务。

请求：POST STUDIO_AGENT_URL，Authorization: Bearer STUDIO_AGENT_TOKEN。JSON 包含 task_id、operation（compose_article）、messages（写作要求与带时间的视频素材）和 output_schema（Article JSON Schema）。Agent 在后台选择默认 GPT，返回 {"article": {...}}；article 必须符合 output_schema。网站继续负责结构校验、截图、SVG、排版与飞书保存。此接口已通过模拟响应测试，真实管理系统尚未提供地址，尚未完成真实 Agent 联调。


## 管理后台

打开 http://127.0.0.1:8765/admin，首次访问自行创建至少12字符的管理员密码。首页底部也有后台入口。后台支持默认 GPT / Agent 切换、私有密钥保存、真实连接测试、任务与错误查看、失败任务重试、修改密码和退出。登录有效8小时；连续5次错误登录后限制五分钟。修改密码会撤销所有登录。

保存连接不等于测试通过；点击“测试已保存连接”验证实际模型调用（会产生一次少量请求费用）。测试失败会阻止新写稿任务，修复后重新测试。密钥留空保留原值，已有值不回显，配置文件权限600。后台设置覆盖环境配置，无需重启。Agent 测试复用 compose_article 请求，output_schema 要求 {ok:true}，返回 {article:{ok:true}}。

此后台仍仅供本机使用；真实外部 Agent 地址未提供，尚未完成真实 Agent 联调。若忘记管理员密码，可关闭网站后删除本机 .state/admin-auth.json，再启动网站重新创建管理员；连接配置与稿件不受影响。


长视频支持：已放开30分钟门槛，当前上限4小时、单媒体下载限制3GiB。语音按120秒分段识别；材料较长时按块提炼带时间的要点，再合成文章，覆盖各段而不是截取前半段。长视频耗时与 Codex 调用次数增加，网页可离开后从历史入口继续查看。尚未用真实4小时视频完成端到端验证。

历史记录入口：http://127.0.0.1:8765/history。可按标题/BV号搜索和状态筛选，查看稿件、打开飞书、下载图文包；数据保存在 .state/jobs，重启仍保留。


## 转录与素材下载

新任务在机器识别完成后，独立保存 TXT 正文、SRT 时间字幕、JSON 分段时间数据；即使后续写稿失败，已生成转录仍可从历史记录下载。转录不经过摘要压缩，但保留语音识别阶段的噪声过滤；不是人工校对逐字稿。素材包还包含已下载视频（非原始母版）、已提取的 audio.wav，以及生成的截图、PNG、SVG。可通过 /api/jobs/{id}/materials 查看可下载文件并单独下载，也可使用 materials-package 打包下载。内部配置、凭据、发布状态和临时识别分片不会导出。

旧记录若没有保存转录导出，则不会凭摘要还原转录。示例也不会假装包含完整原视频转录。仅对拥有相应权利或获得授权的内容使用转录与媒体导出。


后台新增容量控制与飞书真实发布测试，详见 [30分钟视频成本与飞书接入](docs/30分钟视频成本与飞书接入.md)。当前成本为明确假设测算，非实际账单；飞书普通用户OAuth与跨租户访问尚未完成。


## YouTube 与播客 RSS

入口支持B站/BV号、YouTube watch、youtu.be、shorts、live和embed的单视频地址；不批量处理播放列表。YouTube复用yt-dlp和原有转录/截图/写稿/飞书链路，设备需能访问YouTube；部分视频可能受登录、反爬或地区限制。

播客选择“播客 RSS”，输入公开HTTPS RSS 2.0订阅地址，读取最近最多100集，选择一集再提交。需要item包含enclosure音频地址；不支持把平台节目网页当作RSS，也不支持私有订阅或登录付费源。RSS最多2MiB，重定向最多5次，拒绝本机/私有网络地址，XML禁止外部实体。单集媒体遵循后台下载大小限制，下载后ffprobe核验实际时长。音频不生成原视频截图，其他SVG配图、机器转录、素材下载及飞书保存继续使用；源音频导出名为source.m4a，实际编码由源站决定。自动识别语音语言。

新来源做了模拟下载、解析与校验测试；未用真实YouTube及RSS完成写稿到飞书的端到端联调。公网部署还需出站防火墙限制内网与元数据访问，DNS校验不能替代网络隔离。当前仍是本机单用户版本。
