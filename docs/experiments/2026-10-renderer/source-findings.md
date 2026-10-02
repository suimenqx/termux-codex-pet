# Termux:GUI 渲染路径的一手资料核对

核对日期：2026-10-02。本文提供协议、实现与安装环境证据；性能与设备实验以同目录的实验记录为准。本文未修改生产代码，未创建额外 GUI 窗口。

## 证据边界与版本

- **本机检查**：Python 3.14.6；`importlib.metadata.version("termuxgui")` 为 `0.1.6`，模块位于 `/data/data/com.termux/files/usr/lib/python3.14/site-packages/termuxgui/`。初始全局环境没有 Pillow、NumPy。后续隔离依赖实验不代表已安装到生产环境。
- **主实验实测**：`Connection.getversion()` 返回 `7`。官方 APK 标签 `0.1.6` 的 Gradle 配置为 `versionCode 7`、`versionName "0.1.6"`、`minSdk 24`、`targetSdk 33`。返回值支持版本匹配，但不构成 APK 字节或签名相同的证明。[固定版本构建配置](https://github.com/termux/termux-gui/blob/4695f6444488c8f0e74aedff5c682be570292a47/app/build.gradle#L24-L29)
- **源码检查**：以标签 `0.1.6` 的提交 `4695f6444488c8f0e74aedff5c682be570292a47` 为主。另查到 upstream main 为 `be24a5f34681096a788a6b0559caf833f87bd691`，其配置已经是 versionCode 8 / versionName 1.0.0，不能据此称本机插件为 1.0.0。[main 构建配置](https://github.com/termux/termux-gui/blob/be24a5f34681096a788a6b0559caf833f87bd691/app/build.gradle#L79-L85)
- **资料冲突处理**：优先本机实际 binding 与匹配 APK 版本的源码，再对照协议文档。Python HTML 文档标题仍是 0.1.5，不能单独作为 0.1.6 行为保证。[binding 文档](https://tareksander.github.io/termux-gui-python-bindings/termuxgui.html)

## Shared buffer：能用，但必须定义数据消费完成

### 文档和实现确实存在差异

协议文档写 `ARGB8888`，并规定内存是依次 RGBA 四字节。但是本机 Python `Buffer` 默认参数为 **`ARGB888`**，APK 0.1.6 的 JSON `addBuffer` 也只接受这个拼写；这两个名称不能混用。二进制协议的枚举另为 `ARGB8888`。第一版应把差异封装在 renderer 的兼容层。[协议说明](https://github.com/termux/termux-gui/blob/4695f6444488c8f0e74aedff5c682be570292a47/Protocol.md)、[JSON 实现](https://github.com/termux/termux-gui/blob/4695f6444488c8f0e74aedff5c682be570292a47/app/src/main/java/com/termux/gui/protocol/json/v0/HandleBuffer.kt#L23-L32)、[二进制实现](https://github.com/termux/termux-gui/blob/4695f6444488c8f0e74aedff5c682be570292a47/app/src/main/java/com/termux/gui/protocol/protobuf/v0/HandleBuffer.kt)

本机 binding 通过 JSON 协议工作：连接发送 `0x01`；`Buffer` 收到共享内存文件描述符并映射 `w*h*4` 字节。`blit()` 调用 `mem.flush()` 后仅发送 `blitBuffer`，**不等待插件拷贝完成**；`ImageView.refresh()` 同样只是发送命令。`mem.flush()` 不等于跨进程消费者已经读完。

### 插件实际做了什么

0.1.6 的 JSON 连接线程顺序读取、处理每条命令。处理 `blitBuffer` 时直接调用 `Bitmap.copyPixelsFromBuffer()`，再把源 ByteBuffer 的 position 归零；随后返回处理下一条命令。`refreshImageView` 对 overlay 在 UI 线程执行 `invalidate()`。所以共享路径仍有从 staging memory 到插件 bitmap 的拷贝，不是端到端零拷贝。[顺序 dispatch](https://github.com/termux/termux-gui/blob/4695f6444488c8f0e74aedff5c682be570292a47/app/src/main/java/com/termux/gui/protocol/json/v0/V0Json.kt#L43-L81)、[blit / refresh 实现](https://github.com/termux/termux-gui/blob/4695f6444488c8f0e74aedff5c682be570292a47/app/src/main/java/com/termux/gui/protocol/json/v0/HandleBuffer.kt#L122-L186)

**源码推导出的消费屏障**：同一个连接、同一个 GUI worker，写入后依次 `blit()`、`refresh()`、`getversion()`。收到 version 响应，说明此前的 `copyPixelsFromBuffer()` 已返回，staging memory 才能重用。`getversion()` 回的是 `BuildConfig.VERSION_CODE`，不是渲染状态。这是针对已核对实现的兼容办法，不是协议承诺的 present fence。

```python
# 示意合同：frame_bytes 必须已经是连续、预乘 alpha 的 RGBA。
buffer.mem[:] = frame_bytes
buffer.blit()
image_view.refresh()
connection.getversion()  # 相同连接；等待 staging 数据已被插件消费
# 现在可覆写 buffer.mem；不能据此声称 Android 已把该帧显示到屏幕。
```

必须区分三个时点：Python 完成发送、插件完成读取像素、Android 实际呈现。这个屏障只能支持第二项。两块 buffer 轮流写、固定 sleep、30Hz/10Hz 的低频率，都不能自动证明消费者已完成。若未来改用二进制协议，它的 blit response 在拷贝后返回，可用于同一目的，但仍非屏幕呈现完成，且需要另一套协议接入工作。

生产合同建议：`submit()` 返回表示输入像素不再被异步读取；每次最多一个未完成提交；一旦提交超时，丢弃连接并走既有重连，不能继续在无法确定消息边界的 socket 上调用下一方法。若收益不足，保留 PNG 默认路径。PNG 发送没有共享 staging 覆写竞争，但仅发送成功仍不证明图片已呈现。

### Buffer 生命周期

文档要求删除 buffer 前先让所有 ImageView 停止引用它。对现有 overlay，`setimage(png)` 后在同连接等待 `getversion()` 或有效 ImageView 的 `getdimensions()` 响应，可以确认此前 UI 来源切换已经执行；之后再删除 buffer。不能用无效 view/activity 的尺寸查询作为屏障，某些无效参数不会收到响应。[setImage 与 getDimensions](https://github.com/termux/termux-gui/blob/4695f6444488c8f0e74aedff5c682be570292a47/app/src/main/java/com/termux/gui/protocol/json/v0/HandleView.kt)

本机 `Buffer.remove()` 先发删除，再关 mmap 和 fd，且不保证重复调用安全；如果发送抛错，本地关闭语句不会执行。renderer 必须以 `finally` 清理自己持有的映射和 fd，释放派生 memoryview，记录 closed 状态。重连时重新创建窗口、ImageView、buffer、最后一帧缓存；旧连接的对象 ID 不可复用。插件在连接退出时清理该连接的 overlay 和共享内存。[插件清理](https://github.com/termux/termux-gui/blob/4695f6444488c8f0e74aedff5c682be570292a47/app/src/main/java/com/termux/gui/protocol/shared/v0/V0Shared.kt#L73-L105)

### 追加发现：EOF 死循环和删除 buffer 后断连

**已实际复现的 binding 缺陷**：本机 `termuxgui/msg.py` 的 `read_msg` 在头部、正文两个循环中都只按收到的字节数扣减；`recv()` 返回 `b""` 时没有 EOF 分支。`read_msg_fd` 的头部及 `recvmsg()` 正文循环同样如此。socket 超时不能终止这个忙循环，因为已关闭的连接会立即返回空字节。本机文件与官方 binding 0.1.6 提交 `7993577f49146a617e940cb213e4cae14c1230aa` 的文件逐字节相同。[binding 消息读取](https://github.com/tareksander/termux-gui-python-bindings/blob/7993577f49146a617e940cb213e4cae14c1230aa/src/termuxgui/msg.py)

用本机 Python 的 `socket.socketpair()` 关闭对端，在子进程分别调用原版两个函数，设置 socket timeout 为 50ms，外部 watchdog 为 300ms：两例都超出 watchdog，被终止；观测总时长分别为 305.59ms、307.08ms。没有使用 GUI 或修改全局 binding。原生 GUI 实验亦在 `remove()` 后的 `getversion()` 读循环暴露同类 EOF 空转，由主实验记录保存上下文。

另用 socketpair 返回合法 JSON `-1` 且不附 fd，实测 `Buffer(...)` 抛 `TypeError: 'NoneType' object cannot be interpreted as an integer`。原因是 `read_msg_fd` 总返回二元 tuple，失败为 `(-1, None)`，但 `Buffer.__init__` 只检查 `len(ret) == 1`，随后把 None 传给 mmap。错误路径也必须显式验证，不能只测正常建 buffer。本机 buffer.py 亦与此官方版本逐字节相同。[binding Buffer](https://github.com/tareksander/termux-gui-python-bindings/blob/7993577f49146a617e940cb213e4cae14c1230aa/src/termuxgui/buffer.py)

**删除后断连的源码因果候选**：JSON `deleteBuffer` 本身没有关闭连接或特殊处理 id=0；它从 map 移除对应项并关闭共享内存。但是 `Util.sendMessageFd` 用 `setFileDescriptorsForSend` 保存共享内存 fd，发送后没有清空。[FD 发送实现](https://github.com/termux/termux-gui/blob/4695f6444488c8f0e74aedff5c682be570292a47/app/src/main/java/com/termux/gui/Util.kt#L59-L65)

Android 12 AOSP `LocalSocketImpl` 把这些 fd 存在 `outboundFileDescriptors`；JNI 每次写都会取该字段附加 SCM_RIGHTS，发送结束后没有清空。因此删除最近创建 buffer 后，下一个响应可能尝试附加已关闭的 fd，触发发送异常，连接处理器退出。它也解释 binding 为什么在普通 recv 丢弃 header 的 ancillary data 后，仍能从 body 的 recvmsg 得到 fd。这是根据官方 APK 与 AOSP 的**源码推导**；没有取得该 ROM 的实际 JNI 或插件异常日志，不能将这一机制冒充已经抓到 native 堆栈的根因。[Android 12 Java 实现](https://android.googlesource.com/platform/frameworks/base/+/android-12.0.0_r1/core/java/android/net/LocalSocketImpl.java#513)、[Android 12 JNI 实现](https://android.googlesource.com/platform/frameworks/base/+/android-12.0.0_r1/core/jni/android_net_LocalSocketImpl.cpp#185)、[插件异常退出](https://github.com/termux/termux-gui/blob/4695f6444488c8f0e74aedff5c682be570292a47/app/src/main/java/com/termux/gui/ConnectionHandler.kt#L127-L155)

**同机补充实验已经缩小故障条件**：在独立连接依次创建 A/B 两块 4×4 buffer，首次 `getversion()` 为 7；删除较早的 A 后再查询仍为 7；删除最新的 B 后查询获得 EOF，EOFGuard 将其转换成 ConnectionError；新建连接查询恢复为 7。这个 A/B 对照支持“最近一次传出的 FD 被释放”解释，排除了“任何 deleteBuffer 都必定断连”的宽泛描述；它仍没有直接观测 APK 内部 sendmsg 的 errno。[buffer 生命周期原始记录](buffer-lifecycle.json)

对重构顺序的影响：**先修补兼容边界的有限读取，再谈默认 shared renderer**。局部 transport 必须同时覆盖 main/event/fd 读取；空字节立即抛连接错误、对帧长度设上限、fd 缺失/多余时正确关闭、阻塞采用绝对截止时间。回归须覆盖头部半包后 EOF、正文半包后 EOF、空连接 EOF、无 FD 的失败回复、超时、重连和 fd 泄漏。仅调用 `_main.settimeout()` 不足以修复。

首版选取更小的资源状态空间：一条连接持有一个固定 framebuffer，正常运行时不删除；改变画布或回退 PNG 时关闭并重建连接。主实验已使用这种持有到连接退出的路径完成循环提交，Python fd 计数为 5→5，三次新连接均返回版本 7。该记录不证明插件长期 native 内存没有泄漏。[GUI 实验记录](gui-results.json)

A/B 对照也支持后续测试“先创建后继 buffer 再删前一块”的优化，但它没有完成 ImageView 替换、反复尺寸切换与异常路径验收；不要第一轮就把这条优化并入生产生命周期。不能为了维持连接不断创建永不释放的 buffers。

Android 8.1+ 使用 `SharedMemory`；更早版本有 ashmem 分支。因此旧 Python 文档“only Android 8.1+”不是这个 APK 的完整实现范围。但本次实机是 Android 12，未测试 Android 7、8 或其他厂商版本，不能扩大宣称兼容范围。

## 透明度：格式正确仍可能像素错误

Android 官方说明 `copyPixelsFromBuffer` 直接复制源像素，不做 `setPixels` 的颜色转换。View/Canvas 按预乘 alpha 使用 bitmap；`setPremultiplied` 只是数据解释标记，不替已有像素做乘法。[Android Bitmap API](https://developer.android.com/reference/android/graphics/Bitmap#copyPixelsFromBuffer(java.nio.Buffer))

由 Android 契约与插件原始复制路径可得：素材 straight RGBA 不能直接交给这个 bitmap；需要准备 premultiplied RGBA（RGBA 字节顺序、alpha 类型为预乘、连续行、sRGB）并保持可见 RGB 与 alpha 的关系正确。PNG 路径由 Android 图片解码器处理这一步。预乘处理应在帧缓存准备时执行，避免播放期间反复转换。

Pillow 明确区分 `RGBA` 和 `RGBa`，后者是预乘 alpha 模式；可测量 `image.convert("RGBa").tobytes()`，不必仅为了乘 alpha 增加 NumPy。[Pillow 模式说明](https://pillow.readthedocs.io/en/stable/handbook/concepts.html#modes)

**后续人工证据**：主实验已在同设备显示 64 dp 的 PNG / premultiplied shared Running 动画，深浅背景每 10 秒切换，用户确认两侧一致、从左右图标拖动均正常。这使当前样本的可见透明边缘获得人工验收，但未自动读取屏幕像素，也不构成 Android 精确采样、GPU 完成时刻或所有状态无撕裂的证明。数学 round-trip、调用成功或非零耗时仍不能替代这个实机证据；真实重构实现上线前要重复对照。[人工记录与范围](visual-results.json)

## Overlay：坐标、可见性、触摸必须留在 renderer 边界

- `setPosition` 把 x/y 直接写进 `WindowManager.LayoutParams`，是屏幕像素；View 数字宽高默认经过 dp→px，只有 `px=true` 才直接使用像素。Renderer 对外合同必须标注坐标单位，避免 dp、屏幕 px、素材 px 混用。[移动实现](https://github.com/termux/termux-gui/blob/4695f6444488c8f0e74aedff5c682be570292a47/app/src/main/java/com/termux/gui/protocol/json/v0/HandleActivityAndTask.kt#L233-L245)、[尺寸实现](https://github.com/termux/termux-gui/blob/4695f6444488c8f0e74aedff5c682be570292a47/app/src/main/java/com/termux/gui/protocol/json/v0/HandleView.kt#L1038-L1094)
- overlay 创建返回单个 aid；本机 `Activity` 默认构造函数却按 `(aid, tid)` 解包。真实调用 `Activity(c, overlay=True)` 已复现 `TypeError: cannot unpack non-iterable int object`。应保留现有协议兼容封装；失败后关闭该探针连接，以清理已在插件端创建的 overlay。[调用记录](buffer-lifecycle.json)
- **`getConfiguration` 对 overlay 没有返回分支**：它只查询 activities。原生探针已在独立连接复现约 3001ms 后 timeout，随后丢弃连接；这不是尺寸测量慢或偶发不可靠。继续通过布局完成后的已知 dp 宽度和原生 `getDimensions` 校准，勿每帧阻塞查询；布局未完成时尺寸可能仍为 0。[configuration 实现](https://github.com/termux/termux-gui/blob/4695f6444488c8f0e74aedff5c682be570292a47/app/src/main/java/com/termux/gui/protocol/json/v0/HandleActivityAndTask.kt#L73-L79)、[调用记录](buffer-lifecycle.json)
- overlayTouch 使用 `rawX/rawY`，只发 down、up、move；JSON payload 不包含 aid/id，也不发送 cancel。ImageView 的 targeted touch 会通过 `imageMatrix` 的逆矩阵映射至图像空间，并支持 cancel。应保留一个 overlay；统一转换两个事件源，拖动主要使用 overlay 坐标，targeted 事件只补充锚点与取消。在断线和熄屏时清掉未完成手势。[overlayTouch](https://github.com/termux/termux-gui/blob/4695f6444488c8f0e74aedff5c682be570292a47/app/src/main/java/com/termux/gui/protocol/json/v0/V0Json.kt#L218-L231)、[targeted touch](https://github.com/termux/termux-gui/blob/4695f6444488c8f0e74aedff5c682be570292a47/app/src/main/java/com/termux/gui/Util.kt#L256-L340)
- `setVisibility` 对 overlay 下的 View 支持 GONE、INVISIBLE、VISIBLE。但隐藏图像不自动构成“整个窗口不拦截触摸”的保证；需要实机验证或移除窗口重建，不应给抽象接口过强承诺。[可见性实现](https://github.com/termux/termux-gui/blob/4695f6444488c8f0e74aedff5c682be570292a47/app/src/main/java/com/termux/gui/protocol/json/v0/HandleView.kt#L780-L810)
- 插件注册 SCREEN_OFF/SCREEN_ON 广播并产生对应事件，因此可设计熄屏暂停动画、亮屏按单调时钟恢复。但源码中未发现通用的“overlay 被别的窗口挡住”事件；不能承诺所有不可见情况都自动暂停。普通 Activity 的生命周期也不等于 overlay 的可见性。[广播注册](https://github.com/termux/termux-gui/blob/4695f6444488c8f0e74aedff5c682be570292a47/app/src/main/java/com/termux/gui/protocol/shared/v0/V0Shared.kt#L40-L51)、[JSON 事件](https://github.com/termux/termux-gui/blob/4695f6444488c8f0e74aedff5c682be570292a47/app/src/main/java/com/termux/gui/protocol/json/v0/V0Json.kt)

这些结论来自实现检查；当前实机的转屏、锁屏、熄屏、隐藏后触摸穿透、多指取消需在设备验证清单单列，不应记作已测试。

## Pillow / WebP 与最小依赖

Pillow 支持 WebP，但构建须包含 libwebp。检查 `features.check("webp")` 之外，还必须真实加载、裁切、导出、再次解码并核对 RGBA。保存 atlas 时要显式指定 `lossless=True`；若资产验收依赖所有 RGBA 字节一致，包括透明像素内的 RGB，还须 `exact=True`。默认 exact 为 false，会舍弃不可见 RGB。PNG 帧与 WebP atlas 都可解码为相同 FrameSource 合同；atlas 并非 shared-buffer 的依赖。[Pillow WebP](https://pillow.readthedocs.io/en/stable/handbook/image-file-formats.html#webp)、[features](https://pillow.readthedocs.io/en/stable/reference/features.html)

Pillow 12 已移除 `transp_webp`、`webp_mux`、`webp_anim` 专项 feature checks；不要复制旧教程用它们判断新版包能力。[Pillow 移除记录](https://pillow.readthedocs.io/en/stable/deprecations.html#specific-webp-feature-checks)

技术栈建议分开约束：

| 层 | 最小依赖 / 决策 |
| --- | --- |
| 事件、状态、时序、IPC、manifest 验证 | Python 标准库；无 GUI、Pillow、NumPy 导入 |
| 原生窗口 | 已验证的 Termux 与 Termux:GUI APK；Python termuxgui 0.1.6；局部协议兼容层 |
| PNG 基线 | 当前 libpng 解码/合成路径；保持既有像素验收 |
| 帧预处理、可选 WebP atlas | 隔离实测通过的 Pillow + 其 libwebp；非每帧必做 |
| 播放数据 | 连续不可变 bytes + 有上限的缓存；mmap 属标准库 |
| NumPy | 不列为必需项；仅在批量变换经测量确有需要时引入 |
| WebView、GLES2、SDL、另一 APK、protobuf 客户端 | 当前重构不引入；以后有具体性能或功能门槛才评估 |

Termux 与插件安装签名必须相容；官方建议同来源安装。独立 Python 程序不需要自己开发 APK，但 Termux:GUI 插件 APK 仍是必须安装的宿主，并需要 overlay 权限。[Termux 安装契约](https://github.com/termux/termux-app#installation)、[Termux:GUI 使用说明](https://github.com/termux/termux-gui#termuxgui)

本次没有给旧 Android、其他 ROM、APK 升级、跨渠道签名迁移、GLES2 或 protobuf 做执行验证。它们不属于推荐主路径；不得把公开源码存在实现写成已经完成兼容验证。
