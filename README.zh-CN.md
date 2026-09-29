# Codex Pet for Termux 使用指南

[English](README.md)

Codex Pet 是一个悬浮在 Android 应用上方的小机器人，用来显示 Codex CLI 的工作状态。Codex hooks 通过本机 Unix socket 将事件发送给单个 Termux:GUI daemon。它不轮询 Codex，也不需要独立 APK 或 Web 服务。只有在悬浮窗不可用且发生审批或完成事件时，才会尝试发送 Android 通知。

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

安装脚本会按需安装 Python 和官方 `termuxgui` Python binding，创建命令入口，安全合并 Codex hooks，启动 daemon 并完成一次 IPC 冒烟测试。它会备份修改过的 Codex 配置，不覆盖无关设置。`codex-pet test` 约需 23 秒，会依次展示六种状态。

**让真实 Codex 会话驱动 Pet：**安装后重启 Codex。在本项目测试使用的 Codex CLI 0.156.1 中，进入新会话后运行 `/hooks`，如提示审核，则信任 Codex Pet 的 hook 命令。若现有 `~/.codex/config.toml` 已使用内联 hooks，安装器会继续写入该文件；否则使用 `~/.codex/hooks.json`。安装输出会说明采用的方式，也可以查看 `~/.config/codex-pet/install.json` 中的 `hooks_mode`。这些 hooks 只观察事件，不会替你批准或拒绝 Codex 操作。

提交一个 Codex prompt 后，Pet 应显示 **Working**；Codex 等待审批时显示 **Needs approval**；任务结束后短暂显示 **Done**，再恢复待机。

## 日常操作

```sh
codex-pet start       # 按需启动；重复执行不会创建第二份 daemon
codex-pet stop        # 关闭悬浮窗与 daemon
codex-pet restart     # 重新加载代码并连接 Termux:GUI
codex-pet status      # 查看 daemon、GUI、状态、项目及会话数
codex-pet test        # 依次演示全部六种状态
```

点击机器人可展开或收起对话气泡，气泡变化时机器人也会保持原位、不再左右闪跳。机器人会随当前状态切换表情：待机时微笑，工作时专注，审批、完成、中断和错误也各有不同神态。卡片宽度为 116dp，尖角为 5dp；文字向机器人一侧对齐，让项目、彩色状态和简短摘要更像 Pet 正在贴近告诉你。卡片文字略微放大后，状态和摘要更容易扫读。靠近屏幕左边时，气泡会换到右侧。审批和完成时会自动展开；触碰气泡会让它保持显示，直到再次点击机器人。在机器人中心 27dp 半径范围内均可开始拖动，按住的点会持续跟随手指，机器人不会突然跳位；四角仍可点击，但不会误触发拖动。位置保存在 `~/.config/codex-pet/config.json`，重启后会恢复。收起时机器人宽约 64dp。

| 状态 | 显示内容 | 触发与持续时间 |
| --- | --- | --- |
| Idle | 安静待机 | 会话开始、结束或短暂状态到期 |
| Working | 低频动画；卡片显示已工作时间 | 提交 prompt 后 |
| Needs approval | 醒目提醒；卡片自动展开 | Codex 请求权限；保持到后续事件 |
| Done | 完成反馈；卡片自动展开 | Codex 结束当前回合；约 6 秒后待机 |
| Interrupted | 暂停反馈 | 当前回合中断；约 4 秒后待机 |
| Error | 错误图标 | 可通过 `codex-pet test` 演示；hooks 不会猜测错误 |

同时运行多个 Codex 会话时，审批优先于工作状态；有两个及以上工作会话时，机器人会显示数量。

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

安装器注册 `SessionStart`、`UserPromptSubmit`、`PermissionRequest`、`Stop`、`Interrupt` 和 `SessionEnd`。它们都调用 `codex-pet-event`，并将 Codex JSON 传给它。即使 Pet 出错，hook helper 也会正常退出，不阻断 Codex。Android 回收 daemon 后，下一个 Codex 事件会重新启动它，无需 Termux:Boot。`SessionEnd` 会移除对应会话。运行时 socket 和轮转日志位于 `~/.cache/codex-pet/`。

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
