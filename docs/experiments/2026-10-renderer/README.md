# 2026-10 Termux:GUI 重构实验

本目录保存 2026-10-02 的实测证据，供[重构方案](../../research/termux-gui-refactor-plan.md)引用。生产代码、动画图片、时长、用户配置与已安装运行版本没有因这些探针而变更。GUI 探针使用自己的连接和临时窗口，保留已有桌宠运行。

## 证据索引

| 文件 | 内容与边界 |
| --- | --- |
| [environment.json](environment.json) | 设备、Python、binding、插件版本响应与环境能力；不是 APK 文件或签名鉴定 |
| [source-findings.md](source-findings.md) | 固定版本官方源码、协议与本地 binding 核对；包含 EOF 死循环和 buffer 删除后断连的追加发现，区分复现结果与原因推导 |
| [image-results.json](image-results.json) | Pillow/NumPy 隔离依赖、包 SHA256、像素正确性、atlas、预乘、内存计算及 Python 耗时 |
| [runtime-results.json](runtime-results.json) | Manifest 原型与生产帧/时长对照、长时间跳帧原型、独立 wake socket 饱和实验 |
| [gui-results.json](gui-results.json) | 原生窗口、格式名称、PNG/shared 提交加命令屏障耗时、移动、重连与本进程 FD 记录 |
| [buffer-lifecycle.json](buffer-lifecycle.json) | 共享 buffer 创建、删除、后继 buffer 与连接生命周期的设备复现记录 |
| [visual-results.json](visual-results.json) | PNG/shared 并排窗口与触摸记录；是否完成视觉、拖动人工验收以文件记录为准 |

图像原始计时样本、生成的临时 atlas、下载包保留在 `~/.cache/codex-pet/refactor-research/`；仓库保存统计记录和复现脚本。GUI 记录保存各轮统计，不包含逐帧原始时序。结果中的绝对路径是测量当时的设备路径。

## 环境与依赖复现

本机基线为 Android 12 / aarch64、Python 3.14.6、libpng 1.6.59、Python `termuxgui` 0.1.6；插件 `getversion()` 返回 7。初始全局 Python 没有 Pillow、NumPy。隔离实测版本为 Pillow 12.3.0、NumPy 2.4.4；Pillow 的 WebP feature 返回可用，codec 版本为 1.6.0。

以下命令从仓库根目录执行。只下载和解包，不运行 `apt install`、`pip install` 或系统升级。指定版本与本次报告一致；软件源下架某个版本时，应记录无法复现，不能换版本后继续引用旧报告作为新环境的测试结果。

```sh
probe_deps="$HOME/.cache/codex-pet/refactor-research/deps"
mkdir -p "$probe_deps/debs" "$probe_deps/root"
(
  cd "$probe_deps/debs" || exit
  apt download \
    python-pillow=12.3.0 python-numpy=2.4.4-1 \
    openjpeg=2.5.4 libimagequant=4.4.1 libraqm=0.11.0 \
    libavif=1.4.2 libopenblas=0.3.34 libxcb=1.17.0-1
) || exit
for probe_deb in "$probe_deps"/debs/*.deb; do
  dpkg-deb -x "$probe_deb" "$probe_deps/root" || exit
done
apt-get -s install python-pillow python-numpy
```

应等下载成功结束后再解包。`libxcb` 在基线已安装，本次额外下载了一份，不代表新增长期依赖。模拟安装在该基线显示新增另外七包，无升级、删除；其他已有 native 依赖由当前 Termux 环境提供。这不是适用于任意新装手机的完整系统镜像：换设备需重新检查模拟安装和真实导入结果。

`image-results.json` 的 `environment.downloaded_packages` 保存实际下载文件名、大小、版本、Depends 与 SHA256；`apt_simulated_install` 保存依赖解析结果。仅添加 Python 搜索路径、没有添加隔离 native 库路径时，实际复现了 `PIL.Image` 缺少 `libopenjp2.so`、NumPy 缺少 `libopenblas.so` 的错误，见 `control_imports_without_isolated_native_library_path`。探针通过子进程级的 `PYTHONPATH`、`LD_LIBRARY_PATH` 解决，未改变当前终端或全局环境；`global_modules` 用 `python -I` 复查全局模块仍不存在。

## 运行探针

逐个执行，不要并行运行 CPU 基准或其他压力测试。计时使用单机 wall time，无 CPU governor、温度或后台负载控制；重复实验应保留自己的结果，避免覆盖本次证据。

图像探针读取现有 34 张 256×256 PNG；384×416 输入只是把原图放入透明测试画布，没有放大或改写生产素材。默认 30 次样本，批量解码等较重项目固定 10 次，独立进程导入 7 次。

```sh
python tools/probe_image_pipeline.py \
  --deps-root "$HOME/.cache/codex-pet/refactor-research/deps/root" \
  --samples 30 \
  --output "$HOME/.cache/codex-pet/refactor-research/image-rerun.json"
```

该脚本核对 65,536 个颜色×alpha 组合、所有生产 PNG 的解码一致性、WebP `lossless`/`exact` 差异、atlas 切帧、NumPy stride 与 mmap 赋值。`image-results-full.json` 包含原始计时；缓存命中、预乘和 anonymous mmap 复制均不连接 Android GUI。解码输入是内存中的压缩字节，未清空磁盘缓存；fresh-process 导入也是热文件缓存。进程 RSS 读取 `/proc/self/status`，不使用此设备上会继承父进程高水位的 `resource.ru_maxrss`。

运行时探针不启动 daemon、不连接 GUI、不改会话。它验证 clip 数据表达与现有画面/时长一致，并测量隔离对象的时钟和唤醒行为：

```sh
python tools/probe_runtime_plan.py \
  --clock-repeats 3 \
  --output "$HOME/.cache/codex-pet/refactor-research/runtime-rerun.json"
```

Manifest 检查复用生产帧与合成函数，不能证明新的 codec、loader 或已实现的重构 runtime 正确。时钟原型只覆盖 Running 循环；wake 饱和数是本机 socket 缓冲区表现，不是支持会话数。

GUI 探针要求设备已有可用的 Termux:GUI 和 overlay 权限，会临时显示另一个窗口。它不需要 Pillow 或 NumPy。使用外层超时，保留运行日志；若超时或异常退出且没有完整 JSON，本次不能算通过。

```sh
timeout 180s python tools/probe_termux_gui.py \
  --samples 100 --trials 3 \
  --output "$HOME/.cache/codex-pet/refactor-research/gui-rerun.json"
```

人工对照可运行 120 秒，窗口左右标记为 PNG / BUFFER，并切换深浅背景；查看透明边缘、相同姿态、闪烁及拖动，记录观察与设备条件：

```sh
timeout 180s python tools/probe_termux_gui.py \
  --visual-seconds 120 \
  --output "$HOME/.cache/codex-pet/refactor-research/visual-rerun.json"
```

单独复现删除最新 buffer 后 EOF、binding overlay 构造错误、overlay configuration 无响应及新连接恢复：

```sh
timeout 40s python tools/probe_termux_gui.py \
  --lifecycle-only --timeout-seconds 30 \
  --output "$HOME/.cache/codex-pet/refactor-research/lifecycle-rerun.json"
```

最终脚本还包含默认 180 秒的进程级 watchdog，覆盖 binding 构造时的等待；EOFGuard 本身仅保护连接建立后的读取。visual 的简化拖动阈值为 6 屏幕像素，不能将其通过等同于生产 6 dp、取消恢复及屏幕边缘锚点逻辑全部通过。

## 解释结果时必须保留的边界

以上文件是重构前的调查证据。重构后的生产路径与新版 Pillow 复现以
[实施记录](../../research/implementation-status.md) 为准；历史探针通过
`tools/historical_art.py` / `historical_animation.py` 保留原报告标签，当前
图片准备使用生产 Pillow codec，因此重跑这些脚本需要 Pillow。

生产 renderer 的独立验收入口：

```sh
python tools/probe_production_renderer.py --samples 60 --output "$HOME/.cache/codex-pet/renderer-comparison.json"
python tools/probe_renderer_recovery.py "$HOME/.cache/codex-pet/renderer-recovery.json"
python tools/probe_shared_daemon.py --seconds 300
```

前两个临时创建额外测试 overlay，后一个短时重启唯一正式 daemon 并在退出时
恢复普通启动策略。记录分别是 `shared-production-serial.json`、
`shared-recovery.json` 及实施记录中的人工反馈。不要和测试套件同时运行计时。
本地 FD/mmap 归零不替代 Android 窗口与 buffer 的资源观测。

- 本机 JSON buffer 参数是 `ARGB888`；不能把协议文档的 `ARGB8888` 名称直接代入。探针隔离不同格式的连接，并保护 EOF；生产 binding 的 EOF 读取缺陷尚不因运行探针而修复。
- GUI 耗时止于同连接的 `getversion()` 命令屏障。根据已核对版本的顺序处理，它可确认先前 staging 像素已被插件读取；不能测量 Android 实际上屏延迟。`python_cpu_ms` 只属于探针进程，未包括插件进程，也不是设备 CPU 或耗电。
- 共享 buffer 仍会从共享内存复制到插件 bitmap；`flush()`、发送成功、双缓冲或固定等待均不自动证明消费者已读完。最终删除 buffer 后断连与本地 FD 清理必须结合生命周期记录解读。
- 第一轮图像计时曾与 GUI binding 的 EOF CPU 空转重叠，已弃用并完整重测；受影响原始结果仅保留为缓存中的 `image-results-overlapping-full.json`。
- 逐像素相同、预乘公式正确、触摸事件出现，都不能单独证明 Android 透明边缘、屏幕帧节奏、实际拖动或动画美术已通过验收。没有人的实际观察，就保持该项未验收。
- 本次未验证其他 Android/ROM、跨渠道签名迁移、插件升级、GLES2、protobuf、锁屏/旋转/多指取消的完整组合。原始结果和源码推导不得扩大为这些环境的保证。
