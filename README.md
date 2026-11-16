# 视频封面设计师

一个可用于 Codex、WorkBuddy 等兼容宿主的视频封面设计 skill：从用户的视频和已有要求出发，理解内容、推荐方向、展示视觉小样，再按反馈修改并交付图片。适用于口播、教程、产品展示、故事和生活记录等视频。

默认面向抖音和小红书，支持按任务调整平台、比例和风格。它提供设计流程与本地辅助脚本；图像生成、编辑和内容理解使用当前宿主实际可用的能力。

## 工作流程

1. 理解视频主题、看点和可用画面，说明实际读取范围。
2. 保留已有要求，只补问影响设计的关键缺口。
3. 推荐适合的内容角度，制作 2–3 张有明显区别的视觉小样。
4. 根据用户选择修改；局部调整保留已认可的部分。
5. 检查文字、人物、构图和输出规格，交付认可图片。已经认可且达到交付质量的小样可直接定稿。

“先理解”或“先讨论”等阶段限制优先于完整流程。不同视频按内容设计，不固定使用某种人物、色彩或构图。

需要新场景、动作或视觉隐喻时，实际调用宿主的生成/编辑能力，并输入所需人物参考；精确中文排版可以后做。简洁实拍按用户选择制作。展示前逐图核对承诺的视觉内容，多种小样须有实质构图或场景差别，不能只给同一截图换标题。

## 安装与调用

下载仓库，将包含 `SKILL.md` 的整个文件夹命名为 `video-cover-designer`，放入 Codex 的个人 skills 目录：默认是 `~/.codex/skills/`；自定义了 `CODEX_HOME` 时使用其下的 `skills/` 目录。

保留 `agents/`、`references/` 和 `scripts/` 的相对位置。重新打开 Codex 或新建聊天，使其发现新 skill。随后调用：

```text
使用 $video-cover-designer 分析我提供的视频，先理解内容并推荐封面方向。
```

也可同时说明平台、标题、人物是否出现、参考风格和本次只需完成的阶段。素材与输出建议保存在单独的项目目录。

WorkBuddy 请通过其 skill 导入入口安装完整文件夹，并在新任务中重新调用。宿主适配说明见 [references/workbuddy.md](references/workbuddy.md)：先发现当前 `ImageGen` 合同，再实际调用；参数、参考图输入和额外积分提示以当次工具为准。Skill 提供流程，不自带生图引擎或积分；缺少所需能力时会说明限制。此适配已做情景验证，尚未完成 WorkBuddy 新版真实付费生图的端到端验证。

## 本地脚本依赖

- Python 3，建议 3.10 或更新版本。
- Pillow：`python -m pip install Pillow`。
- `ffmpeg` 和 `ffprobe`：安装后使两个命令可通过 PATH 调用。
- 完整视觉小样需要宿主提供可用的图像生成或编辑工具。

以下命令从本仓库根目录运行；把示例相对路径换成实际项目路径。输出目录须为新目录或空目录。

### 检查视频

```text
python scripts/inspect_video.py "../my-project/video.mp4" --out "../my-project/analysis-01" --samples 8 --audio
python scripts/inspect_video.py "../my-project/video.mp4" --out "../my-project/analysis-02" --at 0 12.5 30 --max-edge 1080
```

输出元数据、抽样帧、时间点清单及联系表；`--audio` 在有音轨时提取完整单声道 16 kHz WAV。该脚本不调用外部模型，不转写或总结视频；抽样不能替代完整内容理解。

### 原样交付认可图片

```text
python scripts/finalize_cover.py --out "../my-project/final-01" --cover "douyin=../my-project/approved.png" --cover "xiaohongshu=../my-project/approved.png"
```

脚本原样复制认可图、校验 SHA256，并生成交付清单和 ZIP。两平台若使用不同适配图，分别指定对应文件；同图分别命名不代表重新排版，也不等于已在发布入口验证。

流程说明见 [SKILL.md](SKILL.md)，分支与读取方式见 `references/`。仓库中的试跑案例仅说明一次实际流程，不作为其他视频的固定设计模板。
