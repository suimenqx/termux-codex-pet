# Clawd / DSH 社区素材接入实测

后续这批已完成本机导出、独立安装与自动真机检查，最终状态见[接入记录](../artwork/community_previews/2026-10-popular/brief.md)和[验证摘要](../artwork/community_previews/2026-10-popular/verification.json)。以下保留当时的调查和限制，不以技术探针代替人工观感验收。

调查日期：2026-10-03 UTC。本次只核查现成素材、播放定义及本机离线解码，
不生成新动作，不改变 daemon、选中宠物或用户配置。本文的“通过”指文件与
转换路径可复现；不代表手机观感已经通过人工验收。

## 固定来源与结果

| 来源 | 固定提交 | 结果 |
| --- | --- | --- |
| [Clawd on Desk](https://github.com/rullerzhou-afk/clawd-on-desk/tree/a9c226de6c01f9bfb3afbb1e2885bd55511d6986) | `a9c226de6c01f9bfb3afbb1e2885bd55511d6986` | 有透明 GIF；图片条款明确限制跨应用使用，不能以“仅本机”代替许可 |
| [Clawd Tank](https://github.com/marciogranzotto/clawd-tank/tree/a8942d140eeb8bcf549857ad599f7d62fd29eb01) | `a8942d140eeb8bcf549857ad599f7d62fd29eb01` | 原作者仓库 MIT、无另列素材例外；有可直接读取的透明 GIF，可作为明确注明来源的 Clawd 替代素材 |
| [DSH Pet](https://github.com/PC2005-cloud/dsh-pet/tree/51041a7eb78e4b8e1df5c0a1dc4576ea481f8920) | `51041a7eb78e4b8e1df5c0a1dc4576ea481f8920` | 六段原始 VP9-alpha 视频成功解码；素材允许开源使用、禁止商用，区别于 MIT 代码 |

所有下载、像素样本和探针结果保存在本机
`~/.cache/codex-pet/clawd-dsh-import/`。这不是安装目录，也不应整体提交 Git。
固定 revision 之外还应校验下文 SHA-256，不能从浮动 `main` 静默更新素材。

## Clawd on Desk：真正的阻碍是素材条款

`assets/LICENSE` 明确把 SVG、PNG、GIF 等图片排除在代码许可证之外。
除单独注明的少量 CC0 图标外，复制、修改、分发、使用图片需要权利人的书面
许可；明确列出的例外仅为个人使用原项目发布的 Clawd on Desk 应用。
因此，将这些 GIF 转换后装入另一款桌宠应用，不能仅以“不上传图片”为由
声称满足该例外。Clawd 角色还涉及 Anthropic，不能把本项目当成官方授权产品。
[素材条款](https://github.com/rullerzhou-afk/clawd-on-desk/blob/a9c226de6c01f9bfb3afbb1e2885bd55511d6986/assets/LICENSE)

技术上并不需要另装 SVG 浏览器：`assets/gif/` 已含 idle、typing、notification、
happy、error 五种透明动画。Pillow 顺序 `seek()` 后转 RGBA，实测尺寸均为
302×300、alpha 包含 0 和 255，曝光为 60/70 ms，帧数分别为
48/45/90/45/45。这些结果只用于可行性和权利边界判断，不构成导入许可。
[原始 GIF 目录](https://github.com/rullerzhou-afk/clawd-on-desk/tree/a9c226de6c01f9bfb3afbb1e2885bd55511d6986/assets/gif)

条款文件 SHA-256：
`dfa3167ff417f163515355ad36d2fd7e96e3c1a1ce880549bc20b57497fb1fca`。

## Clawd Tank：明确标注的原上游替代路径

Clawd on Desk 的作者致谢明确将 `marciogranzotto/clawd-tank` 列为 Clawd
像素画参考来源。它不是新生成的近似角色，也不是同一套后续动画。
[来源致谢](https://github.com/rullerzhou-afk/clawd-on-desk/blob/a9c226de6c01f9bfb3afbb1e2885bd55511d6986/README.md)

Clawd Tank README 声明 MIT，仓库树只有根 `LICENSE`，所检查的 SVG 和
导出 GIF 未发现单独的保留权利声明；许可证署名 Marcio Granzotto Rodrigues。
应把 MIT 原文及作者信息随导入包保留。此证据是该仓库作品的发布许可记录，
不是 Anthropic 角色、商标或所有第三方权利的额外授权证明。
[许可证](https://github.com/marciogranzotto/clawd-tank/blob/a8942d140eeb8bcf549857ad599f7d62fd29eb01/LICENSE)、
[素材流水线与许可说明](https://github.com/marciogranzotto/clawd-tank/blob/a8942d140eeb8bcf549857ad599f7d62fd29eb01/README.md)

直接使用 `assets/slack-emojis/` 的现成透明 GIF，避免运行 Playwright 或把
SVG/CSS 动画系统带进运行时。Pillow 已完整遍历以下五份导出，每份均有透明
和不透明像素。表中时间来自 GIF 自身，不能用原 SVG 标称时间覆盖它。
[原始 GIF](https://github.com/marciogranzotto/clawd-tank/tree/a8942d140eeb8bcf549857ad599f7d62fd29eb01/assets/slack-emojis)

| 文件（共同前缀 `clawd-`） | 尺寸 | 帧数 | 单帧曝光 ms | 总时长 ms |
| --- | --- | ---: | --- | ---: |
| `idle-living.gif` | 128×91 | 60 | 260 | 15,600 |
| `working-typing.gif` | 128×123 | 18 | 80 | 1,440 |
| `notification.gif` | 125×128 | 35 | 80 / 490 / 740 | 3,870 |
| `happy.gif` | 128×113 | 24 | 80 | 1,920 |
| `working-confused.gif` | 128×122 | 35 | 80 / 160 / 330 / 580 / 660 / 910 | 5,870 |

上游导出器按**每个动作的整体边界**裁切，再把长边缩到 128，而不是全角色
共用同一比例。实图检查确认 idle 的身体比 happy/typing 大。接入时可以按
固定的角色躯干参考，对每个 clip 做一次固定比例与偏移校准；禁止逐帧裁边、
逐帧缩放，那会造成角色大小和落脚点抖动。也不能把这个像素角色宣传为非像素。
[导出算法](https://github.com/marciogranzotto/clawd-tank/blob/a8942d140eeb8bcf549857ad599f7d62fd29eb01/tools/svg2slack_emoji.py)

| 文件 | SHA-256 |
| --- | --- |
| `clawd-idle-living.gif` | `0a31312108248d80f4428e311308b56f7eb2e5778e6f2cb7e7ef8cfc0439c739` |
| `clawd-working-typing.gif` | `610ce77a79071ae0697cd101c8f91f5514919ed65276a2f9db2adaebec922f3e` |
| `clawd-notification.gif` | `8a0d86e689aca9029edc63c40deb19b6db7429e52da238afb8059b554b1ba420` |
| `clawd-happy.gif` | `b0ad6bb71837caa0ddf0697523ebe69aa083de359e80b026665e8c3696cc0e0e` |
| `clawd-working-confused.gif` | `7111bd892ff9502182a39da911cf06e170a5f67ad3a94cebb207e4ef28656034` |
| `LICENSE` | `4a42b7de3a543d2fd127e953accd7a7db31d4bf90aecf464e156f1f188797072` |

## DSH：复用已有的手绘风动画，不重新生成

默认配置将主角命名为“蓝毛小女仆”。README 说明现有素材由豆包生成，因此准确
描述是“手绘风”，不能改称“画师手绘”。本次下载的是作者已经发布的成品，
不是重新跑其 AI 制作流水线。代码 MIT 与素材开源使用、禁止商用的声明分开
记录；导入包的来源说明应保留两者，不能只附根 MIT 后称图片也是 MIT。
[素材来源、格式及许可](https://github.com/PC2005-cloud/dsh-pet/blob/51041a7eb78e4b8e1df5c0a1dc4576ea481f8920/README.md)

固定 raw 路径格式：

```text
https://raw.githubusercontent.com/PC2005-cloud/dsh-pet/51041a7eb78e4b8e1df5c0a1dc4576ea481f8920/dsh-pet/assets/webm/<UTF-8 百分号编码文件名>
```

本次文件均是实际 WebM 数据，不是 Git LFS 指针。`ffprobe` 检查为
640×360、24 fps、VP9、`ALPHA_MODE=1`；六个文件都完整解码成功。

| 源动作 | 字节 | 帧数 | 容器时长 ms | 用途建议 |
| --- | ---: | ---: | ---: | --- |
| `待机呼吸休闲.webm` | 441,437 | 241 | 10,042 | idle |
| `写代码.webm` | 383,960 | 241 | 10,042 | running 对应工作语义 |
| `工作状态-思考冒泡.webm` | 408,849 | 241 | 10,042 | needs_input |
| `工作状态-雀跃庆祝.webm` | 488,024 | 241 | 10,042 | ready 一次后回 idle |
| `工作状态-垂头叹气冒汗.webm` | 198,937 | 118 | 4,917 | blocked |
| `原地左转奔跑.webm` | 614,526 | 241 | 10,042 | 可选移动素材，当前工作动作不必强制奔跑 |

上述五角色映射是本项目语义适配；上游也有不同工作状态池，但并非完全相同
的状态机。它的移动配置为原地左转奔跑额外指定起止静止时间，因此完整视频
不是“从第一帧到最后一帧一直奔跑”的纯循环。
[默认动画及移动配置](https://github.com/PC2005-cloud/dsh-pet/blob/51041a7eb78e4b8e1df5c0a1dc4576ea481f8920/dsh-pet/assets/config.jsonc)、
[播放器](https://github.com/PC2005-cloud/dsh-pet/blob/51041a7eb78e4b8e1df5c0a1dc4576ea481f8920/dsh-pet/runtime/electron-helper/sprite.js)

### 实测解码命令与依赖坑

本机 ffmpeg 8.1.3 启动最初报 `libplacebo.so` 找不到 libc++ `from_chars`
符号。原因是当前 Codex 会话的 `LD_LIBRARY_PATH` 指向 Codex 自带二进制目录，
遮蔽了 Termux 系统 libc++。只修改解码子进程的搜索路径即可启动，无需改动
系统包或全局环境。应先检测 ffmpeg 能否运行，只在这个已识别场景使用修复。

```sh
LD_LIBRARY_PATH="$PREFIX/lib" ffprobe -v error \
  -show_frames -show_streams -show_format -of json input.webm

LD_LIBRARY_PATH="$PREFIX/lib" ffmpeg -v error \
  -c:v libvpx-vp9 -i input.webm -vsync 0 \
  -f rawvideo -pix_fmt rgba pipe:1
```

关键是把 `-c:v libvpx-vp9` 放在 `-i` **之前**，明确选择支持 alpha 的输入
解码器；输出 `rgba` 这个名字本身不能证明透明度保留。实测上述六个文件的
输出 alpha 均覆盖 0 到 255，首帧还有中间 alpha 值；灰底合成检查能看到
透明边缘与原始人物。不要从默认 ffprobe 显示的 `yuv420p` 误判视频没透明。
同一 idle 首帧的对照解码也已实测：不指定输入解码器时 alpha 全为 255；
显式使用 libvpx-vp9 时为 0…255。因此转换器应检验输出透明度，不能只检验
文件扩展名或 PNG 的 RGBA 模式。

读 rawvideo 时每帧恰好为 `640 * 360 * 4` 字节，流式读取并即时缩放/导出，
不要把所有原尺寸视频帧一次性留在内存。原始 PTS 位于毫秒 time_base：
相邻差为 41/42 ms。末帧曝光取“容器总时长减最后 PTS”，此处为 42 ms；
直接采用末 packet 的 41 ms 会让总时长少 1 ms。

### 内存、尺寸与落脚点

五个状态共 1,082 个原始曝光。128×128 全解码约 67.6 MiB，已超过当前
64 MiB Pet Pack 预算。可维护的首版方案是明确记录的 2:1 时间采样：每两帧
保留第一帧，曝光相加；不合成中间动作。得到 543 帧，160×160 RGBA 共
55,603,200 字节，既保留完整原片时长，也落在现有预算内。这是接入选择，
不是作者原视频的原生 12 fps。

所有动作共用固定裁切矩形与等比缩放。六片在 alpha > 8 的可见像素联合
边界是 x=120…472、y=16…336；360×360 固定裁切 `(116, 0, 476, 360)`
覆盖这个范围。阈值这里只用于量测，**不要因此把输出 alpha 硬阈值化**。
VP9-alpha 的低 alpha 压缩噪声会让直接 `getbbox()` 返回完整 640×360。
源常量明确脚底线 `FEET_Y=330`；不能按帧内容重新贴底。
[源几何定义](https://github.com/PC2005-cloud/dsh-pet/blob/51041a7eb78e4b8e1df5c0a1dc4576ea481f8920/dsh-pet/src/shared/constants.ts)

| 文件 | SHA-256 |
| --- | --- |
| `待机呼吸休闲.webm` | `deb965d05a85dacf5ff4a20faa757846f0d11679598c3ec578a5571487660395` |
| `写代码.webm` | `0441287737cdbb993ce90dfa74c67ea4ea3549d8c8ea98946604668464589ed7` |
| `工作状态-思考冒泡.webm` | `b4a36cfa28ea5d7089e362a01972c6e880297c6dcd0d39f1994efd889a3c1be5` |
| `工作状态-雀跃庆祝.webm` | `3ff681051a0bb4f152d7535d64b7f3194c30298bf56d41e521216a278f135d3e` |
| `工作状态-垂头叹气冒汗.webm` | `ab00c844e62221905574b4c070e0d7b6fa14fb2afa1064c27a160f10e25f7196` |
| `原地左转奔跑.webm` | `79882aedd7b77caaacce1a34dece68e2f001a3dbfa5f9d049c1ce2fc04518d52` |
| 根 `README.md`（含素材条款） | `f000f5bbcce7a6d1b5304a592b6d2f05aad9fe5646a993c4ef8348c476811614` |

## 验证记录与边界

- 本机环境：Python 3.14、Pillow 12.3、Termux ffmpeg 8.1.3；未安装 DSH、
  Electron、Clawd on Desk 或浏览器渲染系统。
- Clawd Tank 五份 GIF：逐帧解码、透明度、帧数、曝光、源哈希通过；已检查
  静态接触表，发现并记录跨 clip 比例不同。
- DSH 六片：完整 VP9-alpha 解码、帧数与 PTS、容器时长、透明度、固定边界、
  源哈希通过；已检查六动作第 60 帧在灰底的接触表。
- 安装、runtime 状态映射、Termux:GUI 实播与用户观感属于后续集成验收，
  不由这些离线证据替代。
