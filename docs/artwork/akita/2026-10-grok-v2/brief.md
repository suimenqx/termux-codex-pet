# 秋田犬 Grok v2 跑步候选复核

## 结论

v2 的抠图方法比当前生产版明显更好，值得作为下一版的边缘处理基础；但 v2 原始 256 帧比当前生产 Running 整圈大约 9–10%，整体低约 6 px，不能原尺寸直接替换。已生成一版固定整圈变换后的候选，仍未接入生产。

推荐查看 [`review/v2-normalization-compare-192px.png`](review/v2-normalization-compare-192px.png)：它按浅色和深色背景并排显示当前生产、v2 原始、固定缩放 v2，以及从 v2 HD 下采样的结果。三帧抽查见 [`review/v2-normalization-contact-192px.png`](review/v2-normalization-contact-192px.png)。

## 输入复核

- 输入归档：`akita-run-grok-v2.zip`，SHA-256：`8bd86fd3a58d9988a0a219110858f8b948cb62c397961d746b604ab99e06d849`。
- v2 提供 20 张 256×256 RGBA 帧、20 张 768×768 RGBA 高清帧和 834 ms 的 `42,42,41 ms` 播放表。
- 原包的 `process2.py` 使用头部区域启发式 `HA` 稳定画面；源码中没有真正的眼睛/鼻子 facial-landmark 检测实现，因此报告中“按 facial landmarks 配准”的说法不能仅凭包内源码复核。
- 高清放大脚本依赖包外的 `/tmp/EDSR_Tensorflow/models/EDSR_x2.pb`，且制作脚本依赖 OpenCV/SciPy；原始视频帧也没有随 v2 包提供，HD 流程不是完全可复现输入。

## 测量结果

当前生产 20 帧的 alpha union bbox 为 `[11,29,245,227]`；v2 原始 256 帧为 `[6,30,251,238]`。v2 的 union 宽度/高度分别为 246/209 px，生产为 235/199 px；以共同中心和底边计算出的固定缩放为 `0.9521531100`。

边缘诊断使用半透明像素到最近不透明内部像素的 RGB 距离，仅用于候选比较，不代替视觉验收：

- 当前生产：半透明像素平均约 2102 个，边缘 RGB 距离均值 68.42；
- v2 原始 256：平均约 391 个，边缘 RGB 距离均值 3.74；
- 固定缩放 v2 256：边缘 RGB 距离均值 19.35，仍明显优于当前生产；
- 固定缩放 v2 HD 再下采样：边缘 RGB 距离均值 41.06，反而重新引入更多抗锯齿/半透明边缘。

因此当前首选候选是 `frames_256-v2-normalized/`，不是 `frames_256-hd-normalized/`。HD 帧仍可作为归档或未来更大显示尺寸的源，但不能因为“分辨率更高”就默认 256 px 结果更好。

## 候选输出与接入边界

- [`candidate-v2-normalized.json`](review/candidate-v2-normalized.json)：可用 `tools/preview_animation.py --state running --candidate ... --cycles 2` 预览；时序沿用 834 ms。
- `review/frames_256-v2-normalized/`：v2 清洁 256 帧经过一次固定整圈变换的候选。
- `review/frames_256-hd-normalized/`：v2 HD 经过同一固定变换并下采样的对照候选，不推荐当前 256 生产使用。
- `source/normalize_v2.py`：不逐帧拟合、不改动作，仅根据两套 20 帧 union bbox 计算一套固定变换，并采用预乘 alpha 重采样。
- `review/edge-before-after.png`、`review/consistency-192px.png`：v2 原包自带的复核图，已保留在候选目录。

这批候选只验证“v2 边缘方案 + 当前生产尺度”的组合，未替换 `codex_pet/assets/akita/frames/running/`，未做设备验证，也不能替代人工确认 Running→Ready 的相位衔接。用户确认 192 px 对比和实际播放后，才考虑接入。
