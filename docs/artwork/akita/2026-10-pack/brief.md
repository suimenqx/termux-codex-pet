# Akita Pet Pack 迁移制作记录

任务：#9，基线 `c7edbfa125e20599d1ae3500f822201e4aba8cfc`；本次仅将已有时间表和眨眼合成搬入数据包。没有生成、重画、缩放、重新居中或更改姿势；生成工具、提示词、批次和新模型标识不适用。

沿用 [当前模型与动作制作单](../2026-10-continuity/brief.md) 的身份、尺度、项圈、视角、锚点、动作极值和肢体参照，画布仍为 256×256、8 bit 直通 alpha RGBA、sRGB，显示仍为 64×64 dp。所有既有源图字节保持不变。既有步态待修复项仍然有效，本次性能和像素测试不能证明步态改善。

唯一新增文件为 `codex_pet/assets/akita/derived/ready-blink.png`，原 `idle/00` 作为姿势、身体与布局参照，原 `idle/02` 只提供眼部补片。来源文件 SHA-256、矩形、输出文件和 RGBA 指纹见 [derived-blink.json](derived-blink.json)。矩形为半开区间 `[58,54,198,116]`，逐行复制四通道，不混合；区域外完全保留底图。该记录替代新增模型测量：没有新的模型、肢体位置或尺度需要校准。

确定性导出命令：`python tools/export_derived_blink.py /tmp/ready-blink.png`。编码器迁移后 PNG 压缩字节可能不同，验收以解码 RGBA 指纹和区域外逐像素一致为准；首次交付的 PNG 指纹仍保留。

本历史迁移包记录当时的时序：`assets/akita/pet.json` 定义 Running 十帧 640 ms；同宠物 Running→Ready 360 ms 收步后接 940 ms 轻跃，再进入 4380 ms 休息循环。眨眼为休息循环第 3 次曝光、200 ms。当前 Running 已由 [2026-10 Grok v2 循环](../2026-10-grok-v2/brief.md) 取代；本包的时间表只用于历史复现。

文件、时长、合成结果和徽标以独立旧基线的 1080 条路径/8694 次曝光校验；设备与自动检查结果记录在 [实施证据](../../../../research/implementation-status.md)。新生产链路的人工观感验收仍 pending；原图及历史记录不改写为本次通过证据。
