# Grok 跑步循环接入制作单

## 范围与决定

本轮把用户提供的 `akita-run-grok.zip` 处理结果接入秋田犬生产版的 `running` 状态。它不是 3D 模型，而是已抠图、稳定和裁切好的 20 张透明 PNG；运行时仍使用项目现有的 PNG 帧播放链路。

素材报告给出的周期是 24 fps 下连续 20 帧，约 834 ms。生产版采用素材原始的 `42,42,41 ms` 重复时序，而不是强行改成旧版 640 ms：这样保留生成视频的自然节奏，后续如果设备录屏证明过慢，再单独做有证据的重定时版本。

## 来源和处理证据

- 输入归档：`akita-run-grok.zip`，SHA-256 见 `delivery.json`。
- 原视频帧：73–92，共 20 帧；无插帧、无混合帧。
- 处理记录：`source/process.py`、`source/matte.py`、`source/pet-clips-running.json`。
- 候选时序：`source/frames.json`，可用 `tools/preview_animation.py --candidate` 重放。
- 视觉复核：`review/contact.png` 和 `review/display-192px.png`。后者包含浅色/深色背景下的实际 192 px 审查尺寸。

## 视觉复核结论

20 帧首尾动作可连续解释；头部保持原地跑的构图，四肢在小尺寸下仍可辨认，透明边缘在浅色和深色背景上均干净。第 15、16 帧的眯眼/眨眼保留为自然的小表情；毛发纹理存在生成模型带来的轻微帧间闪动，192 px 检查图和 64 dp 目标尺寸下不明显，但不把它记录为已经消除。

目前没有正面、纯侧面、背面或俯视补图；这些视图属于未来 3D 模型建模资料，不是本轮 2D 跑步循环接入的前置条件。

## 高清重绘试作（未接入）

为验证“直接把当前低分辨率帧重新绘制成统一高清图”这条路线，使用内置 imagegen 以当前 `running/00` 作为动作参考，以已有高清跑姿和 Idle 高清图作为角色风格参考，生成了 [`review/redraw-prototype-running-00.png`](review/redraw-prototype-running-00.png)。结果为 1254×1254 RGBA 透明图：边缘和毛发细节比当前帧更干净，但前后腿姿势被模型改成了收腿/悬空姿势，不能作为 Running/00 直接替换。

这次试作说明：单张重绘适合验证高清风格，不适合直接重建连续奔跑。完整重绘必须以整段动作序列、统一角色母版或 3D/骨骼渲染为约束；当前候选只作视觉参考，不进入 `pet.json` 或生产帧。

## 生产接入

- `codex_pet/assets/akita/frames/running/00.png`–`19.png` 替换为本轮 20 张帧。
- `codex_pet/assets/akita/running.png` 与新的物理 `running/00.png` 保持逐字节一致。
- `pet.json` 的 `running` 按物理顺序 `00`–`19` 播放，循环时长为 834 ms；`running_to_ready`、其他状态和 Ready 休息循环保持不变。
- `current-running.json` 已更新为新帧的来源哈希、时长、显示审计标记。标记只用于确认采样点落在可见绘画上，不代表犬类步态或接触力学认证。
- 旧版 10 帧、640 ms 记录仍保留在历史制作单和基线文件中，作为可追溯的前一版本，不再作为当前播放表。

## 设备验证状态

已通过 `bash ./install.sh` 部署到 Termux 私有 release，并用 `codex-pet status`、`codex-pet test` 做了运行时冒烟：新 pack 被加载为 `2026-10-grok-run`，20 帧和 834 ms 时序可读，状态依次经过 idle、running、needs_input、ready、blocked 后回到 idle，Termux:GUI overlay ready。完整记录见 [device-check.json](device-check.json)。

这仍不能代替人工观察 Android 原生播放的体感。实际 64 dp 下的速度、15/16 帧眨眼、首尾接缝、Running→Ready 任意相位中断，以及毛发闪动是否可见，仍需在设备屏幕上观察；触摸代码未改，本轮不扩大触摸验收范围。
