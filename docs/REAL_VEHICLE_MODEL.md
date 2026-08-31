# 真实车辆 STL 导入与复算

> DrivAerNet++ 原生 STL 的官方来源和选择性下载流程见
> [`DRIVAERNETPP_SOURCE.md`](DRIVAERNETPP_SOURCE.md)。它是可追溯的研究基准车，
> 不是某个品牌量产车型。

## 选用的公开模型

本项目随审查使用的是 DrivAerML `run_1/drivaer_1.stl`。它是公开的、
面向道路车辆外流场研究的通用乘用车几何，不冒充某个商业车型的 CAD；
DrivAerML 数据集以 CC BY-SA 4.0 发布，引用信息见
[数据集卡](https://huggingface.co/datasets/neashton/drivaerml) 和
[DrivAerML 论文](https://arxiv.org/abs/2408.11969)。原始文件的 SHA-256 为：

```text
411e6651284a26fc94924106b833fd79febc6deba63922c929dd8acfc99720d2
```

TUM 的 [DrivAer geometry/download 页面](https://www.epc.ed.tum.de/en/aer/research-groups/automotive/drivaer/download/)
是另一条可追溯来源；实际工程车辆 CAD 通常受授权限制，网上随意下载的 STL
还常有开口、重叠零件或不明单位，不能直接当作可计算壁面。

## 本地准备结果

原始 ASCII STL 约 142 MB、753,234 个三角面；
`workspace/external_models/drivaerml_run_1/prepared/body_drivaerml_run_1.stl`
是无抽稀的单区域 binary STL。导入前执行了流式转换、法向重算和最低点
对齐到 `z=0.005 m`，并用 OpenFOAM v2412 `surfaceCheck` 验证：
753,234 个三角面、1 个连通区域、封闭、每条边恰好连接两个面。原始模型中
约 18.4% 三角形质量低于 0.05；这提示 snappyHexMesh 可能耗时较高，不能
替代体网格质量和网格无关性审计。完整来源与证据在同目录的 `SOURCE.md`。

## 下载与运行

如果本地没有模型，可用 Hugging Face CLI 下载原文件：

```powershell
hf download neashton/drivaerml run_1/drivaer_1.stl `
  --repo-type dataset --local-dir workspace/external_models/drivaerml_run_1
```

随后先做低成本导入冒烟（示例脚本默认 10 cells/L、约 160 步、55k 级别体网格）：

```powershell
python examples/run_drivaerml.py `
  workspace/external_models/drivaerml_run_1/prepared/body_drivaerml_run_1.stl
```

本轮还保留了一个用于图像展示的中等网格案例：12 cells/L、表面 level 1、尾流
局部加密、wallFunction、260 步，共 193,874 cells；其三机位真实场图片和报告在
`workspace/drivaerml_showcase2/task_28d67b31/`。该案例的图像比低成本冒烟更能显示
尾流弯曲，但仍不是网格无关性研究；不同网格得到的 Cd 差异较大，不能挑选其中一个
作为发表或工程定值。更高的表面/前缘细化曾触发 13 个高偏斜面而被 `checkMesh`
门禁拒绝，失败报告保留在 `workspace/drivaerml_showcase/task_f0b0fb21/`，这正是
需要先做网格质量整改、再增加分辨率的证据。

要复现同类展示配置，可在上面的命令后加 `--profile showcase --iterations 800`；
默认 `smoke` profile 仍保持快速、跳过渲染的行为，避免误把展示配置当作生产配置。

## 尾流偏侧复核（2026-08-31）

旧的 260 步展示场并不是“相机把尾流挪到一边”：入口采样的横向速度均值为
`-1.4636 m/s`（以 30 m/s 自由流计约 4.88%），下游流线中心相对车体中线偏移约
`0.896` 个车宽，且末端偏移约 `1.249` 个车宽。它应被解释为尚未充分收敛、边界/网格
对称性尚未审计的场，不能作为收敛风洞图。

在不覆盖原算例的前提下，已复制到 E 盘并将稳态求解延长至 800 次（最新写盘场为
迭代 780）：入口横向速度均值约 `0.0308 m/s`，下游中心偏移约 `0.0104` 个车宽，
因此单侧尾流显著减弱。该复核场在 WSL/OpenFOAM 12 运行时没有生成新的
`forceCoeffs` 文件，故本轮不发布新的 Cd/Cl；它只用于说明流场采样偏侧的根因和图像改进。
交互清单现记录 `wake_diagnostics`，会在以后自动提示“入口横向速度”与“下游尾流中心偏移”
是不同问题，禁止在可视化层人为镜像或平移流线。

复核算例路径：

```text
workspace/drivaerml_showcase2/task_28d67b31_refined/case/
```

也可以通过 CLI 直接上传，但车辆 STL 应明确给出地面间隙；坐标系不一致时
再指定 z 轴旋转：

```powershell
aeroforge "车辆外流场 30 m/s" `
  --upload-stl body.stl `
  --upload-ground-clearance 0.005 `
  --upload-scale 1.0 `
  --upload-rotation-z 0
```

冒烟算例的 `Cd` 仅说明导入、网格和求解链条工作；发布结果前必须增加表面/尾流
加密、y+ 检查、至少三套网格和时间/统计收敛证据。

## 用户提供的 XPeng P7 候选

用户提供的 `D:\浏览器下载的文件\2022-xpeng-p7.zip` 已复制到项目 E 盘的
`workspace/external_models/xpeng_p7_candidate/`，并在 [`SOURCE.md`](../workspace/external_models/xpeng_p7_candidate/SOURCE.md)
与 `asset_manifest.json` 中记录来源、CC BY 4.0 署名要求和 SHA-256。解包后的 OBJ/MTL
包含多材质/纹理，但审查发现非有限坐标和大量开放边界，尚未满足“水密、单位和车头方向可证实”
的 CFD 门禁；已生成的 `p7_geometry_preview.html` 仅用于本地外观检查，不与 DrivAerML
风场叠加，也不能作为 P7 的计算结果。若要真正计算 P7，需先在建模工具中修复外壳、确认单位
和轴向、通过 `surfaceCheck`/`checkMesh`，并用独立的 P7 case 重新求解。

本轮另外从 `p7_visual_sanitized.glb` 生成了 E 盘独立的
`workspace/external_models/xpeng_p7_candidate/p7_cfd_candidate.stl`。体素填充 +
Marching Cubes 输出 162,936 面、1 个连通分量，导出后水密检查为真；其参数和哈希在
同目录 `p7_cfd_candidate_manifest.json`。这是为了让用户可以继续使用 P7 的近似
外壳候选，不是无损修复或厂商 CAD，清单仍为 `cfd_ready=false`，未与当前 DrivAerML
风场绑定。在确认单位/轴向、外流场部件和 `surfaceCheck`/`checkMesh` 前，禁止直接求解。

保留原 OBJ/MTL 便于追溯；在 E 盘另生成 `p7_visual_sanitized.glb` 作为可交互展示资产。
该 GLB 排除了含非有限值的材质组，并嵌入 50 个材质、49 个纹理，但仍是非水密视觉派生文件，
不应直接送入 `snappyHexMesh`。下载格式的取舍与后续 CFD 外壳要求见
[`VEHICLE_ASSET_POLICY.md`](VEHICLE_ASSET_POLICY.md)。
