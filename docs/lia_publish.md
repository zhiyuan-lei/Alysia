# 莉娅期节目生产与投稿流水线

入口：`scripts/lia_publish.py`

一条命令从旁白稿走到 B站 已提交，中间每一步都能单独重跑。

## 快速开始

```powershell
# 1) 新建期目录，只放一份旁白（一行一段）
# 2) 生成 scenes.json / episode.json 草稿，人工校对标题、卡片、标签
python scripts/lia_publish.py scaffold workspace/lia_batch_20261028/ep12_xxx

# 3) 出画面、配音、成片、封面（不发布）
python scripts/lia_publish.py run workspace/lia_batch_20261028/ep12_xxx --steps frames,tts,build,cover

# 4) 只验证浏览器与登录，不上传任何文件
python scripts/lia_publish.py publish workspace/lia_batch_20261028/ep12_xxx --check

# 5) 上传并填好表，停在「待提交」（安全默认）
python scripts/lia_publish.py publish workspace/lia_batch_20261028/ep12_xxx --dry-run

# 6) 真正发布
python scripts/lia_publish.py publish workspace/lia_batch_20261028/ep12_xxx --submit
```

不加 `--submit` 的任何调用都不会对外发布。

## 期目录结构

| 文件 | 必需 | 说明 |
| --- | --- | --- |
| `narration.txt` | 是 | 旁白，一行一段，一行对应一个画面 |
| `scenes.json` | 否 | 每段的 `title` / `card` / `pose`；缺失时按旁白自动推导 |
| `episode.json` | 否 | `title` `desc` `tags` `category` `declaration` `cover` |
| `assets/presenter_*.png` | 否 | 立绘；缺失时回退到 ep10 的共享素材 |
| `frames/` `audio/` `segs/` | 产出 | 中间产物，可删可重建 |
| `film.mp4` `cover.jpg` | 产出 | 成片与封面 |
| `publish_receipt.json` | 产出 | 投稿回执（账号、标题、时长、状态） |

### scenes.json 的 card 写法

`card` 是 `[样式, 参数1, 参数2, ...]`：

| 样式 | 参数 | 例子 |
| --- | --- | --- |
| `big` | 大数字, 说明 | `["big", "57", "今天六条视频加起来"]` |
| `q` | 一句话 | `["q", "有人记住你了吗"]` |
| `bullets` | 条目数组 | `["bullets", ["耳朵会竖", "尾巴会翘"]]` |
| `list` | 条目数组, 小标题 | `["list", ["讲得急", "讲得重"], "今天发的六条"]` |
| `bars` | [[名称, 数值], ...] | `["bars", [["今天", 57], ["昨天", 13]]]` |
| `grid` | 标签数组（三列） | `["grid", ["第1条", "第2条"]]` |

`pose` 取值：`explain think worry proud confused determined surprise relieved tired pout point reveal wave celebrate`。

## 每一步做什么

1. **frames** — PIL 生成 1920×1080 画面，版式为「左上角集数 / 大标题 / 中间虚构界面卡片 / 右侧莉娅立绘 / 底部字幕 / 双角标」。
2. **tts** — edge-tts，音色 `zh-CN-XiaoyiNeural`，语速 +8%，逐段出 mp3（段落时长决定画面停留长度）。
3. **build** — ffmpeg 每段加缓慢推镜（zoom 1.0→1.085），拼接后旁白按 `loudnorm I=-16` 归一，叠 ep10 配乐（音量 11%，首尾淡入淡出）。
4. **cover** — 1920×1080，导出 **jpg**（B站 封面不接受 png）。
5. **publish** — 启动带 CDP 的 Edge（独立 profile，登录态持久化），上传、填标题/简介/标签、选分区、选创作声明、传封面、提交、去稿件管理页核实。

已有产物会被跳过；要重做加 `--force`。

## 投稿环节的几个真实坑

- **封面是必填的**，B站 不会拿视频首帧兜底，不传就卡在「请先上传封面」。
- 封面的文件输入藏在「封面制作」弹窗里（`accept="image/png, image/jpeg"`）；页面上另外几个 file input 全是视频/字幕/弹幕用的，塞图进去会报「不支持 jpg 格式的文件」。
- 点「完成」还会弹一层「检测到个人空间封面（16:9）未修改，是否同步」——不点「确认同步」封面等于没设。
- 分区是两级：先点大类 tab（如「动画」），列表项不是标准 `li`，要在下拉容器里按层级找。
- 提交成功的判断：页面顶部出现绿色「上传成功」并重置为空表单，或跳转到 `upload-manager`。成功后会去稿件管理页核对标题。
- Edge 默认 profile **禁止**开远程调试，所以必须用独立的 `user-data-dir`；首次用新 profile 要扫码一次。

## 登录态

存在 `workspace/lia_batch_20261028/.publish_profile/`。失效时 `--check` 会提示，扫码后自动继续。

## 状态判断

投稿后稿件进入「审核中」，此时没有 BV 号，`publish_receipt.json` 里 `bvid` 为 `null`。审核通过后再补。
