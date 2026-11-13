# 科研通助手

在 Windows 本地定时签到，按 DOI 查找公开全文，经本人授权发布和跟踪科研通文献求助。可独立运行，也附带 Codex 文献下载技能。此项目由个人维护。

## 安装和登录

需要 Windows、Python 3.10 或以上和 Google Chrome。下载或克隆本项目，在目录内打开 PowerShell：

```powershell
powershell -ExecutionPolicy Bypass -File .\setup.ps1
```

如有多个 Python，运行时可用 `-Python 'C:\path\to\python.exe'` 指定解释器。

双击 `open-assistant.cmd`。点击「登录科研通」，在专用 Chrome 窗口中登录，然后点击「签到并同步」检查运行结果。浏览器会在本机 `data/browser` 保持登录状态。

## 定时签到

```powershell
powershell -ExecutionPolicy Bypass -File .\schedule.ps1
```

Windows 登录后及每小时检查一次。官网确认当天已签到后，当天会跳过重复签到。电脑关闭或 Windows 用户退出时暂停运行。最近一次运行结果在 `data/最近一次同步.txt`。停用可执行 `powershell -ExecutionPolicy Bypass -File .\schedule.ps1 -Remove`。

## 查找文献和发布求助

1. 在助手中输入 DOI。助手核对题录并尝试保存公开 PDF。
2. 若未获得全文，选中文献，点击「授权发布」，核对文章并指定悬赏积分。也可在官网手动发布，然后绑定求助详情链接。
3. 「签到并同步」和定时任务都会跟踪已有求助。找到普通下载入口后会尝试保存至 `data/文献`。标题无法自动核对时，文件标为待核对。采纳、驳回以及需要选择下载方式的情况请在官网处理。

自动填表目前面向有 DOI 的文章正文。验证码、页面改版或站点要求人工处理时，请在官网继续。互助文献按网站规则用于个人学习研究。 [签到说明](https://www.ablesci.com/knowledge/detail?id=21) · [求助须知](https://www.ablesci.com/post/detail?id=Pb63Qj)

## 在 Codex 中使用

```powershell
powershell -ExecutionPolicy Bypass -File .\setup.ps1 -InstallSkill
```

随后在 Codex 中说「用 `$ablesci-paper-download` 核对这篇论文，等我确认后再下载。DOI 是……」。只有题名也可以。技能会等你确认具体文章，再查找全文。需要发帖时，由你确认该篇的悬赏积分。技能与桌面助手使用同一份本地记录。

项目的 `data/` 包含登录资料、文献和求助记录，请保存在本机。
