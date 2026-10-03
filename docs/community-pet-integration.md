# 社区现成 Pet 的直接集成经验

本文记录 `8699456` 接入 Boba、Mochi、Golden Retriever、VPet 和 Bongo Cat
Classic 的经验，供下一次复用社区成品时直接照着做。范围是查找来源、识别
素材格式、转换现有资源、独立安装和验证；角色绘制、AI 生成、补帧和动作
重做不属于这条接入路径。

本次有效的做法是：**先看上游真实动作，再把选中的现成资源转换为本项目
Pet Pack；运行时继续复用已有状态、播放、渲染和触摸代码。** 上游项目的
知名度用于发现候选，具体素材的实际观感决定是否值得接入。

## 1. 已经落地的五个实例

| 本地 ID | 实际采用的来源与材料 | 本次工作状态的表现 | 导入的独立帧 |
| --- | --- | --- | ---: |
| `boba` | Petdex Boba，8列11行 WebP 图表 | 原第1行的横向移动动作 | 31 |
| `mochi` | Petdex Mochi，8列9行 WebP 图表 | 原第1行的横向移动动作 | 31 |
| `golden_retriever` | Petdex Golden Retriever，8列9行 WebP 图表 | 原第1行的横向移动动作 | 31 |
| `vpet` | LorisYounger/VPet 默认 vup 角色的透明 PNG 序列 | 原版人形快走 | 48 |
| `bongo_cat` | Externalizable/bongo.cat 经典网页的猫、嘴、鼓和双爪图层 | 交替敲鼓 | 5 |

这五个 ID 是可独立切换的本地包，共146帧。Akita、Robot、Pixel Dog 仍然
保留。Bongo 实际使用的是经典平面敲鼓版本，不能把它写成已经移植了
ayangweb/BongoCat 的 Live2D 桌宠。

来源链接、固定提交、下载地址及 SHA256 以
[来源锁定表](artwork/community_previews/2026-10-import/sources.json)为准；
转换细节见[本次接入记录](artwork/community_previews/2026-10-import/brief.md)。
[社区调查](research/nonpixel-community-pets.md)还记录了未采用候选；其调查期
“尚未导出”的描述是历史状态，五包的最终结果以上述接入记录为准。

## 1.1 第二批：从五包脚本收敛到配方

之后扩展了六类来源、13个独立本地包：RunCat、Clawd Tank、VS Code Pets六款、
eSheep/Buster Bunny/Pingus、ArkPets阿米娅、DSH蓝毛小女仆。完整ID、命令和维护方式见
[社区配方指南](../community_pets/README.md)。这里的“全部”覆盖六类来源及上述代表角色，
不是下载VS Code Pets、desktopPet或Ark-Models所有角色。

这次的可复用边界是`tools/pet_import/pipeline.py::build_recipe()`：来源SHA、状态映射、
固定画布和署名写在JSON；真正的格式差异放在decoder；写包与第一批共用一个实现。
第一批五包重新导出与原结果逐文件一致，没有因重构改变现有宠物。

新增经验来自实际输入，而不是给每个项目写一套运行时代码：

- GIF必须处理disposal及嵌入曝光；文件名8fps并不准确。Clawd各GIF身体比例不同，
  校准只能每片段固定一次。Totoro原run是猫巴士，DSH原跑步有趴下，不能承诺成匀速步态。
- eSheep XML有命名空间、内嵌PNG及重复曝光；现有alpha不能被简单色键遮罩覆盖。
  只实现已核实的固定曝光子集，随机/物理脚本仍由本项目的语义状态取代。
- DSH透明WebM默认ffmpeg解码会丢alpha，必须libvpx-vp9；逐帧时长取PTS差及容器尾部，
  两帧取一时合并曝光，不能只用包内整数duration累积。
- 阿米娅可在Termux用官方Spine3.8+原生Canvas离线导出。PMA恢复、mesh绘制、统一五动作
  视野和超采样缺一不可；不支持的附件/混合直接报错，不声称通吃所有模型。
- 去重的是RGBA内容和文件，保留全部曝光序列。最大单包DSH约53MiB，按解码预算验收。
- 源许可需追到图片：Clawd on Desk限制跨应用使用，因此明确换MIT的Clawd Tank；
  企鹅保留Pingus GPL/作者，而非误套desktopPet的MIT。旧编码署名也必须正确解码保留。

构建失败不发布半成品，已有ID拒绝覆盖；源损坏会明确报错。原文件、npm依赖与导出图片
保存在私有缓存，公开仓库只有配方/工具/记录。实际来源和验证见
[本批brief](artwork/community_previews/2026-10-popular/brief.md)和
[验证摘要](artwork/community_previews/2026-10-popular/verification.json)。

## 2. 搜索到热门项目之后，先检查什么

下一次按“项目 → 具体角色 → 原始文件 → 原始播放定义”的顺序查。第一轮
拿到少量可播放样例就让用户看，选定候选后再批量下载和转换。

| 检查 | 本次实际发现 | 接入决策 |
| --- | --- | --- |
| 真实画风 | Boba、Mochi、金毛的图表分辨率不低，实际仍有像素轮廓 | 直接展示源图；不能根据尺寸承诺非像素效果 |
| 真实动作 | VPet 有人形快走；Bongo 以敲击为主题 | 接受不同工作表现，保留其现成动作 |
| 可取出的资源 | atlas、独立 PNG、分层 PNG 都有明确转换路径 | 优先沿用已验证的离线转换方式 |
| 只有模型或应用安装包 | Live2D 的 `.moc3`、贴图和 motion 文件不是完整逐帧图像 | 另列研究任务；本次未验证 Live2D 烘焙或运行时 |
| 实际曝光次数 | Shimeji 示例的4次曝光只用了3张不同图片 | 不把帧数、Star 或宣传 GIF 当成流畅度结论 |
| 素材归属 | 代码许可证与角色图片条款可能不同，社区列表还会引用第三方作者 | 追到具体素材的出处和使用说明 |

本次三个像素风候选最初不符合“非像素”偏好，但用户随后明确要求一并
接入比较，因此保留原貌导入。筛选不合偏好与技术上无法接入是不同结论。

授权记录也应区分范围：VPet 默认动画有单独声明；Petdex 这三个角色及
Bongo 图像的通用再分发权限，本次未核实完整。因此五包保存在本机，公开
仓库提交工具、来源和验证记录。**本地保存不等于已经确认所有使用授权**，
以后公开打包素材时仍需核对具体作者条款。

## 3. 三类材料，各自用什么接入方式

### WebP atlas：读取上游布局和播放器

Petdex 原始 `pet.json` 描述的是上游 sprite，不能原样交给本项目的
`pet import`。先由转换工具生成本项目的 `schema_version: 1` 清单。

本次读取上游 `sprite.zig` 的行号、有效格数和逐格毫秒数，不能把一行所有
格子都当有效帧，也不能凭“看起来10fps”统一改时长。三包源格均为192×208，
离线拆分后原尺寸放入256×256透明画布；Boba多出的视线行本轮未用。

WebP 在这里是**源文件格式**。当前应用仍读取转换后的 PNG-directory 包，
正式 renderer 仍使用已部署的 PNG 路径。接入这些 WebP 素材没有启用共享
buffer，也没有增加 WebView、GLES 或新的 Android app。

### 独立 PNG 序列：同时读取阶段和时长

VPet 有现成透明帧。上游播放器以文件名最后一段数值作为毫秒时长，本次
据此保留原顺序和曝光；进入、循环、退出阶段分别映射为 clip。快走采用
A进入→B循环，Running→Ready先用C退出，再接原摸头动作作完成反应。

整个原画布统一缩小即可，不需要移植 VPet 的 WPF 程序。保留阶段信息比
只抽取几张好看的姿势更重要；退出片段不能误设为无限循环。

### 原始图层：还原它依赖的宿主环境

Bongo 原网页依赖白底和 CSS 桌沿。直接叠加透明 PNG 时，身体内部也是
透明的，而敲下的爪子带白色块，在深背景上会出现不一致。

本次按原层序合成，先恢复 CSS 桌沿以闭合轮廓，再从所有图像边缘识别外部
透明区域，只给封闭内部补白。没有桌沿时，身体会与外部连通，直接去白底
会把身体一起去掉。五种姿势统一采用同一个裁切区域，避免敲击时整体跳位。
精确坐标和实现保存在接入记录及转换工具中。

原版 Bongo 是按键按下/释放驱动，没有连续敲鼓的官方循环时长。本次交替
敲击的时序明确记为集成选择，不冒充上游原时序，也没有新增奔跑动作。

## 4. 接入应修改哪些边界

```text
上游图表 / PNG序列 / 原图层 + 播放定义
  → 离线转换工具
  → 本项目 pet.json + 引用的PNG + 来源记录
  → codex-pet pet import
  → 本地素材库 → PetRuntime → FrameSource → Termux:GUI
```

这次新增本地素材库后，再接同类角色通常只需要新增转换配方和包数据。
不要为每只宠物给 GUI、事件适配器或会话状态机增加专用分支。

| 文件 / 边界 | 已承担的职责 | 下一次如何复用 |
| --- | --- | --- |
| [import_community_previews.py](../tools/import_community_previews.py) | 五个已知素材的下载校验、转换、动作映射和导出记录 | 作为已验证实例；它不是自动识别任意社区包的通用转换器 |
| [local_pets.py](../codex_pet/local_pets.py) | 校验、受锁保护的暂存复制、发布目录和目录索引，失败清理 | 调用 `pet import`，不要手工伪造 catalog 或覆盖安装文件 |
| [pets.py](../codex_pet/pets.py) | 合并内置目录与本地轻量元数据 | 新本地包不必加入 `APPEARANCES`；内置发行素材才走该目录 |
| [pet_pack.py](../codex_pet/pet_pack.py) | 编译同一种数据合同，解析两种存放位置 | `bundled_pack()`沿用兼容名称，也能解析本地包 |
| `cli.py` / `preferences.py` / `daemon.py` | 导入入口、列表、持久化选择和即时切换 | 通过现有命令使用，不另造控制通道 |
| `pet_runtime.py` / `frames.py` / `renderer/` | 状态播放、帧准备、原生显示与拖动 | 五包直接复用，接入时没有修改这些运行逻辑 |

当前素材包中的 `roles` 必须覆盖 `idle`、`running`、`needs_input`、`ready`、
`blocked`。其中 `running` 表达业务正在工作，可以选择快走或敲鼓。
`ready` 的图像片段结束后可以进入休息循环，业务状态仍保持 Ready。

当前 v1 视图固定为64×64dp；源图高分辨率不意味着屏幕角色会变大。
内置 Pixel Dog 的画布为64×64，五个社区包为256×256。导入器还验证帧路径、
图片解码、尺寸、clip引用和预算；精确规则以 `pet_pack.py` 为准。
本轮运行依赖仍为 Python、Pillow、termuxgui 及 Termux:GUI 原生插件。

## 5. 可直接复用的操作顺序

本机已经安装这五包时，直接 `codex-pet pet list` 和 `pet use <id>` 即可。
下面是从干净输出目录复现的命令，在仓库根目录执行。`--download` 只下载
锁定表中缺失的原始文件，已有源文件也必须通过 SHA256；输出目录必须不存在。

```sh
python tools/import_community_previews.py \
  --sources "$HOME/.cache/codex-pet/community-sources" \
  --output "$HOME/.cache/codex-pet/community-packs" --download

codex-pet pet import "$HOME/.cache/codex-pet/community-packs/vpet"
codex-pet pet list
codex-pet pet use vpet
```

其余生成包分别位于 `boba`、`mochi`、`golden_retriever`、`bongo_cat` 目录，
按同样方式导入。不要重复导入已经存在的 ID；拒绝覆盖是预期保护。
若安装版本尚无 `pet import`，先从支持本地包的源码运行 `bash ./install.sh`。
已经支持该功能的运行版本，导入和切换新数据包无需重新安装应用。

本地 ID 接受 `[a-z][a-z0-9_]{0,63}`。例如上游 `golden-retriever` 在本项目
使用 `golden_retriever`。同一 ID 不可覆盖，修改素材时生成新版本 ID，
例如 `vpet_preview2`；原版本保持可选，编译和帧缓存也不会混用新旧内容。

三个目录承担不同职责：

| 位置 | 内容及生命周期 |
| --- | --- |
| `~/.cache/codex-pet/` 中的下载、导出目录 | 复现和排查用的源文件与中间结果；需要长期保留的来源应另行归档 |
| `~/.local/share/codex-pet/pets/<id>/` | 独立安装副本；不依赖下载目录和 checkout；更新、回滚、卸载程序都会保留数据 |
| `~/.config/codex-pet/config.json` | 当前选择和保存位置；导入不修改它，`pet use` 才切换选择 |

回滚到支持本地包的程序版本才能继续使用这些包；更早版本即便保留目录也
不会因此获得识别能力。卸载保留素材不意味着卸载后还能执行应用命令。

每包保留 `CREDITS.md`、适用的 `LICENSE.txt` / `LICENSE.md` 和
`import-record.json`。导入器只复制清单引用的图像及规定的来源文件，不复制
整个上游仓库。新接入工具也应保留 URL、提交或源哈希、映射和输出指纹。

## 6. 怎样确认“已接入”，怎样确认“好看”

本次经验是分开记录四类证据，避免反复烧时间在已经验证过的层上。

| 层次 | 实际检查 | 能说明的结果 |
| --- | --- | --- |
| 源与转换 | 实图、真实alpha、完整动作定义；同源导出两次逐字节比较 | 源材料明确、转换可复现 |
| 程序集成 | 非法包拒绝、重复ID拒绝、发布失败回滚；真实CLI/IPC输出像素；移走源目录仍可播放；安装/回滚/卸载保留数据 | 独立包正确进入现有运行路径 |
| 真机运行 | 安装版本、GUI状态、每包隔离执行五状态检查、日志、恢复旧选择 | 当前手机上这条运行路径可用 |
| 人工观感 | 原速持续动作、首尾衔接、画风、实际大小、深浅背景与拖动 | 只能据用户具体反馈记录接受、问题或未测 |

导入后的离线预览可以直接走生产清单，先确认原顺序和时长：

```sh
python tools/preview_animation.py --pet vpet --state running --cycles 2 \
  --output "$HOME/.cache/codex-pet/vpet-running.html"
python tools/preview_animation.py --pet vpet --state ready --from-state running \
  --output "$HOME/.cache/codex-pet/vpet-finish.html"
```

HTML 使用的 CSS 尺寸不等于 Android dp；手机观感仍需真人确认。不要把
Akita专用脚掌标记、步态阈值套到人形或敲鼓猫上。

本次接入已通过212项完整测试、29个模块的mypy检查、五包各自的隔离
`codex-pet test`，以及每包20秒的连续试播。原素材和导出记录可复现；
当前没有这五包的逐项人工美术验收结论。
[验证摘要](artwork/community_previews/2026-10-import/verification.json)保留了范围。
之前 Pixel Dog 的“动作可以接受、像素画风不好看”反馈只适用于 Pixel Dog。

### 会话与自动恢复的实际坑

`codex-pet test` 有其他会话时，显示优先级会干扰结果。只能临时隔离自己
明确拥有的会话，不要结束用户的其他会话。保留必要的 turn ID 并在
`finally` 恢复；聚合 status 不是所有会话的完整备份。

本次发现：工具调用提前返回后，Codex 的 PostToolUse 会重新加入当前会话，
导致测试中途失去隔离。解决方式是让约19秒的单包测试在一次等待足够长的
工具调用内结束，并在返回前断言 `session_count == 0`，再恢复自己会话。
后台提前返回加频繁轮询，不能作为同等的隔离证据。

临时多包试播要有有限时长和 `finally` 恢复，并识别试播期间的手动选择。
本次恢复了原来的 Akita，同时保留试播中真实拖动后新保存的位置；不能为了
声称配置未变而覆盖用户刚做的操作。触摸计数和新坐标证明收到事件，不能
单独证明抓取点跟手、多指或锁屏行为都已被人确认。

## 7. 下一只社区 Pet 的最小交付

1. 交付具体角色的源链接、实际动作样例和素材条款记录；明确它表现什么动作。
2. 锁定本次使用的源版本，选已验证的 atlas / PNG序列 / 图层转换路线；
   遇到模型烘焙等未验证依赖，单独说明，不承诺已可直接导入。
3. 生成独立新 ID 的本项目包，保留原播放定义和来源；显式记录必要的语义映射。
4. 校验并导入，确认旧包、原选择、保存位置以及移除下载目录后的使用不受影响。
5. 在不干扰其他会话的前提下检查状态，再给用户一段有名字、有时长的原速试播。
6. 交付 `pet use <id>` 切换命令、恢复原宠物的命令和验证记录。只有明确获得
   再分发依据的素材才考虑进入内置发行包；本地试用包不自动转成公开素材。

下一轮应先让用户选定现成动作与画风，再扩展该角色的状态覆盖。运行检查
已经通过而用户仍不喜欢时，优先换候选或明确具体观感问题，避免重做已经
跑通的 renderer、重新调研全部依赖，或未经要求转入动画生成。
