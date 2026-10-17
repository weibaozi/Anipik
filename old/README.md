# 旧版代码（已停用）

重构前基于第三方 `pikpakapi` + streamlit 的版本，仅作存档参考，不再维护：

- `main.py`：旧调度脚本；`web_main.py`：旧 streamlit 页面
- `utils/`：旧 RSS 解析、PikPak API 封装
- `anime_rss.yaml`：旧订阅规则（已通过 `python -m anipik migrate` 导入数据库；`migrate` 默认仍读取这里）
- `requirements.txt`：旧依赖（含冲突的重复版本）

这些文件移动后路径已变化（例如 `main.py` 按自身目录查找 `setting.yaml`），无法直接在这里运行。
请勿与新版同时运行旧调度器，否则会重复下载。
