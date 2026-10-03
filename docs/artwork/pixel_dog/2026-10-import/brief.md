# Pixel Dog 成品素材接入

基线 `d23aee3`；用户接受 rmazanek 的 Dog 成品素材，要求作为新 pet 接入，
不得影响现有 pet。本次 ID 为 `pixel_dog`，显示名称 Pixel Dog。
Akita/Robot 的素材、manifest、默认选择和播放行为保持不变。

## 来源与模型

- 来源：[Dog / rmazanek](https://opengameart.org/content/dog-3)，标为 CC0。
  原表 `dog_medium.png` 为 360×228 RGBA，6 列×6 行，每格 60×38。
  SHA-256：`77a32e17840c921f939a754cc5d73622334e568a0bc2c40d55d534b487d2a58a`。
- 上游：[Husky / Hellkipz](https://opengameart.org/content/husky-sprites) 与
  [German Shepherd / Shepardskin](https://opengameart.org/content/german-shepherd-0)，
  页面均标为 CC0。保留来源说明和许可文本于安装资源内。
- 此次没有 AI 生成、重绘、光流或混帧。参考与源稿是同一成品表：第 6 行第 1 格
  用于角色身份、尺度和站立定位，第 3 行完整五格用于奔跑路径及极值。
- 固定侧视、朝左，灰白毛色、红色眼睛及原始描边；不套用 Akita 的项圈、
  身体尺度、脚掌坐标或步态指标。远侧脚在原稿中有遮挡，不凭像素统计认证解剖。
- 生产采用 64×64 straight RGBA8/sRGB（无配置文件按现有合同解释），64 dp 视图。
  每格原样放到 `(2,13)`，仅加透明边，不缩放、不逐帧居中、不裁透明外接框。
  原格地面下边界 y=38 对应画布 y=51；脚掌会随腾空改变，不强制逐帧贴地。
  数量徽标复用现有 64px `robot_count_v1`，位于右上留白。

## 动作与时间

原表有效格数逐行是 4 / 6 / 5 / 3 / 4 / 4。空白格不进入播放。
保留完整原表，运行包只导出此次状态映射需要的 20 格。

| 产品状态 | 成品动作 / 零起点行 | 顺序、曝光与结束 |
| --- | --- | --- |
| idle | standing / 5 | 0–3 各 200ms，800ms 循环摆尾 |
| running | running / 2 | 0–4 各 130ms，650ms 循环 |
| needs_input | bark / 0 | 0–3 各 150ms，再 standing/00 停 800ms，1400ms 循环 |
| ready | sit / 3 → sitting / 4 | 坐下 0–2 各 140ms，仅一次；坐姿 0–3 各 200ms 循环 |
| blocked | sit / 3 → sitting/00 | 坐下 0–2 各 140ms，然后保持至状态改变 |

Running 的 130ms 和 bark 的 150ms 来自原始 German Shepherd 包 x1 GIF 的
实际逐帧 duration；不是 rmazanek 页面声明的独立时序。原始 GIF 作为时间参照
保存在本目录。摆尾 200ms、坐下 140ms 和提醒间隔 800ms 是本次接入选择，
待真机观感验证。原表第 2 行 walking 此次不用，仍保留在源表中。
新事件立即生效，Ready 的坐下仅在进入时播放，Blocked 稳态没有刷新 deadline。

## 导出与复现

`python tools/import_pixel_dog.py --output <new-directory>` 从本目录固定源表
导出 production PNG 与 manifest，拒绝覆盖已有目录。源稿像素无改色或重采样；
帧引用、矩形、时长和输出指纹由导出记录与回归核对。
现有运行时从 manifest 读物理帧，没有新增 GUI backend 或新依赖。
每个状态的根 PNG 是该状态首帧的副本，供人工浏览，不参与运行时调度。

审查入口：[原速循环预览](running-preview.html)、[五姿势两圈接触表](running-audit/contact-sheet.png)、
[状态首帧及数量徽标](states-count10.png)。HTML 默认放大至 192 CSS px，真机为
64 dp；静态接触表与审核 JSON 不证明运动观感。

## 验收

| 项目 | 状态与范围 |
| --- | --- |
| 来源、许可与原表几何 | pass：作者与两级上游页面、实际下载文件及像素检查 |
| 原稿身份及导出后全像素一致 | pass：20 格与源表固定矩形逐像素一致；29 个包文件离线重导出逐字节一致；拒绝覆盖已有目录 |
| 时间线、打断、徽标与预检 | pass：五帧循环、坐下一次、Blocked 保持、离线/运行时全状态像素与曝光一致；缺帧阻止部署 |
| 保持原有宠物与用户设置 | pass：独立目录、默认 Akita；真实安装入口测试覆盖三种选择、重装保留、失败回滚及卸载保留设置；旧资产无修改 |
| 手机安装与原生状态输出 | pass：正式安装后切换新宠物；隔离会话 `codex-pet test` 五状态通过；连续预览 70 秒 GUI ready；随后恢复 Akita，配置与原位置一致，无新增错误日志 |
| 64 dp 原速奔跑、循环接缝和透明边缘 | pending：需要用户设备观察 |
| 新宠物的真实拖动与状态可读性 | pending：需要用户设备观察 |

验证数据见 [verification.json](verification.json)：206 项完整回归通过，
mypy 检查 28 个生产模块通过；Akita 的 41 个现有资源/manifest 文件和 Robot
的 manifest 均与基线逐字节一致。设备为现有华为手机，Termux:GUI plugin 7、
binding 0.1.6，使用原有 PNG 默认。安装版本为 `20261003T002139Z-72e0bba5`。
现场已展示新宠物并请求人工观察；尚未收到本次观感和触摸结论，因此保留 pending。

导入成品不等于用户已经认可动作效果。自动测试只验证原图忠实接入、程序行为
和文件资源；不得把图像/文件 PASS 写成步态或美术验收。
