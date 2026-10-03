# 社区素材配方与离线导入

六类来源、13个独立 Pet Pack。素材只下载/转换到本机；安装应用不会自动下载，仓库不分发第三方角色图片。原来 Boba 等五包继续使用 `tools/import_community_previews.py`，两个入口共用 `tools/pet_import/pack.py`。

| 配方 ID | 显示名 | 工作动画 / 已知特征 |
| --- | --- | --- |
| `runcat` | RunCat | 原游戏5帧奔跑；黑色剪影在深色背景对比度低 |
| `clawd_tank` | Clawd Tank | 原敲键盘GIF；取代无法跨应用使用的Clawd on Desk素材 |
| `vscode_clippy` | VS Code Clippy | 滑板 |
| `vscode_cockatiel` | VS Code Cockatiel | 凤头鹦鹉走动 |
| `vscode_crab` | VS Code Crab | 螃蟹走动 |
| `vscode_fox` | VS Code Fox | 狐狸奔跑 |
| `vscode_duck` | VS Code Rubber Duck | 上游原版火箭鸭 |
| `vscode_totoro` | VS Code Totoro | 原run为猫巴士；提示动作含多只龙猫 |
| `esheep` | eSheep | 原奔跑只有2张独立图片、3次曝光 |
| `esheep_bunny` | Buster Bunny | 原兔子行走；低分辨率经典素材 |
| `esheep_pingus` | Pingus | 原企鹅行走；低分辨率经典素材 |
| `ark_amiya` | ArkPets 阿米娅 | 原Spine骨骼行走，15fps，非像素角色 |
| `dsh_pet` | DSH 蓝毛小女仆 | 原奔跑视频，12fps；整段含趴下动作，非匀速步态循环 |

业务状态映射属于本项目适配。没有“blocked”原画的来源会复用原姿势，并不宣称这些社区项目原生支持 Codex 的五状态。

## 使用

普通PNG/GIF/eSheep只需应用已有的Python+Pillow；DSH离线转换另需`ffmpeg`，阿米娅离线转换另需`nodejs`与固定Canvas包。**这些依赖不进入daemon或hook入口**。在本机已验证：Python3.14.6、Pillow12.3.0、Node26.4.0、`@napi-rs/canvas@1.0.10`及其Android arm64二进制，Spine3.8固定Runtime。

```sh
python tools/import_pets.py --list

# 只导出一只，不需要 Node 或 ffmpeg
python tools/import_pets.py --pet vscode_fox --download \
  --output "$HOME/.cache/codex-pet/fox-export"
codex-pet pet import "$HOME/.cache/codex-pet/fox-export/vscode_fox"
codex-pet pet use vscode_fox
```

全量首次导出（请先阅读下面各来源的使用范围）：

```sh
pkg install nodejs ffmpeg
python tools/import_pets.py --all --download --setup-spine \
  --output "$HOME/.cache/codex-pet/popular-export"
for manifest in "$HOME/.cache/codex-pet/popular-export"/*/pet.json; do
  codex-pet pet import "${manifest%/pet.json}"
done
codex-pet pet list
codex-pet pet use ark_amiya
```

- `--pet`可重复；与`--all`互斥。`--list`不下载资源。
- 默认源缓存为`~/.cache/codex-pet/import-sources/`。文件按SHA-256寻址；存在但损坏会失败，不悄悄覆盖。`--download`只下载缺失源，哈希通过才发布缓存文件。
- `--setup-spine`通过随仓库维护的npm lock执行`npm ci --ignore-scripts`，安装到缓存的`spine-deps/`；不动全局npm环境。之后自动复用，也可用`--canvas-module`指定已安装包目录。
- 每包在临时目录构建，全部校验后才发布；失败删除本包半成品，已完成的其他包保留。目标ID已存在就拒绝覆盖。批次中途失败后，修复原因，再用`--pet`继续缺失项，或换一个输出目录重新全量导出。
- 导出不会自动安装或切换。`pet import`将完整结果复制到私有素材库，因此删掉下载缓存也不影响使用。
- 更新已安装包要使用**新ID**，例如`vscode_fox_v2`，不能修改已有包背后的文件。这样旧包、当前选择与编译/帧缓存保持一致。

## 配方与扩展边界

`tools/import_pets.py`是CLI；`tools/pet_import/pipeline.py::build_recipe()`是唯一构建入口；`decoders.py`封装真实格式差异；`pack.py`写出并编译统一的PNG-directory清单。运行时不认识任何社区项目名。

新增同格式角色：

1. 复制最相近的JSON配方并改文件名、`id`、显示名和说明。固定具体提交的源URL与SHA-256；保留图片真实出处和通知文本，不能从代码MIT推断所有角色都MIT。
2. 在`sequences`定义原始片段；在`clips`定义片段循环、完成转待机、单帧保持；在`roles`映射五业务状态。`select`仅用于明确选择原帧，例如末帧保持。原GIF逐帧曝光由解码器读取，不需手写一份会漂移的帧率表。
3. 填每段固定`layout`：可先`crop`、再按`size`缩放、最后按`offset`放入`canvas`。缩放使用预乘alpha，paste不重复乘alpha；超出输出画布的非透明像素会使构建失败。禁止逐帧自动居中或按各帧包围框分别缩放。
4. 用新ID导出、导入。检查全部状态、首尾循环、深浅背景和真机拖动；核对输出`import-record.json`的源哈希、配方、PNG/RGBA哈希、曝光总时长和解码预算。
5. 仅提交配方、来源/验收记录及必要的格式适配测试。新格式才扩展decoder，并用合成fixture验证关键行为；不因新角色修改runtime、renderer或installer。

具体字段以现有配方为可执行示例，配方是维护者审核的输入，不是任意第三方脚本格式。`sources`每项支持`encoding`（默认UTF-8）；Pingus AUTHORS显式使用Latin-1，保留原作者姓名而非吞掉解码错误。

格式差异：

- `png_sequence`：明确原序列和每帧曝光；RunCat采用原游戏100ms间隔。
- `gif`：顺序seek并取完整合成RGBA，保留GIF disposal和嵌入时长；同名`8fps`文件的实际时长可能不同。
- `esheep`：解析命名空间、内嵌PNG、0起算按行tile、精确色键，同时保留已有alpha。只支持相同正整数字面start/end间隔；保留重复曝光，不执行原随机重复、窗口物理或action脚本。变速片段明确报错。
- `vp9_alpha`：强制`libvpx-vp9`，原始时间由逐帧PTS和容器结尾确定。DSH每两帧取一帧并合计曝光，保留原完整周期；验证源尺寸、帧数、时长和透明度。仅ffmpeg/ffprobe子进程修正Termux的`LD_LIBRARY_PATH`，不改系统环境。
- `spine38`：PMA纹理先恢复straight RGBA，调用私有官方Runtime+Canvas；五动作共用固定联合视野、四倍超采样。限单页纹理、普通混合、无染色的region/mesh；不支持的附件/混合明确失败。不能声称通用兼容所有ArkPets模型。

输出按相同RGBA去重，但不删除重复曝光，因此减少重复PNG文件和清单的独立资源预算，不改变节奏。运行时仍由共享字节缓存控制实际占用。单包上限64MiB按解码RGBA算，绝不能按PNG/WebM文件大小算。`display_dp`仍为64²；本批各包128²至256²只是各源的离线画布选择。

## 出处与使用范围

各JSON保留固定版本的原始通知，转换时写入`CREDITS.md`，再随本地包复制。原素材不放进公共Git仓库。

- RunCat：Apache-2.0项目；保留README及LICENSE。
- Clawd Tank：MIT来源，与Clawd on Desk自有受限GIF明确区分。后者未经书面许可不可据本工具复制使用。
- VS Code Pets：保留MIT、作者贡献及角色来源，不因此授予第三方角色/商标权利。
- eSheep/Buster Bunny：原README标注sprite rip贡献者，未证明独立图片再分发许可；仅做本机比较，不能宣传为自由再分发素材。
- Pingus：保留原游戏GPLv3+、AUTHORS及源链接，不重标为desktopPet引擎的MIT。
- DSH：作者说明图片为豆包生成的手绘风，允许开源使用、禁止商用；不是本次生成，也不冒称人工逐帧手绘。
- ArkPets模型：版权归鹰角，保留非商用条款。Spine官方明确允许个人Runtime导出；本工具不分发Runtime或模型，不把该说明扩展为通用商用或Runtime再分发许可。

详细证据：[Clawd/DSH调查](../docs/research/clawd-dsh-import-validation.md)、[ArkPets调查](../docs/research/arkpets-import-validation.md)、[本次brief](../docs/artwork/community_previews/2026-10-popular/brief.md)、[验收记录](../docs/artwork/community_previews/2026-10-popular/verification.json)。
