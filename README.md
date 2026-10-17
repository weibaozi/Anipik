# Anipik

追番自动下载：按订阅定时搜索 RSS 站点，识别新集数，交给下载器（目前是 PikPak 官方客户端）下载到本地媒体库，带 Web 管理界面和 Discord 通知。

**Features**

- 以番剧为中心的订阅，每部番可绑定多个来源（按优先级），每个来源单独设置关键词 / 包含 / 排除
- 新建订阅时实时预览搜索结果：集数识别、字幕组、是否会下载，一键把标签加为过滤条件
- bgm.tv 封面、开播日期、总集数；可按季度归档（如 `26年10月/番名`）
- 下载器可插拔；PikPak 客户端通过本机调试端口调用官方模块，云端下载完成后直接下载到本地
- 每一步有检查点，崩溃 / 重启后自动续上，结果不确定时进入「需要处理」而不是盲目重试
- Discord 通知（复用 `chatbot/discordbot`）

## 安装

需要 Python 3.11+ 和 Node.js 18+。

```
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
cd anipik\web && npm install && npm run build
```

## 使用

1. 完全退出 PikPak，再以调试端口启动并登录（只监听本机）：

   ```
   "C:\Program Files\PikPak\PikPak.exe" --remote-debugging-port=19223 --remote-debugging-address=127.0.0.1
   ```

2. 双击 **run anipik.bat**（首次会自动构建前端），打开 http://127.0.0.1:8964
3. 在「来源」添加 RSS 站点（内置常用站点预设），在「订阅」新建订阅
4. （可选）在 `setting.yaml` 填写 `discord_token`，启动 **run dcbot.bat**，并在设置页开启 Discord 通知

数据保存在 `data/anipik.db`（SQLite）。API 没有认证，默认只监听 127.0.0.1。

## 命令行

```
.venv\Scripts\python -m anipik --help
```

| 命令 | 说明 |
|---|---|
| `serve` | Web 界面 + API，调度器在同一进程运行 |
| `run` | 只运行调度器（无界面） |
| `scan --dry-run` | 预览这次扫描会下载什么，不提交任何任务 |
| `status` / `probe` | 订阅和任务概况 / 检测下载器连接 |
| `retry JOB` / `mark SUB EP...` | 处理卡住的任务 / 手动标记集数 |
| `migrate` | 从旧版 `old/anime_rss.yaml` 和 `setting.yaml` 导入（可重复执行） |

## 开发

```
.venv\Scripts\python -m pytest tests
cd anipik\web && npm run dev     # 热更新前端，/api 代理到 :8964
```

目录结构：

```
anipik/
  models.py db.py      领域模型（订阅 / 来源绑定 / 集数 / 任务）与 SQLite
  scheduler.py         扫描来源 -> 新集数入队；轮询推进下载任务
  matcher.py           标题集数解析、过滤、磁力规范化
  sources/             来源插件（rss_search）
  downloaders/         下载器插件（pikpak_client）
  api/                 FastAPI 接口
  web/                 Vue 3 + Naive UI 前端
old/                   旧版（pikpakapi + streamlit），已不再使用
```
