# ArkPets / 阿米娅本机离线导出验证

后续这批已完成本机导出、独立安装与自动真机检查，最终状态见[接入记录](../artwork/community_previews/2026-10-popular/brief.md)和[验证摘要](../artwork/community_previews/2026-10-popular/verification.json)。以下保留当时的调查和限制，不以技术探针代替人工观感验收。

2026-10-03 UTC 调查。本记录只证明社区原素材的导出路径；未操作生产桌宠、切换外观或安装运行版本。完整接入和真机验收由主任务记录，不能用本文件替代用户的观感反馈。

## 结论与边界

在本次 Termux / Android arm64 设备上，已用官方 Spine 3.8 Canvas Runtime 和 `@napi-rs/canvas` 导出 **原版阿米娅的五段完整动作**，得到透明 PNG。无需在桌宠进程中加入 Spine、Node、WebView 或 OpenGL。这里只选择 ArkPets 使用的同一模型库中的一个代表角色，并非导入整个 Ark-Models 收藏。模型和导出图片保留在本机缓存，不进入公开源码仓库。

这是可复现的转换验证，不是“支持所有 Spine 模型”的声明。此模型包含区域和网格附件，未发现裁剪附件；官方 Canvas 绘制器不能完整替代 WebGL 的裁剪、着色及混合功能。以后换模型必须重新检查附件、混合模式、颜色动画和边界；遇到未支持的能力，应报错或使用合适的上游渲染器，不能悄悄丢图层。[官方 Canvas 实现](https://github.com/EsotericSoftware/spine-runtimes/blob/8b4844bd4b193ba9e54487ed397a777993cbad56/spine-ts/canvas/src/SkeletonRenderer.ts)

## 固定来源

| 项目 | 固定版本 / 文件 | 作用 |
| --- | --- | --- |
| ArkPets | `isHarryh/Ark-Pets@d82d47ba4858adc91befd1e77a3abe6f2ce6a4f8` | 目标社区项目；调查时 1,106 stars，仅代表项目热度 |
| Ark-Models | `isHarryh/Ark-Models@8a3857c250a5c271429aefa82c660ff35803166e` | 模型数据来源 |
| 模型 | `models/002_amiya/build_char_002_amiya.{atlas,png,skel}` | `models_data.json` 将其标为阿米娅 / Amiya、干员、默认服装 |
| Spine Runtime | `EsotericSoftware/spine-runtimes@8b4844bd4b193ba9e54487ed397a777993cbad56`，`spine-ts/build/spine-canvas.js` | 官方 `3.8` 分支；固定 SHA 文件与初次下载逐字节一致 |
| Canvas 后端 | `@napi-rs/canvas@1.0.10`，Android arm64 可选二进制同版本 | 在本机完成 `require()`、画布创建及 PNG 编码 |

模型库明确要求 Spine 3.8，并说明自 2025-03 起纹理统一使用预乘 alpha；2026-02 起干员基建模型来源改为 PC 版。[Ark-Models README](https://github.com/isHarryh/Ark-Models/blob/8a3857c250a5c271429aefa82c660ff35803166e/README.md) 模型身份可由固定版 [models_data.json](https://github.com/isHarryh/Ark-Models/blob/8a3857c250a5c271429aefa82c660ff35803166e/models_data.json) 核对。Canvas 的平台包由其 [npm 官方元数据](https://registry.npmjs.org/@napi-rs/canvas/1.0.10) 指定；本机实际安装结果另见缓存的 `package-lock.json`。

只下载了该模型的三件套及元数据，没有克隆约 GB 级的整个素材库。

| 文件 | 字节数 | SHA-256 |
| --- | ---: | --- |
| `build_char_002_amiya.atlas` | 4,554 | `696114f96f2a2366fc4a373bd1d08c7569f9eb279305347364ffd629eab9d9b5` |
| `build_char_002_amiya.png` | 183,676 | `618d7ce9cc18e4ef46cb5f513ffebc0b6b7b7e08f8e0f12a7abb3ff93547d7e4` |
| `build_char_002_amiya.skel` | 82,146 | `41908ed5c73ed9c5b5616a7c45d61275c29319fbb6a46068df5a4d0c6f5c7bff` |
| `spine-canvas.js` | 309,759 | `250eaf578a4654a63de0aef7dfad0fc4bcb613bcf2b3ea8d0d2822e4b9597ce0` |

## 许可要分开核对

1. **角色美术**：Ark-Models 声明全部素材版权归上海鹰角网络有限公司所有，限制商业使用及损害权利人利益。它不是将角色美术置于 ArkPets 的代码许可证下，也不是一般用途的开源角色授权。保留来源、固定版本和该声明；本次只准备用户本机预览，不公开再分发图片。[素材声明](https://github.com/isHarryh/Ark-Models/blob/8a3857c250a5c271429aefa82c660ff35803166e/README.md#版权声明)
2. **运行库**：Spine 3.8 Runtime 自有许可证，不是 MIT。其集成和再分发条款涉及 Spine Editor 许可；不能因为 GitHub 可下载或最终产物为 PNG，就声称公开分发运行库没有要求。[固定版 LICENSE](https://github.com/EsotericSoftware/spine-runtimes/blob/8b4844bd4b193ba9e54487ed397a777993cbad56/LICENSE)
3. **本机个人导出**：针对“没有 Editor、从游戏资源导出 PNG”的同类问题，官方 Nate 明确回复： “Using the Spine Runtimes for personal use is fine without a Spine license.” 本次个人离线转换依据这一明确说明，不把“私有目录”本身当成授权理由。[官方导出讨论](https://esotericsoftware.com/forum/d/25551-exporting-animation-frames)
4. **发布边界**：Nate 的后续解释区分资产、开发过程和 Runtime 分发：分发 Runtime 需要许可安排，单独图像/视频不携带 Runtime 许可要求。这不能消除美术本身的权利限制。[官方许可解释](https://esotericsoftware.com/forum/d/29920-spine-license-usage-and-responsibilities-in-freelance-work)

本机保留了 `SPINE-LICENSE` 和模型库 `README.md`。公开仓库不应 vendor `spine-canvas.js`、平台二进制或阿米娅纹理；若今后提供包含 Runtime 的通用导出工具发行包，需要单独落实分发条款。不要将本次个人试播写成商用或任意再分发授权。

## 实测的模型和时间轴

二进制解析报告：Spine `3.8.99`；纹理 **516 × 516**；默认皮肤 `default`；15 个网格附件、32 个区域附件；文件中的初始宽高约 232.50 × 436.50，不足以包含五种动作的共同极值。

| 原动作名 | 原时长 | 15 fps 取样数 | 整数毫秒总时长 | 可用于的语义 |
| --- | ---: | ---: | ---: | --- |
| `Relax` | 1 s | 15 | 1,000 | 待机 |
| `Move` | 1.133333325 s | 17 | 1,133 | 工作期间走路 |
| `Interact` | 1 s | 15 | 1,000 | 完成反馈，可播一次后回待机 |
| `Sit` | 8 s | 120 | 8,000 | 等待输入 |
| `Sleep` | 3 s | 45 | 3,000 | 阻塞时休息 |

另有零时长 `Default`，不作为动画循环。这些名字和时长来自官方 Runtime 对上述固定骨骼文件的解析，不是凭图片猜测。**15 fps 是本次离线取样选择，不是声称原画只有 15 fps**。取样数为 `ceil(duration × fps)`，时间点覆盖 `[0,duration)`，不重复附加循环首帧；每帧毫秒数用累计边界四舍五入之差分配，保持表中的总周期。

212 张 256 × 256 RGBA 帧的解码上限为 `212 × 256 × 256 × 4 = 55,574,528` 字节，即 **53 MiB**，低于当前 64 MiB Pet Pack 上限；本次得到 201 种不同 RGBA 像素内容。全部 PNG 合计 5,520,663 字节。若改取样率或加入动作，需重新计算预算，不能只看压缩文件大小。

## 实际转换步骤和坑

本机实验目录：`~/.cache/codex-pet/arkpets-import/`。其中 `probe.js` 验证加载，`export.js` 为可重复执行的独立实验脚本，`frames/report.json` 保存每帧路径和时长。它们是实验材料；生产导出入口应由主任务统一维护。

```sh
npm install --prefix "$HOME/.cache/codex-pet/arkpets-import" \
  --ignore-scripts --no-audit --no-fund @napi-rs/canvas@1.0.10
node "$HOME/.cache/codex-pet/arkpets-import/probe.js"
node "$HOME/.cache/codex-pet/arkpets-import/export.js"
```

脚本接受一个 JSON 配置文件路径；字段为 `canvasModule`、`runtime`、`texture`、`atlas`、`skeleton`、`clips`、`fps`、`size`、`supersample`、`output`。未配置时使用本机上述缓存和五种已验证动作。`canvasModule` 是安装好的包目录；不在桌宠运行时安装 npm 依赖。此设备加载 Canvas 不需要额外 `LD_LIBRARY_PATH` 修复。

关键处理顺序：

1. 先用 Pillow 读取纹理。原图所有像素均满足 `max(R,G,B) ≤ A`，与上游 PMA 声明一致。Canvas 会按常规 PNG 再做预乘，因此输入前必须将已有 PMA 恢复为直通道：`Image.frombytes("RGBa", im.size, im.tobytes()).convert("RGBA")`。不能把预乘数据直接当普通 RGBA 送入 Canvas，否则半透明边缘发暗。转换后的中间纹理也只存本机。
2. 用官方 `TextureAtlas`、`AtlasAttachmentLoader`、`SkeletonBinary` 读取源文件。用 `AnimationState` 应用每个时间点并更新世界变换，保留原骨骼动画，不自行解析骨架、不补画中间姿势。
3. 必须启用 `renderer.triangleRendering = true`。默认 `drawImages()` 只处理区域附件，会丢掉网格部分。本例无需修改下载的上游 Runtime。
4. 以五个动作的两倍时间采样检查共同边界，得到约 `[-275.44,-98.10,197.66,451.90]`。对最长边加入两侧各 4% 的本次设计留白，共同视野边长约 594.01。五个动作共用同一变换；不逐帧按包围盒放大或重新居中。
5. 先在 **1,024 × 1,024** 透明 Canvas 绘制，再以高质量取样缩到 **256 × 256**。这用于减轻 Canvas 三角裁剪边缘的细缝；初版 512 px 直出曾看见头发网格细线。超采样能减轻，但不等于官方 WebGL 输出逐像素一致，后续仍要审查小尺寸显示。

最终全帧检查：所有帧非空；有真实透明像素及不透明像素；非零 alpha 到画布最近边缘至少 10 px。`contact.png` 将每个动作的首帧、约四分之一、约二分之一和末帧放在深浅背景上，已查看，角色部件完整、姿势来自原动画。以上证明文件导出和基本构图通过，不证明真实手机上的周期衔接、视觉流畅度或拖动已通过。

## 可维护接入要求

- 社区来源目录只声明仓库、固定提交、三个模型文件及哈希、动作到语义的映射、取样率和共同布局。相同类型走一套转换器，不为每个角色复制一份解析器。
- 转换依赖与 Python 桌宠运行依赖分离。输出仍是既有 `pet.json + RGBA PNG`，然后走统一 `pet import`；别把 Spine 状态机放进桌宠 runtime。
- 记录本次支持的附件、混合模式、颜色能力；新模型出现不支持能力时失败退出。解析成功不能证明渲染正确。
- 固定依赖与源哈希，保留完整许可和导入记录。更新来源或转换参数时采用新 Pack ID，避免覆盖不可变本地包、污染帧缓存。
- 先验证本地帧及解码预算，再让主任务安装和逐状态试播；不因导出成功就改动用户原有 Pet、位置或 renderer 默认值。

与本次相关的原始来源：[ArkPets README](https://github.com/isHarryh/Ark-Pets/blob/d82d47ba4858adc91befd1e77a3abe6f2ce6a4f8/README.md)、[模型目录](https://github.com/isHarryh/Ark-Models/tree/8a3857c250a5c271429aefa82c660ff35803166e/models/002_amiya)、[官方 3.8 Canvas Runtime](https://github.com/EsotericSoftware/spine-runtimes/blob/8b4844bd4b193ba9e54487ed397a777993cbad56/spine-ts/build/spine-canvas.js)。
