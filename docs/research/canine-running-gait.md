# 犬类跑姿：原始研究核对

研究日期：2026-10-01。范围：为现有秋田犬跑步动画确定运动依据；本轮不替换图片、不规定新帧数或时长。下文将实验观察、文献模型与项目判断分开。

## 1. 先区分步态，不能要求所有狗都双腾空

| 主来源及定位 | 样本、条件 | 能支持的结论与局限 |
| --- | --- | --- |
| [Deban 等，2012，Methods，p.288；Figs.4–5，Discussion](https://carrier.biology.utah.edu/Dave%27s%20PDF/extrinsic%20appendicular%20walking%20trotting%20galloping.pdf) | 12 只混种犬，平均 25±1 kg；奔跑记录来自 9 只；水平跑台，gallop 4.43±0.12 m/s | 本实验 gallop 被明确分类为 **transverse**，前肢离地后进入腾空。肌电支持前肢的支柱作用、后肢的推进杠杆作用；肌电不是爪子轨迹，也不能直接作为图像关键帧。 |
| [Schilling 与 Carrier，2010，Methods；Summary；Figs.1–3](https://journals.biologists.com/jeb/article/213/9/1490/10266/Function-of-the-epaxial-muscles-in-walking) | 6 只混种犬，25±3 kg，跑台 gallop 约 4.6 m/s；两种后肢领腿比较样本缩至 4 只 | 记录 transverse gallop、同对肢体短暂共同支撑及收腿腾空。背肌招募与躯干矢状面伸展相符，沿躯干存在时序差异。可据此要求躯干和腿配合，不能推导秋田犬必须弯背多少度。 |
| [Walter 与 Carrier，2007，Methods、Table 1、Results](https://journals.biologists.com/jeb/article/210/2/208/17106/Ground-forces-applied-by-galloping-dogs) | 6 只成年犬，23.3–34.2 kg，包括拉布拉多、混种犬和威玛犬；跑道接近最大努力，平均 9.2 m/s | 此样本使用 **rotary**。这是高速犬类的直接证据，不是所有速度、所有体型的默认模板。 |

这些研究没有给出“秋田犬到某速度必然换步态”的通用阈值。当前角色的轻快感、夸张程度与周期长度仍须通过候选动画判断，不能用这些实验速度反推既定的 640ms 是生理标准。

## 2. 领腿、左右顺序与完整闭环

**领腿（leading limb）是同一对肢体中后触地的那一条；先触地的是 trailing limb。** 名称不代表“时间上第一个落地”。前肢、后肢分别判断，左右均指狗自身。[Hackert 等，2008，Introduction，作者稿 p.1，行 81–86](https://arxiv.org/pdf/0809.2415)

以下明确选择“右前肢为领腿”，使用 `LF/RF/LH/RH` 表示左前／右前／左后／右后。它是依据足序定义标侧的示例，不声称论文中的 Dog E 恰为这一侧。

| 足序类别 | 触地事件闭环 | 领腿关系 |
| --- | --- | --- |
| transverse gallop | `LH → RH → LF → RF → 下一轮 LH` | 前后领腿同侧：RF、RH |
| rotary gallop | `LF → RF → RH → LH → 下一轮 LF` | 前后领腿异侧：RF、LH |

前后两对肢体的左右触地次序，transverse 相同、rotary 相反。以上两行是**触地事件次序，不是四段互斥的单脚支撑，也不是等时间间隔**。[Walter 与 Carrier，2007，Introduction，Fig.1](https://journals.biologists.com/jeb/article/210/2/208/17106/Ground-forces-applied-by-galloping-dogs)

该文所述高速 rotary 的完整事件链可标为：

```text
LF 落 → RF 落 → LF 离 → RF 离
  → 收腿腾空
  → RH 落 → LH 落 → RH 离 → LH 离
  → 伸展腾空
  → 下一轮 LF 落
```

同对腿存在重叠接触；双腾空是这里的高速样例限定。[Walter 与 Carrier，2007，Introduction、Fig.1](https://journals.biologists.com/jeb/article/210/2/208/17106/Ground-forces-applied-by-galloping-dogs)

## 3. 动作不是四根腿摆动，也不是前后肢各做一件事

- 前后肢都有制动和推进分量，不能写成“前肢只接住，后肢只推进”。特别注意：摘要概括前肢净制动，但 Results 明确其净前后冲量与零无显著差异；Discussion 将此归因于试次有轻微加速，匀速下净制动是作者解释，不应改写为本实验已显著测得。[Walter 与 Carrier，2007，Results 与 Discussion 的 Forelimbs vs hindlimbs、Table 2](https://journals.biologists.com/jeb/article/210/2/208/17106/Ground-forces-applied-by-galloping-dogs)
- 奔跑时的背部动作与背肌顺序招募相联，不宜把胸、腰、臀整体设为同步机械上下平移。至于卡通需要保留多少屈伸，是美术判断；这篇肌电研究不提供可直接套用的网格变形量。[Schilling 与 Carrier，2010，Summary、Discussion](https://journals.biologists.com/jeb/article/213/9/1490/10266/Function-of-the-epaxial-muscles-in-walking)
- [Catavitello 等，2015，Figs.4–6](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0133936)观察到前、后肢节段角度协同有区别。它支持分别处理肘腕与膝踝的回收配合，不能把同一条腿的摆动曲线复制四份后仅错开时间。后一句是动画应用推论。

## 4. 阅读参考时需要保留的限定

### 运动分类与重心力学不是同一个标签

[Bertram 与 Gutmann，2009，§§4–6、Fig.5](https://pmc.ncbi.nlm.nih.gov/articles/PMC2696142/)指出，狗可以在不同重心转换方式下使用 rotary 足序。因此不能由“rotary”一词直接推出固定双腾空、固定弯背幅度。本文是力学解释；Fig.3 犬类曲线组合了不同犬与速度的数据，经过平衡条件调整，不是单只秋田犬实测轨迹。

还要区分：Deban 的 **forelimb-initiated aerial phase** 指前肢离地后进入腾空；Bertram 的 **forelimb-initiated transition** 指主腾空后由前肢落地开始重心方向转换，不能混用。[Deban，Methods p.288](https://carrier.biology.utah.edu/Dave%27s%20PDF/extrinsic%20appendicular%20walking%20trotting%20galloping.pdf)、[Bertram，§§3–5](https://pmc.ncbi.nlm.nih.gov/articles/PMC2696142/)

原文核对注意：Bertram §5 对 Fig.5 的 a/b 引用与图注对调；这里依图注、动作和完整论述判断，不将正文单个 a/b 当证据。

### PLOS 的图不能直接当接触相位规范

[Catavitello 等，2015，Methods、Fig.3A 及图注](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0133936)研究 3 只金毛、3 只拉布拉多，约 35 kg，户外自选速度、60Hz 无标记记录。作者称 gallop 为 transverse；但核对原图，黑条起始顺序显示 `HL → HL_contr → FL_contr → FL`，与前述 transverse 定义有疑点。图注黑条首先表示相对身体的后摆期，不能等同力板支撑证据。本项目不从这张图提取精确触地／腾空百分比，也不自行更正作者的数据。

### 不能固定所有狗都由某侧领腿

[Hackert 等，2008，Methods、Results、Discussion；Fig.1](https://arxiv.org/pdf/0809.2415)研究 5 只成年雄性马里努阿犬，2.2–10.3 m/s，观察到个体侧别偏好，没有据此建立全犬种统一左／右偏好。动画可选一侧完成稳定循环；持续每轮镜像换领腿没有此研究依据。后一项是制作建议。

## 5. 用于下一步的边界

1. 先选同体型、同速度感的**一段完整真实犬循环**，记录四脚落地与离地，再讨论改画。
2. 先看相位、支撑交接、关节回收和躯干响应；帧数不是动作正确性的证据。
3. 本次来源没有提供秋田犬专属的完整标定循环，不能用赛犬／猎豹极限姿态补齐这项缺口。
4. 本笔记提供生物力学依据，不替代现有角色神态、造型和原速可爱程度的对照验收。

## 6. 对当前秋田犬的具体判断与候选方向

### 现有八帧尚未证明什么

当前视觉基准仍是用户认可的 `d1b63b7`，运行代码和图片由 `59b3c3b` 恢复。`tools/audit_animation.py` 的八个阶段名是人工标签，四脚标记是画面中的脚掌中心；两者没有记录完整的落地／离地事件。透明图片也没有直接提供足底压力或实际地面接触信息。

此前看到 `01 → 02 → 03` 近侧前脚前伸、收回、再前伸，以及部分后脚相邻帧跨度较大。这些是需要复查的视觉线索；在确认脚的身份、遮挡、支撑阶段及身体相对位移前，不能仅由屏幕横坐标反向就断言步态错误。自动审计通过也不能证明自然。

### 建议试画的循环

为保留原稿开心、紧凑的形象，建议试画**中等速度感、带收腿腾空的 transverse gallop**。其生物学可行性见上文 Deban 与 Schilling 的犬类实验；速度感、收腿幅度和镜头侧别是本项目的美术选择，尚待候选稿比较。

保持原视角，固定近侧前、后肢为领腿。触地次序为：

```text
远侧后脚落地 → 近侧后脚落地 → 远侧前脚落地 → 近侧前脚落地
       ↑                                           ↓
       └──── 收腿腾空 ← 最后一只支撑前脚离地 ──────────┘
```

此图只规定触地顺序与选定的腾空位置，**不是完整接触时间轴**。各脚离地时刻、支撑重叠和时间比例要另行标定；箭头不表示均分周期。这个候选不强行插入后肢离地后的伸展腾空。若改用高速双腾空样式，须重新安排整个足序与身体响应，不能只多塞一张伸展图。

制作时落实四点：

1. **先画接触表。** 四行分别对应四只脚，标出落地、支撑、离地、摆动及遮挡；同一只脚不能在支撑途中突然回到前方。以匹配候选步态的完整真实犬循环为依据，不把多段不同步态拼成一轮。
2. **让受力传到躯干。** 后肢承重、伸展与前肢接续承重须有连续的胸髋响应；前肢也有支撑和推进过程。腿通过关节回收，避免整根腿绕一个点摆动。头部稳定程度、卷尾跟随幅度通过原速观感调整，不预设经验角度。
3. **明确原地跑的地面关系。** 虚拟世界中支撑脚近似固定，而身体前进，所以原地循环中该脚相对身体向后移动；离地后才回收、前摆。具体坐标关系见[动作规范](../animation-motion.md#原地奔跑的坐标关系)。近、远足底按镜头投影确定位置，不强迫四爪共用同一个屏幕 y 值。
4. **先看关键姿势，再加帧。** 先做带脚身份和接触说明的少量轮廓草稿，与批准原稿原速并排看，确认受力、轮廓和神态，再决定哪些间隔需要补画。当前 8 × 80ms 可作为比较节奏，但不是生物学规范；若接触节奏需要改变，明确记录原因。角色头身比例与体积感沿用批准原稿，不能通过逐帧整体缩放模拟身体屈伸。

下一步应交付接触表与关键姿势草稿。尚缺匹配当前卡通体型的完整参考循环及其逐脚标定，因此这里不编造精确离地时刻、关节角度或腾空占比。本轮仅研究与修正文档，未改运行帧、时序或部署。
