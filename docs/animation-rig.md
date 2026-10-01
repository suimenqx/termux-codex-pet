# 秋田犬共享原画与骨骼制作流程

当前模型为 **akita-rig-v1**。五个状态都从同一套图层、固定相机和骨骼导出。模型尺度不是由每帧透明外接框推算：头部、身体、尾部的变换只有平移与旋转，`scale=1`；四肢骨长在所有状态中保持不变。

## 制作边界

| 文件 | 职责 |
| --- | --- |
| `docs/artwork/akita/rig-v1/` | 原画来源、图层、`model.json`、提示词、制作单、审查联系表 |
| `tools/prepare_akita_model.py` | 从保留的原画重建固定绑定图层，记录裁切与哈希 |
| `tools/akita_rig.py` | 无绘图库依赖的连续动作、固定长度 IK、骨骼皮片变换 |
| `tools/render_akita.py` | 皮片合成、局部眼部网格、透明边缘取样、离线 PNG 导出和清单 |
| `codex_pet/animation.py` | 唯一曝光时间表、进入/循环/保持逻辑 |
| `codex_pet/art.py` / `frame_display.py` | 读取离线预乘像素包、缓存徽标帧，在 GUI 线程复用一个原生缓冲区 |
| `codex_pet/assets/akita/rig-manifest.json` | 当前生产 PNG、原画模型、制作源码、关节、接触与遮挡的对应关系 |
| `tools/audit_animation.py` | 核对上述版本与实际运行像素，再输出尺寸、骨长、接触和四脚轨迹 |

运行时只读取离线导出的帧数据；Pillow、模型求解与网格处理均在离线工具中。导出器同时生成标准 PNG 与 `native-frames.zip`，后者逐帧保存同一 PNG 的显式预乘 RGBA，并独立压缩。秋田犬实时读取对应条目、叠加不透明徽标并缓存；首次显示也无需逐像素预乘或重编 PNG。缺少像素包的旧版/部分素材允许走较慢的 PNG 解码回退。GUI 线程把预乘像素写入同一个原生缓冲区；每次复制后等待同一连接的应答，再写下一帧。机器人继续使用 PNG 显示接口。原生应答不是屏幕刷新回执，实际呈现仍需设备观察。

静态 PNG 缓存可容纳整套 168 张素材；原生预乘缓存上限为 80 帧，即 20 MiB 像素，另有一个 256 KiB 共享缓冲区和对应原生位图。合成 PNG 与离线直通道 RGBA 缓存各自有界，实时显示不填充离线 RGBA 缓存。只读 ZIP 索引与一个文件描述符在 daemon 生命周期内复用，避免首次读取每张图时重新解析 168 个条目；当前压缩像素包约 15 MiB。预乘公式为 `round(channel × alpha / 255)`，alpha=0 时 RGB 必须为 0；禁止将直通道字节原样交给原生位图。

## 同一模型如何保持尺寸

- 统一右向三分之四视角与 256 单位画布；构图原点 `(128,236)`。近侧名义足底 `y=234`，远侧 `y=224`。纹理包含毛边与取样留白，足底标记属于模型坐标。
- 头部、尾与项圈从同一中性原画分层；被遮挡的躯干和完整前/后腿在一张静态部件原画中补齐。两只前腿共用前腿纹理，两只后腿共用后腿纹理。
- 静态部件图集实际尺寸为 `2172×724`，不是合格的等格动作表。按 `model.json` 中明确的部件边界裁切，并在**绑定阶段一次**放到模型坐标。原图、裁切框、身体放置框和图层哈希全部保留；后续不逐帧裁角色或调 zoom。
- 远侧腿使用固定 `0.9` 投影与固定明暗，这是该模型的单一视角设定，五个状态共用。它不是奔跑状态的缩放修正，也不是通用透视标准。
- 头部像素的相对位置由刚性变换保持；只允许两个眼部区域变形，闭眼时增加同位置眼睑线。项圈独立随身体移动，状态色使用同一个蒙版。
- 1024 单位工作纹理（4 个纹理像素/设计单位）及 2 倍渲染采样是本次离线制作配置，最终一律导出 256×256。模型绑定可以使用不同部件的固定尺寸；禁止每个动作各自改变头身尺寸。

姿势轮廓会随抬爪、摆尾和腾空改变，这是动作占用空间的变化。检查头脸固定尺度、骨长与共同原点，不能要求每个姿势的外接矩形同宽同高。

## 骨骼与皮片

每条腿有上段、下段和脚掌。两段 IK 由固定骨长解出膝/肘位置；目标超出可达范围直接失败，不能拉长骨骼掩盖错误。上段、下段和脚掌是同一腿纹理上有重叠区的刚性皮片，关节遮罩平滑过渡。弯曲时允许关节遮挡，皮片自身不发生网格翻折；脚掌独立控制朝向。

最初试作的线性混合网格在粗短腿的大屈曲处发生三角形翻折；曲线条带方案又产生不合适的关节收窄，因此均未采用。现有方案用骨骼控制肢体、局部网格控制眼睑。更复杂的皮肤变形可另建模型版本，不能把当前皮片误写成体积保持的三维蒙皮。

从后到前依次绘制远侧腿、尾、身体、近侧腿、项圈和头。遮挡数据来自实际合成层：在每个脚掌中心周围采样自身 alpha，再乘以后续覆盖层的透过率。清单保留 `visible_fraction`；联系表仅给可见比例至少一半的采样点画圆环。这是一条标记显示规则，不是步态自然度阈值。

[Pillow 的变换接口](https://pillow.readthedocs.io/en/stable/reference/Image.html)负责仿射及眼部网格取样；取样先转换成预乘 `RGBa`，再还原为 PNG 的直通道 `RGBA`，相关像素模式见 [Pillow concepts](https://pillow.readthedocs.io/en/stable/handbook/concepts.html)。

## 动作与补帧

`pose_at(model, state, seconds)` 返回该时刻的确定姿势，`clip_poses()` 按运行时间表采样。当前 Running 为 32×20ms，640ms 周期；详见[四足接触表](animation-gait.md)。其余状态的曝光与语义见[制作单](artwork/akita/rig-v1/brief.md)。

补帧步骤：

1. 读取本模型和制作单，确定要细分的动作段及保留的事件时刻。
2. 修改曝光表；同一模型按新累计时间重新求解姿势。补帧无需重新生成头、身体或整张宠物。
3. 如果改变动作轨迹，检查所有连续时间段的 IK 可达性、接触和循环位置/速度，不能只检查导出的离散帧。
4. 若确实修改原画、绑定或镜头，升级模型记录，五个状态一起导出并重新审查。
5. 导出到新的候选目录，检查完整动作及四周边界。不得按单帧外接框重新居中或补放大。

## 重建与导出

离线依赖与运行时依赖分开安装，以下路径可以替换为另一个专用虚拟环境：

```sh
python -m venv "$HOME/.cache/codex-pet/rig-tools"
"$HOME/.cache/codex-pet/rig-tools/bin/python" -m pip install -r tools/requirements-art.txt
"$HOME/.cache/codex-pet/rig-tools/bin/python" tools/prepare_akita_model.py
"$HOME/.cache/codex-pet/rig-tools/bin/python" tools/render_akita.py \
  --output "$HOME/.cache/codex-pet/artwork-review/rig-candidate"
```

导出包含 `frames/<state>/NN.png`、逐字节相同的首帧回退、`native-frames.zip`、`rig-manifest.json` 和 `preview-<state>.json`。像素包使用固定 ZIP 时间和权限，内容为 `<state>/NN.rgba` 的 256×256 行优先、R/G/B/A 字节；它是可重建的显示产物，不是另一套原画。清单记录 Pillow 版本、模型及制作源码哈希、曝光、关节、固定骨长、接触状态、脚掌可见比例，以及 PNG 文件、直通道 RGBA、预乘 RGBA 和完整像素包哈希。更改制作代码或时间表后必须重导出。

`--state running` 只导出该状态，得到的是部分候选清单；正式发布应一次导出全部状态。`--pose 0.24 --state running --output /path/pose.png` 可单独检查任意中间时刻。导出拒绝画布边缘非零 alpha、不可达 IK 和非 1 的头身/尾缩放；不能自动判断美观或真实显示节奏。

先用候选清单预览，非循环片段只播放一遍以免把进入段误当循环：

```sh
python tools/preview_animation.py --state running --cycles 2 \
  --candidate "$HOME/.cache/codex-pet/artwork-review/rig-candidate/preview-running.json"
```

通过素材审查后，将整套 `frames/`、五张回退图、`native-frames.zip` 与 `rig-manifest.json` 一起复制到 `codex_pet/assets/akita/`；不要把预览清单作为运行素材。跑全套测试和全部状态审计，再依[接入流程](animation-acceptance.md)安装到设备。生产预览会正确执行 Ready 的一次进入、休息循环及 Blocked 的保持规则。

重现性针对保留的原画和固定 Pillow 版本，不针对重新调用图像模型。不同 Pillow/滤波实现需要重新导出、审查及更新清单，不得沿用旧帧哈希。
