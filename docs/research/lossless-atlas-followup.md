# 无损 WebP atlas：当前素材实测与接入边界

建议把无损 WebP atlas 作为下一步素材容器。它与 shared buffer 可以组合，
也能继续给 PNG renderer 供帧；二者分别负责素材存储和跨进程呈现。
本次只完成离线实验，没有迁移生产 manifest，也没有改变 PNG 默认策略。

## 本机实测

使用当前 Akita manifest 的全部 35 个帧引用，包括 34 张原画和派生眨眼帧。
Python 3.14.6、Pillow 12.3.0、libwebp 1.6.0；没有增加 NumPy 或其他运行依赖。

| 项目 | 结果 |
| --- | --- |
| 独立 PNG 总大小 | 3,117,602 字节 |
| 5 列 × 7 行 WebP atlas | 1,581,300 字节，减少约 49.3% |
| atlas 像素尺寸 | 1280 × 1792 |
| atlas RGBA 数据量 | 9,175,040 字节，即 8.75 MiB |
| 裁回全部 35 帧 | 与当前生产 RGBA 逐字节一致 |
| 独立透明度测试 | 全部 256 个 alpha 值以及透明像素隐藏 RGB 一致 |
| 两轮 PNG 全套热缓存解码中位数 | 248.60 / 263.27 ms |
| 两轮 WebP 整张热缓存解码中位数 | 100.64 / 101.26 ms |

测量是离线 Pillow 读取、转 RGBA 和取得 bytes，交替顺序，每轮 7 次。
不是冷启动、生产 PNG 验证器耗时、切帧总耗时、Android 呈现延迟或功耗测量。
日常系统和已安装桌宠仍在运行，不能把该耗时比例写成通用性能保证。
RGBA 数据量是计算值，不是进程 RSS：解码器、临时副本和帧缓存另占内存。

[原始结果与逐帧指纹](../experiments/2026-10-renderer/lossless-atlas.json)
可通过以下命令复现；临时 atlas 自动清理，生产素材不变：

```sh
python tools/probe_lossless_atlas.py --output ~/.cache/codex-pet/lossless-atlas.json
```

导出必须显式使用 `lossless=True, exact=True`。Pillow 的 `exact` 默认关闭，
会丢弃全透明像素隐藏的 RGB；只设置 `quality=100` 并不等于无损模式。
这是 [Pillow WebP 文档](https://pillow.readthedocs.io/en/stable/handbook/image-file-formats.html#webp)
的参数合同，本次也做了实际往返验证。

## 如何接入

1. **`pet_pack.py`**：新增受验证的 `webp_atlas` source，帧定义增加 atlas
   文件引用和整数 `rect: [x,y,w,h]`。验证路径不越界、矩形不越图、帧宽高与
   canvas 一致、整个 atlas 和所有驻留页面符合预算。保留现有 frame reference、
   clips、roles 和 transitions，不把动作时长塞进 WebP 动画容器。
2. **`image_codec.py` 与安装 preflight**：加入 WebP 能力实测和受限解码。
   先检查容器、静态图和尺寸，再分配像素；仍执行 sRGB 色彩合同，未知 ICC
   配置应拒绝或经过独立验证的离线转换。当前 `decode_png()` 明确拒绝 WebP，
   所以改后缀或只修改 manifest 文件名不能工作。
3. **`frames.py`**：增加 AtlasFrameSource，加载后输出既有不可变、连续的
   straight RGBA `RgbaFrame`。当前 35 帧可以一次解码、预切后释放整张 atlas；
   将所有常驻帧记入现有 32 MiB 缓存，避免另持一份不计预算的 atlas。
   大包再按页面管理，并明确缓存淘汰后重新解码的成本。
4. **导出和验收工具**：稳定排列、固定帧引用、不自动裁透明边或重新居中。
   自动比较全部 RGBA 字节和已有曝光序列；保留原 PNG 作为可追溯源稿，验证
   加载峰值、首次 Running、切宠物、缓存压力和安装回滚后再迁移生产包。

`PetRuntime`、时间线、Codex Adapter、触摸控制和 renderer 的 RGBA 接口不需
随素材容器重写。Pillow 的 crop 会产生图像副本，不能当作免费的 NumPy view；
这里不需要为了 atlas 再引入 NumPy。

采用 shared 时的路径是：

```text
pet.json + lossless atlas.webp
    → 加载 / 裁帧 → straight RGBA 缓存
    → 装饰 → 预乘 RGBA 缓存
    → shared buffer → ImageView
```

保持 PNG renderer 时，中间 RGBA 仍需编码为 PNG 后发送（当前已有编码缓存）。
将整张 atlas 直接交给 ImageView 不会自动按 manifest 裁帧或播放。
atlas 迁移不能代替共享路径尚未完成的 Android 原生资源验收。
