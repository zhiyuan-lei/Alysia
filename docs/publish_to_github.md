# GitHub 仓库发布说明

仓库地址：<https://github.com/zhiyuan-lei/Alysia>

本文件记录本仓库的开源发布口径与后续维护约定。上次更新：2026-10-31。

## 发布状态

| 项目 | 状态 |
| --- | --- |
| 远端 | `origin` → `https://github.com/zhiyuan-lei/Alysia.git` |
| 可见性 | Public |
| 默认分支 | `main` |
| 入库文件数 | 1062（仓库体积约 6.2 MB） |
| CI | `.github/workflows/ci.yml`；Windows 上 Python 3.11 与 3.12 双绿 |
| 描述与 Topics | 已设置：`ai-agent`、`bilibili`、`video-generation`、`python`、`remotion`、`content-pipeline`、`llm` |
| 不含 | `models/`、`workspace/`、`runs/`、`supervisor/` 运行时日志、`audit/*.jsonl`、`tools/bilibili-mcp/bili_credential.json` |
| 许可 | MIT |

依赖由 Dependabot 按月提 PR（`.github/dependabot.yml`），合并方式为 squash。合并后动过的依赖，`uv.lock` 会随 PR 一起更新。

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

1. `pip install uv`，`choco install ffmpeg`（`render.mock` 的 health 依赖 ffmpeg 在 PATH）
2. `uv sync --extra dev`
3. `python -m alysia doctor`
4. `python -m alysia create "..." --provider mock`（最小链路冒烟）
5. `pytest tests -m "not integration and not h3_local"`
6. 工作树干净断言（`uv.lock` 除外）
7. 前端 `npm ci` / `npm run test -- --run` / `npm run build`

三个曾经踩过的坑，改动 CI 时不要退回去：

- **强制 UTF-8**：`PYTHONUTF8=1` 与 `PYTHONIOENCODING=utf-8`。Windows runner 控制台默认 cp1252，Rich 输出中文表格会抛 `UnicodeEncodeError`。
- **冒烟在临时目录跑**：`ALYSIA_CONFIG_FILE` 指向仓库的 `config.example.yaml`，工作目录用 `${{ runner.temp }}`，否则 `create` 会往检出的 `runs/` 与 `knowledge/` 写产物。
- **工作树干净断言**：测试与冒烟不允许改动已入库文件。`uv.lock` 是唯一豁免项，Dependabot 改依赖区间后 `uv sync` 重写它属于预期行为。

Linux 与 macOS 尚未取得实测证据，因此没有放进矩阵——把没跑过的平台标成通过违反本项目的证据约定。

## 仓库设置

已完成的设置：

- 可见性 **Public**；Description 与 Topics 已填。
- Issues 开启，Wiki 与 Projects 关闭。
- `SECURITY.md` 里的 Private vulnerability reporting 在 Public 仓库上可用（GitHub 要求先切公开才能对该端点操作）。

仍建议手动确认的项目：

- About 侧栏的 Releases / Packages 区块按需显示。
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
