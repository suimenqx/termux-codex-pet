# Codex Pet for Termux 使用指南

[English](README.md)

Codex Pet 是一个悬浮在 Android 应用上方的小机器人，用来显示 Codex CLI 的工作状态。Codex hooks 通过本机 Unix socket 将事件发送给单个 Termux:GUI daemon。它不轮询 Codex，也不需要独立 APK 或 Web 服务。只有在悬浮窗不可用且发生“需输入”或“就绪”事件时，才会尝试发送 Android 通知。

## 安装与首次验证

1. 安装签名来源兼容的 Termux 和 Termux:GUI。
2. 在 Android 中开启 **Termux:GUI → Advanced → Display over other apps**（显示在其他应用上层）。
3. 在 Termux 中运行：

   ```sh
   git clone https://github.com/suimenqx/termux-codex-pet.git ~/codex-pet
   cd ~/codex-pet
   ./install.sh
   codex-pet status
   codex-pet test
   ```

安装脚本会按需安装 Python 和官方 `termuxgui` Python binding，创建命令入口，安全合并 Codex hooks，启动 daemon 并完成一次 IPC 冒烟测试。它会备份修改过的 Codex 配置，不覆盖无关设置。`codex-pet test` 会演示 Idle 和官方四种活动状态；Ready 会一直显示，直到用户确认。

**让真实 Codex 会话驱动 Pet：**安装后重启 Codex。在本项目测试使用的 Codex CLI 0.156.1 中，进入新会话后运行 `/hooks`，如提示审核，则信任 Codex Pet 的 hook 命令。若现有 `~/.codex/config.toml` 已使用内联 hooks，安装器会继续写入该文件；否则使用 `~/.codex/hooks.json`。安装输出会说明采用的方式，也可以查看 `~/.config/codex-pet/install.json` 中的 `hooks_mode`。这些 hooks 只观察事件，不会替你批准或拒绝 Codex 操作。

提交 prompt 后显示 **Running**；Codex 请求工具权限时显示 **Needs input**；工具执行并返回后恢复 **Running**；当前回合停止后显示 **Ready**，直到用户点击活动卡片或机器人确认。

## 日常操作

```sh
codex-pet start       # 按需启动；重复执行不会创建第二份 daemon
codex-pet stop        # 关闭悬浮窗与 daemon
codex-pet restart     # 重新加载代码并连接 Termux:GUI
codex-pet status      # 查看 daemon、GUI、状态、项目及会话数
codex-pet test        # 依次演示官方 Pet 活动状态
```

点击机器人可展开或收起活动气泡，气泡变化时机器人也会保持原位、不再左右闪跳。机器人会随 Idle、Running、Needs input、Ready 和 Blocked 切换表情。卡片宽度为 116dp，尖角为 5dp；文字向机器人一侧对齐，让项目、彩色状态和简短摘要更像 Pet 正在贴近告诉你。卡片文字略微放大后，状态和摘要更容易扫读。靠近屏幕左边时，气泡会换到右侧。Needs input 和 Ready 时会自动展开；点击 Ready 活动卡片或机器人会确认该活动，其他手动触摸会让卡片保持显示，直到再次点击机器人。在机器人中心 27dp 半径范围内均可开始拖动，按住的点会持续跟随手指，机器人不会突然跳位；四角仍可点击，但不会误触发拖动。位置保存在 `~/.config/codex-pet/config.json`，重启后会恢复。收起时机器人宽约 64dp。

| 状态 | 显示内容 | 触发与持续时间 |
| --- | --- | --- |
| Idle | 安静待机 | 会话开始、结束或当前回合被中断 |
| Running | 低频动画；卡片显示已运行时间 | 提交 prompt，或 Codex 在工具调用后继续 |
| Needs input | 醒目提醒；卡片自动展开 | Codex 请求工具权限 |
| Ready | 完成反馈；卡片自动展开 | 当前回合停止；点击活动卡片确认后清除 |
| Blocked | 错误表情 | 仅演示状态；hooks 不会收到明确的回合失败事件 |

多会话状态优先级遵循官方 Pet 的公开顺序：Needs input、Blocked、Ready、Running。有两个及以上运行会话时，机器人会显示数量。

**状态准确性：**官方公开了这四种活动状态及其优先级，但当前 Termux 版本通过 hooks 接收事件，拿不到桌面端相同的内部状态流。hooks 会报告 prompt、工具权限、工具、停止、中断和会话生命周期事件，但不会报告回合最终是成功还是失败、活动是否未读，也不会报告 Codex 是否在文本中向用户提问。权限请求若被拒绝且没有工具结果，Needs input 可能会保持到下一条 hook 事件。因此本项目不会根据看起来像错误的工具结果猜测 Blocked；Ready 会保持到用户点击可见的摘要作为确认。其他 Stop hook 可能要求 Codex 继续执行，Pet 会在收到下一条 prompt 事件后切回 Running，中间可能短暂显示 Ready。若要获得明确的失败回合事件，所有 CLI 会话都需要使用同一个 App Server 事件流；当前 hooks 版本尚未接入。

## 更新

命令入口指向克隆目录。拉取新代码后，需要重启已经运行的 daemon：

```sh
cd ~/codex-pet
git pull --ff-only origin main
./install.sh
codex-pet restart
codex-pet status
```

## Hooks 与自动恢复

安装器注册 `SessionStart`、`UserPromptSubmit`、`PermissionRequest`、`PostToolUse`、`Stop`、`Interrupt` 和 `SessionEnd`。它们都调用 `codex-pet-event`，并将 Codex JSON 传给它。即使 Pet 出错，hook helper 也会正常退出，不阻断 Codex。Android 回收 daemon 后，下一个 Codex 事件会重新启动它，无需 Termux:Boot。`SessionEnd` 会移除对应会话。运行时 socket 和轮转日志位于 `~/.cache/codex-pet/`。

## 故障排查

- **Pet 消失：**先运行 `codex-pet status`；如果已停止，运行 `codex-pet start`。下一个 Codex 事件也会尝试自动拉起 daemon。
- **显示 `GUI=unavailable`：**检查 Termux:GUI 的悬浮窗权限及两个 App 的签名来源，然后运行 `codex-pet restart`。仍失败时查看 `~/.cache/codex-pet/pet.log`。
- **`codex-pet test` 正常，但提交 prompt 后没反应：**重启 Codex，运行 `/hooks` 并信任 Pet hooks。根据 `~/.config/codex-pet/install.json` 中的 `hooks_mode` 检查对应配置文件。`codex features list` 应显示 `hooks` 已启用。
- **更新后还是旧界面：**运行 `codex-pet restart`；正在运行的 daemon 不会自动重载 Python 文件。
- **点击或拖动不稳定：**用 `codex-pet status` 确认 `GUI=ready`，再运行 `codex-pet restart`。从机器人中心区域开始拖动；触摸活动卡片只会让卡片保持展开。

## 卸载

```sh
cd ~/codex-pet
./uninstall.sh
```

卸载脚本会停止 daemon、移除 Pet 命令入口和运行时文件，并且只移除它自己添加的 hooks。Python 依赖、Codex 配置备份和保存的位置会保留，方便以后重新安装。

## 许可证

MIT。见 [LICENSE](LICENSE)。
