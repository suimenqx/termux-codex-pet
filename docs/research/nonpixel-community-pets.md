# 非像素桌宠素材：社区项目与复用边界

调查日期：2026-10-02（America/Los_Angeles；API 抓取时间为
2026-10-03 00:30–00:39 UTC）。本轮只找素材、检查原始文件和授权，不改现有
Akita、Robot、Pixel Dog、宠物选择或 renderer。

用户已接受 Pixel Dog 的动作，但不喜欢手机上的像素画风。筛选条件因此是
**现成非像素角色 + 已完成的连续动作 + 可核对的素材来源**，不是重新生成帧。
GitHub Star 只能说明项目受关注，不能证明某一角色的动画质量、作者身份或
可再分发权限；引擎许可证也不自动等于第三方素材许可证。

## 已核对的社区方向

Star 为调查时 GitHub REST API `stargazers_count` 的实测值，后续会变化。

| 项目 | Star | 已找到的动作材料 | 对当前需求的判断 |
| --- | ---: | --- | --- |
| [VPet](https://github.com/LorisYounger/VPet) | 6,853 | 默认角色透明 PNG，左右步行、快走、爬行、睡眠、工作等目录 | 如果接受 Q 版人形，最值得先看；不要把快走目录称为四足奔跑 |
| [BongoCat](https://github.com/ayangweb/BongoCat) | 23,747 | Live2D 猫模型、表情、敲键盘/鼠标/手柄交互 | 适合把“工作”表现成敲击；本轮没有找到成套奔跑帧 |
| [Awesome-BongoCat](https://github.com/ayangweb/Awesome-BongoCat) | 2,088 | 社区模型目录，含作者链接及模型下载 | 适合选外形；每个模型要单独核对授权和动作 |
| [Shijima-Qt](https://github.com/pixelomer/Shijima-Qt) | 200 | Shimeji 默认白色角色、PNG 和动作 XML | 格式易转，但默认 Run 只有 3 张不同画面，不是本轮平滑度优先项 |
| [DyberPet](https://github.com/ChaozhongLiu/DyberPet) | 989 | Kitty / ChrisKitty 示例和 JSON 动作配置，社区角色入口 | 仅保留社区索引线索；已追到的 Desktop-Cat 上游标为像素画，不推荐默认猫 |
| [CubismWebSamples](https://github.com/Live2D/CubismWebSamples) | 390 | 官方 Wanko 狗 Live2D 模型，有 idle / shake / touch 文件 | 外形方向可参考，不能当成已完成的奔跑素材包 |

统计来源分别是各项目的 GitHub API：
[VPet](https://api.github.com/repos/LorisYounger/VPet)、
[BongoCat](https://api.github.com/repos/ayangweb/BongoCat)、
[Awesome-BongoCat](https://api.github.com/repos/ayangweb/Awesome-BongoCat)、
[Shijima-Qt](https://api.github.com/repos/pixelomer/Shijima-Qt)、
[DyberPet](https://api.github.com/repos/ChaozhongLiu/DyberPet)、
[CubismWebSamples](https://api.github.com/repos/Live2D/CubismWebSamples)。

## VPet：可以转换现成 PNG，但角色和授权要说清楚

核对固定提交 `332933432a93b6daac90186d67be2356e71e75ff`。默认角色是
Q 版人形，源目录 `VPet-Simulator.Windows/mod/0000_core/pet/vup/` 已有
Default、Sleep、WORK、Think、Touch 等动作。MOVE 下有左右步行、快走、慢走、
攀爬、爬行、下落；本轮没有在该 MOVE 清单发现独立 `run` 目录。
[原始素材树](https://github.com/LorisYounger/VPet/tree/332933432a93b6daac90186d67be2356e71e75ff/VPet-Simulator.Windows/mod/0000_core/pet/vup)

具体到 `MOVE/walk.left.faster/B_Happy`，文件清单是 10 张 PNG，文件名的
曝光值均为 125；普通 `MOVE/walk.left/B_Nomal` 是 6 张。
本机下载普通左走首帧，用 Pillow 解码为 **1000×1000 RGBA**，文件大小
116,846 字节。上游 `PNGAnimation.cs` 解析文件名最后一个 `_` 后的数值，
并用毫秒 `Thread.Sleep(Time)` 播放，故这里的 125 可解释为 125 ms，
无需猜测或自行均匀补帧。
[快走原帧](https://github.com/LorisYounger/VPet/tree/332933432a93b6daac90186d67be2356e71e75ff/VPet-Simulator.Windows/mod/0000_core/pet/vup/MOVE/walk.left.faster/B_Happy)、
[播放器源码](https://github.com/LorisYounger/VPet/blob/332933432a93b6daac90186d67be2356e71e75ff/VPet-Simulator.Core/Graph/PNGAnimation.cs)

代码仓库标为 Apache-2.0，**默认动画另有声明**：权利归虚拟主播模拟器制作组。
非商用须告知来源并链接上游；再分发须保留全部授权说明、链接，不能对动画
分发收费。商业用途还有首次弹窗、易访问的来源说明、不得出售动画获利和联系
作者等要求。第三方 MOD 不在默认动画声明范围内。这里记录上游要求，不把
它简化为“Apache 素材可随便用”。
[动画版权声明](https://github.com/LorisYounger/VPet/blob/332933432a93b6daac90186d67be2356e71e75ff/README.md#动画版权声明与授权)

接入判断：若用户选中该画风，离线导出一个新 Pet Pack 即可；按原始 A/B/C
阶段和时间组织 clip，避免只截一段导致首尾或退出跳变。不需要移植 WPF，
不需要替换 Termux:GUI。尚未做整套导出或手机观感验收。

## BongoCat：热门的非像素工作伴侣，动作主题与奔跑不同

核对固定提交 `e5922f3c71716ba06531324f4ab5f8066b2cc487`。
官方 README 明确描述 Live2D 猫跟随鼠标并响应键鼠、手柄，模型目录也确有
`.moc3`、贴图、表达式和 motion JSON；这是参数化模型，不是可直接按序裁切
的奔跑 atlas。
[README](https://github.com/ayangweb/BongoCat/blob/e5922f3c71716ba06531324f4ab5f8066b2cc487/README.md)、
[默认模型](https://github.com/ayangweb/BongoCat/tree/e5922f3c71716ba06531324f4ab5f8066b2cc487/resources/models)

如果用户喜欢敲键盘猫，`working` 可以表现为敲击，`idle` 为等待或呼吸，
无需强迫每个宠物都奔跑。这个语义映射是本项目的设计建议，上游并未提供
Codex 状态契约。现有引擎代码保持不变，可先考虑在许可允许后离线烘焙有限
动作；该导出路径本轮尚未运行验证，不能称为已经可以安装。

当前仓库代码声明 Apache-2.0；官方社区素材表列出不同作者，其中经典小键盘
模型署名 MMmmmoko。列表不是统一素材许可证。该项目自己的 Cubism 说明也
区分 Core、Framework 和可扩展应用发布条件。不能从仓库 LICENSE 推断所有
猫皮肤、Live2D 模型或角色形象已经获得本项目再分发许可。
[代码许可](https://github.com/ayangweb/BongoCat/blob/e5922f3c71716ba06531324f4ab5f8066b2cc487/LICENSE)、
[作者和模型目录](https://github.com/ayangweb/Awesome-BongoCat/blob/b939396cf88ff798878a9089d55019e6a7e90925/README.md)、
[Cubism 许可边界说明](https://github.com/ayangweb/BongoCat/blob/e5922f3c71716ba06531324f4ab5f8066b2cc487/docs/cubism/cubism-sdk-source-and-license.md)

## Shimeji / Shijima：不能凭兼容格式认定动画优质或授权完整

核对 Shijima-Qt 固定提交 `57723f1d7a4ea4a32e5fbb90deb7febc0dd49f63`。
默认角色包含 46 张 PNG；动作 XML 的 Walk、Run、Dash 都用
`shime1 → shime2 → shime1 → shime3`，改变速度和曝光而非增加动作姿势。
因此 **Run 虽有 4 次曝光，只有 3 张不同图片**；XML 的 Duration 是引擎时间
单位，本轮没有将其擅自当作毫秒。
[默认动作 XML](https://github.com/pixelomer/Shijima-Qt/blob/57723f1d7a4ea4a32e5fbb90deb7febc0dd49f63/DefaultMascot/actions.xml)

Shijima-Qt 已于 2026-04-29 归档，README 说明停止维护。它可作为 Shimeji
素材格式入口，而不是建议在 Termux 上再装一个 Qt 桌宠系统。
[维护状态](https://github.com/pixelomer/Shijima-Qt/blob/57723f1d7a4ea4a32e5fbb90deb7febc0dd49f63/README.md)

其 GPL-3.0 项目许可不自动证明网上任意 Shimeji 角色均可打包。实际存在明确
禁止二次分发的画师作品，例如 YuenC2 的凹凸角色在作者 README 中保留这一
限制；这类包本轮排除。默认角色的独立素材授权和源作者链也未完成核对，
所以不将它列为“现在就能随项目分发”的已通过选项。
[具体作者要求](https://github.com/YuenC2/auto-shimeji/blob/master/README.md)

## DyberPet：可以继续找猫，但要追到原始素材

固定源码树为 `012dbbc72046de6042e46643cb0fa83098d58f6d`。
Kitty 的 `pet_conf.json` 配置宽高 98×98，包含站立、左右行走、生气、入睡等
动作引用；配置名本身不能证明素材是高清非像素，也不能证明存在奔跑周期。
[Kitty 配置](https://github.com/ChaozhongLiu/DyberPet/blob/012dbbc72046de6042e46643cb0fa83098d58f6d/res/role/Kitty/pet_conf.json)

README 明确说明 Demo 的部分素材来自
[daywa1kr/Desktop-Cat](https://github.com/daywa1kr/Desktop-Cat)，同时有
[社区角色目录](https://github.com/ChaozhongLiu/DyberPet/blob/012dbbc72046de6042e46643cb0fa83098d58f6d/docs/collection.md)。
旧 Desktop-Cat 链接当前跳转至
[1ilit/Desktop-Cat](https://github.com/1ilit/Desktop-Cat)，上游项目自带 `pixel-art`
标签，所以这条默认猫素材线不满足本轮画风目标。主仓库 GPL-3.0、Desktop-Cat
根目录 MIT 都不应代替逐包作者记录；本轮尚未
查清每个 Kitty 帧的原始画师权利链或验证动作循环。暂作为素材线索，不因
接近千 Star 就升级为已验收方案。
[作者致谢](https://github.com/ChaozhongLiu/DyberPet/blob/012dbbc72046de6042e46643cb0fa83098d58f6d/README.md#致谢)

## 官方 Live2D Wanko：画风备选，不能承诺现成奔跑

核对 CubismWebSamples 固定提交 `b1de66b0b1f1cb881d95fb6158622aeb6a2827bd`。
Wanko 目录有 12 个 motion JSON（4 idle、2 shake、6 touch），但
`Wanko.model3.json` 默认只引用 3 个 Idle 和 2 个 TapBody。目录与该映射中
没有发现 walk/run 动作。模型的 1024 贴图是部件纹理，不是完整动画帧。
[模型目录](https://github.com/Live2D/CubismWebSamples/tree/b1de66b0b1f1cb881d95fb6158622aeb6a2827bd/Samples/Resources/Wanko)、
[默认动作映射](https://github.com/Live2D/CubismWebSamples/blob/b1de66b0b1f1cb881d95fb6158622aeb6a2827bd/Samples/Resources/Wanko/Wanko.model3.json)

官方 LICENSE 将 Wanko 列入 Free Material License；Framework、Core、素材
分别适用不同条款，官方样例角色还需遵守对应角色约定。采用它前要确认预期
使用和导出形式，不把 “Free” 写成 CC0，也不为了找一只宠物引入完整 Live2D
运行时。
[仓库许可分类](https://github.com/Live2D/CubismWebSamples/blob/b1de66b0b1f1cb881d95fb6158622aeb6a2827bd/LICENSE.md)、
[官方素材许可](https://www.live2d.com/eula/live2d-free-material-license-agreement_en.html)、
[官方样例及角色条款](https://www.live2d.com/en/learn/sample/)

## 实图核查与本轮接入

完整查看了 Boba（1536×2288、8×11）、Mochi 和 Golden Retriever
（1536×1872、8×9）的透明 WebP。三个源格均为192×208，具有明显像素
轮廓，分辨率高不代表非像素画风。它们不满足最初的非像素筛选偏好，但用户
随后明确要求一并接入以便看效果，因此保留原图制作独立预览。

Bongo 实际接入采用 Externalizable/bongo.cat 的经典敲鼓版本，而不是上文
ayangweb 的 Live2D 版本。原始图层、CSS桌沿、身体透明适配和真实姿势均已
查看；敲击时序由本地集成定义。VPet 使用原版vup的默认、快走、思考、摸头
帧和源文件曝光时长，不引入WPF或Live2D运行时。

五个独立包共146帧，具体来源哈希、统一变换、角色映射、授权边界、导出和
设备验收记录见[本次制作单](../artwork/community_previews/2026-10-import/brief.md)。
图片留在Termux私有目录；仓库提交可复现的导入工具和来源记录。现有宠物的
图像和动作没有替换；新增本地素材库接口复用既有runtime/renderer。
