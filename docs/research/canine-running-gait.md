# 犬类跑姿：当前基线的参考边界

犬类步态研究只用于理解支撑、腾空、回收和领腿等概念，不直接提供本角色的
像素坐标、关节角度或固定周期。当前秋田犬 Running 以角色可读性、体量和原速
观感为准，生产帧、时序和脚掌采样点见
[`docs/animation-gait.md`](../animation-gait.md) 与
[`docs/artwork/akita/current-running.json`](../artwork/akita/current-running.json)。

## 可借鉴但不能照搬的结论

- 犬只可使用 transverse 或 rotary 等不同疾驰足序，不能假设所有犬只共享一个
  固定左右顺序。
- 前后肢都参与制动、支撑和推进；不能把前肢只画成接住身体、后肢只画成蹬地。
- 躯干、胸、腰和髋存在时序响应；卡通动作需要保持结构连续，但研究数据不能
  直接决定本角色的夸张幅度。
- 同对肢体可能有短暂共同支撑，遮挡、视角和速度会改变可见轮廓；不能从一张
  侧视图推导完整接触力学。

## 当前制作边界

当前 v2 是一套已经接入的 20 帧透明循环，不是犬类运动捕捉或生物力学认证。
审计工具只检查记录的显示采样、帧序和曝光；自动通过不能替代原速播放和设备
人工观察。未来若更换动作，应先确定完整的脚掌身份/接触表，再制作关键姿势，
并重新更新 `current-running.json`，不能只增加帧数或套用研究中的足序。

参考研究：

- [Deban 等，犬类行走、疾驰与肌电](https://carrier.biology.utah.edu/Dave%27s%20PDF/extrinsic%20appendicular%20walking%20trotting%20galloping.pdf)
- [Schilling 与 Carrier，犬类背肌与步态](https://journals.biologists.com/jeb/article/213/9/1490/10266/Function-of-the-epaxial-muscles-in-walking)
- [Walter 与 Carrier，疾驰犬的地面反作用力](https://journals.biologists.com/jeb/article/210/2/208/17106/Ground-forces-applied-by-galloping-dogs)
- [Hackert 等，犬类疾驰中的领腿偏好](https://arxiv.org/pdf/0809.2415)
