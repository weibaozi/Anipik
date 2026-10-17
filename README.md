# Anipik

追番自动下载：按订阅定时搜索 RSS 站点，识别新集数，交给下载器（目前是 PikPak 官方客户端）下载到本地媒体库，带 Web 管理界面和 Discord 通知。

**Features**

- 以番剧为中心的订阅，每部番可绑定多个来源（按优先级），每个来源单独设置关键词 / 包含 / 排除
- 新建订阅时实时预览搜索结果：集数识别、字幕组、是否会下载，一键把标签加为过滤条件
- bgm.tv 封面、开播日期、总集数；可按季度归档（如 `26年10月/番名`）
- 下载器可插拔；PikPak 客户端通过本机调试端口调用官方模块，云端下载完成后直接下载到本地
- 每一步有检查点，崩溃 / 重启后自动续上，结果不确定时进入「需要处理」而不是盲目重试
- 内置 Discord 机器人：随 anipik 启动，下载完成 / 失败 / 需要处理时通知；支持 `!status` `!scan` 命令

## 安装

需要 Python 3.11+ 和 Node.js 18+。双击 **run anipik.bat** 即可：首次会创建 `.venv` 并安装依赖，启动时自动构建网页。

**更新**：`git pull` 之后照常双击 run anipik.bat（先在托盘里退出旧的）。它会安装新增的 Python 依赖，
并在网页源码有变化时自动重新构建 `anipik/web/dist`（这个目录不在 git 里），不需要手动 `npm run build`。

## 使用

1. 先完全退出 PikPak（包括托盘），然后双击 **run anipik.bat**（首次会自动构建前端）。
   没有命令行窗口：Anipik 以**托盘图标**运行，并自动打开 http://127.0.0.1:8964。
   想要桌面 / 开始菜单快捷方式，运行一次 `.venv\Scripts\python -m anipik shortcut`。
2. anipik 会自动以调试端口（只监听本机）启动 PikPak 并最小化到托盘；首次需要在客户端里登录。
   如果 PikPak 已经以普通方式运行，在设置页点「重启 PikPak」。
3. 在「来源」添加 RSS 站点（内置常用站点预设），在「订阅」新建订阅
4. （可选）在设置页开启 Discord 通知，填写 bot token 和要通知的用户 / 频道 ID；机器人随 anipik 一起启动。
   命令需要在 Developer Portal 开启 Message Content intent

**托盘图标**：双击打开网页；右键菜单有 立即扫描 / 打开下载目录 / 打开日志 / 开机自启 / 重启 / 退出。
悬停显示下载数和 PikPak 连接状态。再次启动时不会开第二个实例，只会打开网页。日志在 `data/anipik.log`。

所有配置（媒体库目录、PikPak、调度、Discord）都在设置页里，保存在数据库中，没有配置文件。
数据保存在 `data/anipik.db`（SQLite）。API 没有认证，默认只监听 127.0.0.1；局域网访问用 `--host 0.0.0.0`。

## 命令行

```
.venv\Scripts\python -m anipik --help
```

| 命令 | 说明 |
|---|---|
| `tray` | 托盘模式（无控制台，用 pythonw），`--open` 启动后打开网页 |
| `serve` | 控制台模式：Web 界面 + API + 调度器，日志输出到窗口，便于调试 |
| `shortcut` | 创建桌面 / 开始菜单快捷方式（`--startup` 开机自启，`--remove` 删除） |
| `run` | 只运行调度器（无界面） |
| `scan --dry-run` | 预览这次扫描会下载什么，不提交任何任务 |
| `status` / `probe` | 订阅和任务概况 / 检测下载器连接 |
| `retry JOB` / `mark SUB EP...` | 处理卡住的任务 / 手动标记集数 |
| `migrate` | 从旧版 `old/anime_rss.yaml` 和 `old/setting.yaml` 导入（可重复执行） |

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
