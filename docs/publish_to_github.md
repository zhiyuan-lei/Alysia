# GitHub 仓库发布说明

仓库地址：<https://github.com/zhiyuan-lei/Alysia>

本文件记录本仓库的开源发布口径与后续维护约定。上次更新：2026-10-31。

## 发布状态

| 项目 | 状态 |
| --- | --- |
| 远端 | `origin` → `https://github.com/zhiyuan-lei/Alysia.git` |
| 默认分支 | `main` |
| 入库文件数 | 1053（约 25 MB 工作树） |
| 不含 | `models/`、`workspace/`、`runs/`、`supervisor/` 运行时日志、`audit/*.jsonl`、`tools/bilibili-mcp/bili_credential.json` |
| 许可 | MIT |

## 日常推送

```powershell
Set-Location D:\Alysia
git status --short          # 先确认没有把凭证或运行产物带进来
git add -A
git commit -m "feat: ..."
git push origin main
```

首次在新机器推送时，git 会通过 GitHub 凭据管理器要求授权；也可以设置个人访问令牌（用户名填 GitHub 用户名，密码填令牌）。

## 提交前必须确认

```powershell
# 1. 凭证与运行记录没有入库
git ls-files | Select-String -Pattern '\.env$|config\.yaml$|credential|\.pem$|\.key$|audit/.*\.jsonl$'

# 2. 仓库里没有真实密钥
git grep -nE 'ghp_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9]{32,}'

# 3. 测试通过
uv run python -m pytest tests -m "not integration and not h3_local"
```

三条都干净再推。第 1 条有输出说明有文件该进 `.gitignore`。

## CI

`.github/workflows/ci.yml` 在 `windows-latest` 上跑 Python 3.11 与 3.12 两个版本：

1. `uv sync --extra dev`
2. `python -m alysia doctor`
3. `python -m alysia create "... " --provider mock`（最小链路冒烟）
4. `pytest tests -m "not integration and not h3_local"`
5. 前端 `npm ci` / `npm run test -- --run` / `npm run build`

Linux 与 macOS 尚未取得实测证据，因此没有放进矩阵——把没跑过的平台标成通过违反本项目的证据约定。

## 仓库设置建议

- 开启 **Private vulnerability reporting**（对应 `SECURITY.md` 的报告渠道）。
- Description：`Alysia — 面向 B 站的自主创作者系统：可恢复的内容流水线，带人工审核与发布闸门`
- Topics：`ai-agent`、`bilibili`、`video-generation`、`python`、`remotion`、`content-pipeline`
- About 里勾选 Issues；Discussions 可按需开启。
- 不建议上传生成视频与大体积中间文件；README 顶部如需截图，控制在 500 KB 以内。

## 提交身份

仓库级提交身份已设为：

```text
user.name  = zhiyuan-lei
user.email = 54499271+zhiyuan-lei@users.noreply.github.com
```

`users.noreply.github.com` 地址不会泄露真实邮箱。若要改用其他身份：

```powershell
git config user.name "你的名字"
git config user.email "你的邮箱"
git commit --amend --reset-author --no-edit   # 只改最近一次提交
```

已推送的历史改写需要 `git push --force-with-lease`，执行前先确认没有其他人基于该分支工作。
