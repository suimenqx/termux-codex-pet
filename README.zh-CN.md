# Codex Pet for Termux 使用指南

[English](README.md)

Codex Pet 是一个悬浮在 Android 应用上方的小伙伴形象，默认是一只秋田犬，用来显示 Codex CLI 的工作状态。Codex hooks 通过本机 Unix socket 将事件发送给单个 Termux:GUI daemon。它不轮询 Codex，也不需要独立 APK 或 Web 服务。只有在悬浮窗不可用且发生“需输入”或“就绪”事件时，才会尝试发送 Android 通知。

## 安装与首次验证

1. 安装签名来源兼容的 Termux 和 Termux:GUI。
2. 在 Android 中开启 **Termux:GUI → Advanced → Display over other apps**（显示在其他应用上层）。
3. 在 Termux 中运行：

   ```sh
   pkg update
   pkg install -y git
   git clone https://github.com/suimenqx/termux-codex-pet.git ~/codex-pet
   cd ~/codex-pet
   bash ./install.sh
   codex-pet status
   codex-pet test
   ```

安装脚本会按需安装 Python、libpng 和 `termuxgui` Python binding，将运行代码复制到 `~/.local/share/codex-pet/` 的独立版本目录，创建固定命令入口，安全合并 Codex hooks，重启 daemon 并完成一次 IPC 冒烟测试。若已检查的安装步骤失败，它会恢复原先的运行版本链接、命令入口和 hooks 配置；此前 daemon 正在运行时，也会尝试恢复它。源码仓库之后可以移动，不会改变已安装 Pet 的运行路径。脚本会备份修改过的 Codex 配置，不覆盖无关设置；不会安装 Termux:GUI Android 应用，也无法替你开启悬浮窗权限。`codex-pet test` 会演示 Idle 和官方四种活动状态；Ready 会以图标形式保持显示，直到后续事件改变该会话状态或会话结束。预检、依赖缺失时的处理、预期输出和需要用户在 Android 上操作的情况，见[详细安装与依赖排查指南](docs/installation.zh-CN.md)。

**让真实 Codex 会话驱动 Pet：**安装后重启 Codex。在新会话中打开 `/hooks` 检查 Pet 命令；若 Codex 提示信任，请先查看再决定。若现有 `~/.codex/config.toml` 已使用内联 hooks，安装器会继续写入该文件；否则使用 `~/.codex/hooks.json`。安装输出会说明采用的方式，也可以查看 `~/.config/codex-pet/install.json` 中的 `hooks_mode`。这些 hooks 只观察事件，不会替你批准或拒绝 Codex 操作。

提交 prompt 后显示 **Running**；Codex 请求工具权限时显示 **Needs input**；工具执行并返回后恢复 **Running**；当前回合停止后显示 **Ready**，直到后续事件改变该会话状态或会话结束。

## 日常操作

```sh
codex-pet start       # 按需启动；重复执行不会创建第二份 daemon
codex-pet stop        # 关闭悬浮窗与 daemon
codex-pet restart     # 重启当前安装版本并重新连接 Termux:GUI
codex-pet status      # 查看 daemon、GUI、状态、形象、项目及会话数
codex-pet test        # 依次演示官方 Pet 活动状态
codex-pet pet list    # 查看支持的形象和当前选择
codex-pet pet use akita
codex-pet pet use robot
```

Pet 是一个约 64dp 的悬浮形象。默认秋田犬采用透明的 256 × 256 高清 PNG 帧：奶油白圆脸、明亮橘红额顶和浅色额心、短立耳、张嘴露舌的笑脸，以及紧凑的身体。待机时缓慢呼吸、偶尔眨眼，并以更明显但舒缓的幅度摆尾；运行时以 8 个连续姿势表现不对称奔跑，两只后脚错开蹬地，近侧和远侧前爪先后前伸、着地与回收；需要输入时轻轻挥爪；就绪时先轻轻蹲身蓄力，再开心跃起一次，之后缓慢呼吸、慢慢眨眼并轻轻摆尾；受阻时短暂歪头，然后停在思考姿势。经典机器人仍可切换，并保留原有动画。运行 `codex-pet pet list` 查看已支持形象和当前选择，用 `codex-pet pet use <id>` 切换到列表中的任一形象，例如 `codex-pet pet use robot`。选择与悬浮位置一起保存在 `~/.config/codex-pet/config.json`；daemon 正在运行时会立即切换。点击没有操作；如需移动，从 Pet 图标的任意位置拖动即可，移动约 6dp 后就会跟随手指。

| 状态 | 显示内容 | 触发与持续时间 |
| --- | --- | --- |
| Idle | 缓慢呼吸、偶尔眨眼，并舒缓地摆尾 | 会话开始、结束或当前回合被中断 |
| Running | 8 姿势循环奔跑，前后两对脚掌错相运动；多个活动会话时显示数量徽标 | 提交 prompt，或 Codex 在工具调用后继续 |
| Needs input | 轻轻挥爪提醒 | Codex 请求工具权限 |
| Ready | 进入时轻蹲蓄力并开心跃起一次，之后循环呼吸、慢慢眨眼并轻轻摆尾 | 当前回合停止；后续事件改变状态或会话结束后清除 |
| Blocked | 短暂歪头，然后停在思考姿势 | 仅演示状态；hooks 不会收到明确的回合失败事件 |

多会话状态优先级遵循官方 Pet 的公开顺序：Needs input、Blocked、Ready、Running。有两个及以上运行会话时，形象会显示数量。

**状态准确性：**官方公开了这四种活动状态及其优先级，但当前 Termux 版本通过 hooks 接收事件，拿不到桌面端相同的内部状态流。hooks 会报告 prompt、工具权限、工具、停止、中断和会话生命周期事件，但不会报告回合最终是成功还是失败、活动是否未读，也不会报告 Codex 是否在文本中向用户提问。权限请求若被拒绝且没有工具结果，Needs input 可能会保持到下一条 hook 事件。因此本项目不会根据看起来像错误的工具结果猜测 Blocked。Ready 会以图标形式保持显示，直到后续事件改变该会话状态或会话结束。其他 Stop hook 可能要求 Codex 继续执行，Pet 会在收到下一条 prompt 事件后切回 Running，中间可能短暂显示 Ready。若要获得明确的失败回合事件，所有 CLI 会话都需要使用同一个 App Server 事件流；当前 hooks 版本尚未接入。

## 更新

运行副本与源码仓库相互独立。拉取新代码后，重新运行安装器即可部署新版本并重启 daemon：

```sh
cd ~/codex-pet
git pull --ff-only origin main
bash ./install.sh
codex-pet status
```

## Hooks 与自动恢复

安装器注册 `SessionStart`、`UserPromptSubmit`、`PermissionRequest`、`PostToolUse`、`Stop`、`Interrupt` 和 `SessionEnd`。它们都调用 `codex-pet-event`，并将 Codex JSON 传给它。即使 Pet 出错，hook helper 也会正常退出，不阻断 Codex。Android 回收 daemon 后，下一个 Codex 事件会重新启动它，无需 Termux:Boot。`SessionEnd` 会移除对应会话。运行时 socket 和轮转日志位于 `~/.cache/codex-pet/`。

## 故障排查

- **Pet 消失：**先运行 `codex-pet status`；如果已停止，运行 `codex-pet start`。下一个 Codex 事件也会尝试自动拉起 daemon。
- **显示 `GUI=unavailable`：**检查 Termux:GUI 的悬浮窗权限及两个 App 的签名来源，然后运行 `codex-pet restart`。仍失败时查看 `~/.cache/codex-pet/pet.log`。
- **`codex-pet test` 正常，但提交 prompt 后没反应：**重启 Codex，运行 `/hooks` 并信任 Pet hooks。根据 `~/.config/codex-pet/install.json` 中的 `hooks_mode` 检查对应配置文件。`codex features list` 应显示 `hooks` 已启用。
- **更新源码后还是旧界面：**在源码仓库中运行 `bash ./install.sh`，部署新版本并重启 daemon。单独运行 `codex-pet restart` 只会重启当前已安装版本。
- **秋田犬边缘出现彩色噪点：**更新源码后运行 `bash ./install.sh`，部署 PNG 渲染修复并重启 daemon。旧安装版本仍会使用原来的共享缓冲区渲染路径，直到重新部署。
- **拖动不稳定：**用 `codex-pet status` 确认 `GUI=ready`，再运行 `codex-pet restart`。从 Pet 图标任意位置开始拖动，移动约 6dp 即可。

## 卸载

```sh
cd ~/codex-pet
bash ./uninstall.sh
```

卸载脚本会停止 daemon、移除 Pet 命令入口和运行时文件，并且只移除它自己添加的 hooks。Python 依赖、Codex 配置备份以及保存的位置和形象选择会保留，方便以后重新安装。

## 许可证

MIT。见 [LICENSE](LICENSE)。
