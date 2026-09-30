# 安装与依赖排查指南

本指南用于在 Android 上的 Termux 安装 Codex Pet，也可供 agent 按步骤执行。Shell 安装命令要在 Termux 中运行；安装 Android 应用、开启悬浮窗权限，以及处理 Codex 的 hook 信任提示时，需要用户参与。

## 依赖清单

| 依赖 | 用途 | 安装方式 |
| --- | --- | --- |
| Android 上的 Termux | 运行 Pet daemon 和命令行 | 安装 Termux 应用，并在它的终端内执行本指南；该环境应提供 `pkg` 和 `PREFIX`。 |
| Termux:GUI Android 应用 | 创建原生悬浮窗 | 需单独安装；其签名来源必须与已安装的 Termux 兼容。`install.sh` 不安装 APK。 |
| 悬浮窗权限 | 让 Pet 显示在其他应用上层 | 在 Android 中打开 **Termux:GUI → Advanced → Display over other apps** 并开启。安装脚本无法替用户授权。 |
| `git` 命令 | 克隆仓库 | 克隆前运行 `pkg install -y git`；仓库下载前安装脚本无法安装 Git。 |
| Python、libpng、`termuxgui` Python binding | 绘制素材并连接 Termux:GUI | 缺少时由 `install.sh` 自动安装。 |
| Codex CLI | 让真实 Codex 会话驱动 Pet 状态 | 安装和演示 Pet 不需要；要接收真实会话 hook 才需要。若未安装，请单独安装 Codex。 |
| Termux:API 应用和包 | 悬浮窗不可用时的可选通知 | 悬浮窗不依赖它。只有需要通知回退时才安装签名兼容的 Android 应用，并运行 `pkg install termux-api`。 |

缺少文件或依赖时，需要连接 GitHub、Termux 软件源和 PyPI。无需 root、`termux-setup-storage`、Termux:Boot 或单独的 Pet APK。

## 从新目录安装

先从签名兼容的软件源安装 Termux 和 Termux:GUI，再在 Android 设置中开启悬浮窗权限。随后在 Termux 应用内运行：

```sh
pkg update
pkg install -y git
git clone https://github.com/suimenqx/termux-codex-pet.git ~/codex-pet
cd ~/codex-pet
./install.sh
codex-pet status
codex-pet test
```

如果 `~/codex-pet` 已存在，先检查：

```sh
git -C ~/codex-pet status --short --branch
```

保持在 `main`；只有本地没有未处理的修改时才运行：

```sh
git -C ~/codex-pet pull --ff-only origin main
```

已安装的命令是指向此目录的符号链接，安装期间不要移动或删除仓库。

`install.sh` 会通过 `pkg` 安装缺少的 Python 和 `libpng`，再通过 `python -m pip` 安装 `termuxgui` Python binding。脚本会创建命令入口、安全合并 Codex hooks、启动 daemon 并发送 IPC 冒烟事件。修改 Codex 配置前会备份原文件。它不会安装 Termux:GUI Android 应用、开启 Android 权限、安装 Codex CLI，也不会替用户信任 hook。

如果 `~/.codex/config.toml` 已有内联 hook 事件组，安装器会更新该文件；否则会把 Pet 命令合并到 `~/.codex/hooks.json`。只有 `hooks.state` 元数据并不会触发 inline 模式。已有用户 hooks 会保留，修改过的配置会备份，使用的模式会记录在 `~/.config/codex-pet/install.json`。`import termuxgui` 只验证 Python binding；还需通过 `codex-pet status` 确认设备侧 Android 应用和权限正常，即显示 `GUI=ready`。

预期结果：

- `codex-pet status` 显示 `GUI=ready` 和 `pet=akita`。没有活动 Codex 会话时，`state=idle` 是正常结果。
- `codex-pet test` 依次演示 Idle、Running、Needs input、Ready 和 Blocked，最后移除临时测试会话；大约需要 18 秒。没有其他活动会话时 Pet 会回到 Idle。若要逐一目视检查状态，请先结束或隔离其他会话。
- 安装器会输出 `Codex hooks installed (inline)` 或 `Codex hooks installed (json)`。如果改动了已有 hooks 文件，也会打印备份路径。
- 运行日志在 `~/.cache/codex-pet/pet.log`。

## 依赖检查与修复

在 Termux 中运行以下命令，确认具体缺少哪项依赖：

```sh
command -v pkg
command -v git
printf 'PREFIX=%s\n' "${PREFIX:-unset}"
python -c 'import ctypes; ctypes.CDLL("libpng16.so"); print("libpng OK")'
python -c 'import termuxgui; print(termuxgui.__file__)'
```

| 现象 | 原因与处理 |
| --- | --- |
| 找不到 `pkg` 或 `PREFIX=unset` | 命令不在 Termux 应用内运行，或 Termux 环境异常。不要从桌面 Linux、macOS 或普通 Android shell 运行 `install.sh`；打开 Termux 后重试检查。 |
| 克隆前提示 `git: command not found` | 运行 `pkg install -y git`。若软件包索引过期，先运行 `pkg update`。 |
| `Unable to locate package` 或软件源下载错误 | 保留完整的 `pkg` 输出，先检查网络并运行 `pkg update`。若当前镜像不可用，通过 Termux 软件源选择器切换后重试。 |
| libpng 检查报 `libpng16.so` 的 `OSError` | 运行 `pkg install -y libpng`，然后重复原检查。这是原生图像解码依赖。 |
| `No module named termuxgui` | 运行 `python -m pip install termuxgui`，再重复 import 检查。如果 pip 失败，保留完整错误并检查 PyPI/网络；不要换成其他 binding 包。 |
| `Codex Pet did not start` 或 `GUI=unavailable` | 检查 Termux:GUI Android 应用是否已安装、签名来源是否兼容，以及 **Display over other apps** 是否开启。然后运行 `codex-pet restart`、`codex-pet status` 并查看 `~/.cache/codex-pet/pet.log`。 |
| `Cannot install over directory` | 命令链接位置上存在目录。先检查目录及内部文件，再决定备份或换安装位置；安装器会拒绝覆盖目录。 |
| `hooks.json has an unexpected shape` 或 TOML 解析错误 | 不要直接覆盖 Codex 配置。保留原文件和完整错误供检查；安装器会备份准备修改的文件，但不会猜测如何重写格式异常的用户数据。 |
| `codex-pet test` 成功，但真实 prompt 不改变 Pet | 确认已安装 Codex CLI 且 hooks 已启用。重启 Codex，在新会话中运行 `/hooks` 检查 hook；如果 Codex 请求信任，让用户查看并决定。检查 `~/.config/codex-pet/install.json` 的 `hooks_mode`，确认更新的是哪份配置。 |

任何命令失败时，都应在第一处失败停下，记录准确命令和完整输出，再按对应条目处理。依赖或配置失败后不要反复重跑安装器。

## 连接 Codex 会话

没有 Codex CLI 也能安装 Pet 并演示各状态。要让真实会话驱动状态，请安装并启动 Codex；安装 hooks 后重启 Codex。在新会话中运行 `/hooks` 查看已注册命令。如 Codex 提示信任 hook，应把提示交给用户查看和决定。安装器会把 hook 模式（写入 `~/.codex/config.toml` 的 inline hooks 或 `~/.codex/hooks.json`）记录在 `~/.config/codex-pet/install.json`。

如需卸载，在同一仓库目录运行 `./uninstall.sh`。脚本移除 Pet 命令链接和 Pet 自己添加的 hooks，同时保留 Python 依赖、Codex 配置备份及保存的形象和位置。
