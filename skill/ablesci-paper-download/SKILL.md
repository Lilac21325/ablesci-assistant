---
name: ablesci-paper-download
description: 按 DOI 或题名核对和下载指定学术文章，查找公开 PDF，或经用户授权通过 Windows 科研通助手发布并跟踪文献求助。
---

# 下载指定文献

读取本技能目录下的 `assistant-path.txt`，取得科研通助手的安装目录。以该目录下 `.venv\Scripts\python.exe` 执行 `paper_cli.py`。命令返回 JSON。若在项目源码中读取此技能，可使用项目根目录。缺少依赖时，按项目 README 安装。

1. 有 DOI 或 DOI 链接时用 `inspect <doi>`。只有题名时先 `search <题名>`，用作者、年份、期刊和 DOI 区分候选。展示题名、DOI 和出版商链接，等用户确认目标后再下载。用户明确表示已经核实题录并要求下载时，可使用该确认。
2. 对已确认的文章运行 `fetch <doi>`。当 `state` 为 `downloaded` 且 `file_exists` 为真，提供文件绝对路径。`review` 表示文件待核对。
3. 如需发科研通求助，先取得用户对该 DOI 和悬赏积分的明确授权，再运行 `request <doi> --points <积分>`。有原求助或提交结果待核对时，继续查原请求。
4. `status <doi>` 读取本地记录。`sync <doi>` 立即检查已发布的求助并尝试普通下载。只有确认 `post_url` 后才报告发布成功。`queued` 是待提交，`submitting` 或 `uncertain` 时先核对“我的求助”。如需登录，请用户打开 `open-assistant.cmd` 并点击“登录科研通”。应助采纳由用户在官网确认。
