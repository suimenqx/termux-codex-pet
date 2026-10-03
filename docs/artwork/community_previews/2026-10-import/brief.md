# 五款社区素材的独立本地预览

任务：基于 main 的 `9625e05` 接入 `boba`、`mochi`、`golden_retriever`、`vpet`、`bongo_cat`，供用户在同一手机比较。原有 Akita、Robot、Pixel Dog 的文件、播放方式和默认选择不变。本次仅导入既有图像，不生成、重绘或推断缺失中间帧。源素材和输出保存在 Termux 私有目录，不作为仓库发行素材。

## 模型参照与固定布局（导出前确定）

| ID | 身份、尺度、姿势与布局参照 | 一致变换 | 时序来源 |
| --- | --- | --- | --- |
| boba | Petdex Boba 原始 1536×2288 RGBA WebP，8列11行，192×208格 | 全部格子原尺寸放入256方画布，偏移(32,24) | Petdex native sprite.zig |
| mochi | Petdex Mochi 原始1536×1872 RGBA WebP，8列9行 | 同上 | 同上 |
| golden_retriever | Petdex Golden Retriever，同Mochi网格 | 同上 | 同上 |
| vpet | LorisYounger/VPet 原版vup，1000×1000透明PNG；Default、快走、Think、Touch_Head 的原始阶段 | 整张固定缩至256×256；预乘alpha后LANCZOS，不逐帧裁边或居中 | 文件名最后一段毫秒数 |
| bongo_cat | Externalizable/bongo.cat 经典平面敲鼓猫；原猫、嘴、鼓、双爪图层与CSS桌沿 | 舞台800×450；固定crop(240,0,700,414)，上下补齐460方画布后统一缩至256 | 原版是按键事件；本地敲击循环明确属于接入设计 |

每包输出8位RGBA、sRGB解释、256×256画布、64dp视图；这是当前运行合同与本次集成布局选择，不是画质合格阈值。192×208源格不放大。保留源角色脸、毛色、服装、线条、镜头和肢体关系；没有新模型设定。原始图表的各姿势是本次 identity / scale / pose / layout 参照，精确来源URL与SHA256见 `sources.json`。构图原点固定为画布中心；动作位移完全来自源帧。不同角色并未校准成同一身高。

Bongo 原网页以白底表现身体，直接堆PNG会让身体透明。按原CSS加桌沿，以闭合边界恢复白色内部，外部保持透明；保留敲下爪子原有白色。桌沿采用4倍栅格抗锯齿，是可复现适配，不是逐像素浏览器截图。裁切会截断无限延伸的桌沿，但不裁手、猫和鼓。

## 角色与动作映射

- 三个Petdex角色：idle第0行6格；running第1行8格；needs_input第3行4格；ready第4行5格一次后idle；blocked第5行8格一次后保持末格。按上游native定义逐格曝光，完整时表写入pet.json。Boba额外两行视线不用于本轮。
- VPet：默认8帧循环；快走A两帧进入→B十帧循环；Think A两帧→B九帧循环；Touch_Head A两帧→B十一帧→C两帧→默认；blocked用Think A/B一次后保持。Running→Ready先播放快走C两帧，之后才进入Touch_Head。手势仅用于展示完成反应，不声称来自实际触摸输入。保留原顺序、曝光，不附加位移。
- Bongo：idle静态；running左敲100ms→抬爪80ms→右敲100ms→抬爪80ms；needs_input喵300ms→idle700ms；ready双敲160ms→idle160ms，重复一次后idle；blocked喵姿静止。所有时长为本地预览选择，没有奔跑动作。

四足接触轨迹和骨长没有重新设计或量化，本轮不会宣称修复源素材动作。首尾循环、透明边缘和64dp可读性需与真人屏幕反馈区分于文件验证。

## 来源和授权边界

Petdex页面/下载源并未为这三个具体素材给出已核实的通用再分发许可；项目代码MIT不能代替素材许可。Bongo README记录原作者对网站使用的允许，不等于任意跨应用再分发授权。VPet默认动画有独立使用声明，个人非商业使用保留原声明及来源链接；不能把代码许可证直接套用到动画。每个本地包保留CREDITS和相关声明，程序安装包和Git提交只含导入代码、来源记录、测试与文档。

来源：[Petdex](https://github.com/crafter-station/petdex)、[VPet](https://github.com/LorisYounger/VPet/tree/332933432a93b6daac90186d67be2356e71e75ff)、[Bongo Classic](https://github.com/Externalizable/bongo.cat/tree/591940644775d7cfd5167eceeeb6b97a1f9aadd4)。没有本次生成模型或提示词：全部来自原始素材。

## 导出和验收

`tools/import_community_previews.py --sources <已下载源目录> --output <全新输出目录>` 验证锁定源文件SHA256，导出五个包，生成每帧PNG/RGBA哈希和变换记录；不覆盖现有目录。`codex-pet pet import <包目录>`校验后复制到私有素材库，随后可通过`pet use`切换。素材库不依赖下载缓存或checkout，更新、回滚和卸载应用时保留。

2026-10-02（设备本地日期；UTC已为10月3日）验收记录：

| 项目 | 结果与边界 |
| --- | --- |
| 文件与清单 | 5包共146帧：31/31/31/48/5。每包独立256×256 RGBA，编译器解码、引用、时长和字节预算校验通过 |
| 可复现 | 同一源目录运行两次导出，五包全部文件逐字节一致；源定义和VPet声明核对了固定上游提交 |
| 实图 | 检查源图与导出工作动作联系表，确认像素画风、VPet原角色和Bongo白色内部；此静态检查不证明原速顺滑 |
| 回归 | 全套212项测试通过，mypy检查29个模块通过，git diff --check通过。新测试覆盖非法/冲突素材拒绝、源目录移除后仍可播放、发布失败回滚、实际CLI/IPC/PNG像素、安装/回滚/卸载保留本地包 |
| 真机 | ALN-AL10，API31，binding0.1.6/plugin7；已安装私有release并启动单daemon，PNG默认。五只分别隔离运行codex-pet test，全5状态成功、GUI ready、日志无新增错误，每次恢复Akita和位置(920,138) |
| 原有宠物 | Git中Akita/Robot/Pixel Dog素材和播放清单均无修改；新增素材独立存放，导入前后当前配置逐字节不变 |
| 人工 | 五只各20秒连续动作对比已完成，整个过程GUI ready并恢复Akita。试播期间位置从(920,138)改为(973,188)，保留新保存位置。画风偏好、拖动质量、深浅背景边缘与动作接缝尚无本轮用户结论，不记为通过 |

每包manifest指纹及自动验收摘要见 [verification.json](verification.json)。完整每帧指纹保存在本地包的import-record.json。原始下载位于`~/.cache/codex-pet/nonpixel-research/`，两次导出在`community-preview-packs/`、`community-preview-reproduced/`，安装后的独立副本在`~/.local/share/codex-pet/pets/`。设备记录为`~/.cache/codex-pet/community-device-<id>.json`，全测试日志为`community-preview-tests.log`，连续试播记录为`community-gallery.json`。

授权范围和人工观感边界不因这些自动检查而改变。新素材供本机试用，不宣称已经改善了原秋田犬奔跑，也不把高清源图称作非像素或顺滑。
