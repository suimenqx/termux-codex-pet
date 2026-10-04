# 秋田犬 Grok v2 跑步候选复核

## 当前结论

v2 的抠图方法比接入前的旧生产版明显更好，值得作为当前 Running 的边缘处理基础。重新把 `idle`、`ready`、旧 `running` 和 v2 原尺寸帧放在同一尺度下比较后，不能再把旧 `running` 的包围框当成缩放真值：旧 running 本身就比 ready 偏小。

因此本轮不缩小 v2。v2 的原始 256×256 帧作为首选版本；之前按旧 running 包围框生成的固定缩放版只保留作对照。现在已将原尺寸 v2 接入生产 `running`，正在等待设备上的实际尺寸和 Running→Ready 人工复核。

推荐先看 [`review/v2-normalization-compare-192px.png`](review/v2-normalization-compare-192px.png)：它按浅色和深色背景并排显示接入前旧生产、v2 原始、固定缩放 v2，以及从 v2 HD 下采样的结果。三帧抽查见 [`review/v2-normalization-contact-192px.png`](review/v2-normalization-contact-192px.png)。原尺寸首选候选在 [`review/frames_256-v2-raw/`](review/frames_256-v2-raw/)。

## 输入复核

- 输入归档：`akita-run-grok-v2.zip`，SHA-256：`8bd86fd3a58d9988a0a219110858f8b948cb62c397961d746b604ab99e06d849`。
- v2 提供 20 张 256×256 RGBA 帧、20 张 768×768 RGBA 高清帧和 834 ms 的 `42,42,41 ms` 播放表。
- 原包的 `process2.py` 使用头部区域启发式 `HA` 稳定画面；源码中没有真正的眼睛/鼻子 facial-landmark 检测实现，因此报告中“按 facial landmarks 配准”的说法不能仅凭包内源码复核。
- 高清放大脚本依赖包外的 `/tmp/EDSR_Tensorflow/models/EDSR_x2.pb`，且制作脚本依赖 OpenCV/SciPy；原始视频帧也没有随 v2 包提供，HD 流程不是完全可复现输入。

## 测量结果

接入前旧生产 20 帧的 alpha union bbox 为 `[11,29,245,227]`；v2 原始 256 帧为 `[6,30,251,238]`。v2 的 union 宽度/高度分别为 246/209 px，旧生产为 235/199 px；这只能说明旧 running 的整圈包围框更小，不能证明 v2 应该缩小。

抽查同一首帧的有效 alpha 面积如下：

| 素材 | bbox | 有效面积 |
| --- | --- | ---: |
| 旧 `running/00` | `(31,31)–(234,227)` | 24321 |
| `ready/00` | `(43,38)–(226,235)` | 25646 |
| v2 原尺寸 `00` | `(27,33)–(238,238)` | 26624 |

旧 running 的脚底约在 `y=227`，ready 约在 `y=235`，v2 原尺寸约在 `y=238`。这与实际观察到的“running 比 ready 小”一致。固定缩放 `0.9521531100` 是基于旧 running 算出的诊断变换，不应继续作为默认生产尺度。

边缘诊断使用半透明像素到最近不透明内部像素的 RGB 距离，仅用于候选比较，不代替视觉验收：

- 接入前旧生产：半透明像素平均约 2102 个，边缘 RGB 距离均值 68.42；
- v2 原始 256：平均约 391 个，边缘 RGB 距离均值 3.74；
- 固定缩放 v2 256：边缘 RGB 距离均值 19.35，仍明显优于当前生产；
- 固定缩放 v2 HD 再下采样：边缘 RGB 距离均值 41.06，反而重新引入更多抗锯齿/半透明边缘。

因此当前首选候选是原尺寸 `frames_256-v2-raw/`，不是 `frames_256-v2-normalized/`，也不是 `frames_256-hd-normalized/`。HD 帧仍可作为归档或未来更大显示尺寸的源，但不能因为“分辨率更高”就默认 256 px 结果更好。

## 候选输出与接入边界

- `review/frames_256-v2-raw/`：从输入 v2 归档原样保留的 20 张 256×256 RGBA 帧，未缩放、未重采样；`frames.json` 保留 834 ms 的原时序。
- [`candidate-v2-normalized.json`](review/candidate-v2-normalized.json)：可用 `tools/preview_animation.py --state running --candidate ... --cycles 2` 预览；它仍可用于观察缩小后的差异，但现在只是诊断对照，不是首选候选。
- `review/frames_256-v2-normalized/`：v2 清洁 256 帧经过一次固定整圈变换的候选。
- `review/frames_256-hd-normalized/`：v2 HD 经过同一固定变换并下采样的对照候选，不推荐当前 256 生产使用。
- `source/normalize_v2.py`：不逐帧拟合、不改动作，仅根据两套 20 帧 union bbox 计算一套固定变换，并采用预乘 alpha 重采样。
- `review/edge-before-after.png`、`review/consistency-192px.png`：v2 原包自带的复核图，已保留在候选目录。

本次已将原尺寸 v2 的 20 帧写入 `codex_pet/assets/akita/frames/running/`，并同步更新回退图、`pet.json` 的运行版本、来源哈希和跑步审计标记；播放时序仍为 834 ms。下一步应在 192 px/64 dp 实际显示尺寸下检查原尺寸 v2 与 `ready` 及 Running→Ready 过渡；若出现跳变，应以稳定的头部/面部参照重新求一套固定变换，而不是继续沿用旧 running 的整体包围框。设备检查失败时恢复接入前的生产提交即可。
