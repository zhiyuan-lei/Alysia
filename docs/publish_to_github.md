# 把 Alysia 推送到 GitHub

本机的代码与提交已经准备好，但本机没有安装 `gh` CLI、没有 SSH 密钥，也没有保存的 GitHub 凭据，所以最后一步需要你提供身份。

## 方式一：先在网页建仓库，再用 HTTPS 推送（最简单）

1. 打开 <https://github.com/new>。
2. Repository name 填 `alysia`；可见性建议先选 **Private**，确认内容无误后再改 Public。
3. **不要**勾选 "Add a README / .gitignore / license"，让仓库保持空。
4. 在本目录执行：

```powershell
Set-Location D:\Alysia
git remote add origin https://github.com/<你的用户名>/alysia.git
git push -u origin main
```

推送时会弹出浏览器或终端要求登录 GitHub，按提示授权即可。若使用个人访问令牌（PAT），用户名填 GitHub 用户名，密码填令牌。

## 方式二：用 GitHub CLI

```powershell
winget install --id GitHub.cli
gh auth login
Set-Location D:\Alysia
gh repo create alysia --private --source=. --remote=origin --push
```

确认无误后改为公开：

```powershell
gh repo edit --visibility public --accept-visibility-change-consequences
```

## 方式三：用 SSH

本机目前没有 SSH 密钥，需要先生成并把公钥加到 GitHub：

```powershell
ssh-keygen -t ed25519 -C "your-email@example.com"
Get-Content $env:USERPROFILE\.ssh\id_ed25519.pub
```

把公钥内容粘贴到 <https://github.com/settings/keys>，然后：

```powershell
Set-Location D:\Alysia
git remote add origin git@github.com:<你的用户名>/alysia.git
git push -u origin main
```

## 推送前请确认

- 分支为 `main`，最新提交是开源准备提交。
- `git ls-files | Measure-Object -Line` 约为 1051，仓库体积约 10 MB。
- `models/`、`workspace/`、`tools/bilibili-mcp/bili_credential.json`、`audit/*.jsonl` 均未入库。
- 提交身份目前是仓库级占位值，可按需修改：

```powershell
git config user.name "你的名字"
git config user.email "你的邮箱"
git commit --amend --reset-author --no-edit
```

## 建议的仓库设置（公开后）

- 开启 **Private vulnerability reporting**，对应 `SECURITY.md` 的报告渠道。
- Description 建议：`Alysia — 面向 B 站的自主创作者系统：可恢复的内容流水线，带人工审核与发布闸门`。
- Topics 建议：`ai-agent`、`bilibili`、`video-generation`、`python`、`remotion`。
- 若仓库包含演示图片，可在 README 顶部加一张截图，但不要上传生成视频与大体积中间文件。
