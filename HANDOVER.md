# AeroForge-Agent 交接文档

> 写给接手的 AI / 工程师：本文档交代**已做工作、当前真实状态、已知坑、未完成事项**，
> 并列出**需要复核的疑点**与验证方法。请带着审查眼光阅读——前任（我）的方案
> 可能有误，欢迎推翻。
> 最后更新：2026-08-31（多形态交互可视化、8L/U∞ 示踪窗、DrivAerML run_2 独立复算）。

## 0.8. 当前交付：多形态视图与 DrivAerML run_2（2026-08-31）

- `interactive_viz.py` 的自包含 Plotly 页面现在提供 `连续流线`、`速度点云`、`尾流截面`、
  `组合` 四种模式。连续流线/箭头是默认论文式视图；点云与截面只是对真实 `U` 采样的
  可选诊断层，点云使用方形块，不再用球形节点。
- 稳态粒子输运周期统一为 `8L/U∞`，清单区分该展示时间与 simpleFoam 迭代时间；当前
  refined run_1 为 1.2543 s，run_2 为 1.2609 s，均 120 帧/40 fps。
- 新下载的 `workspace/external_models/drivaerml_run_2/run_2/drivaer_2.stl` 通过原生 STL
  门禁（1 component、watertight、753246 faces）。run_2 独立 case 在
  `workspace/drivaerml_run_2/task_5e31083c/case/`，191628 cells、800 次 simpleFoam、
  `checkMesh=True`、`Cd=0.25186`、`Cl=-0.03051`；这仍是 showcase 结果，不是网格无关性
  工程结论。
- run_2 的静帧、GIF/MP4、可拖动 HTML 已复制到 `docs/img/` 和 `docs/media/`，而源 STL/帧/
  JSON 等大文件仍留在 E 盘 `workspace/`（`.gitignore` 排除）。每次 ParaView 调用的
  `TEMP/TMP` 都显式指向 E 盘 scratch，完成后清理。

## 0.7. 尾流诊断与 DrivAerNet++ 接入（2026-08-31）

- 旧的 `task_28d67b31/case` 260 步场经真实 `streamline_data.json` 审计：入口
  `Uy` 均值 `-1.4636 m/s`，下游中心偏移 `0.896` 个车宽，不能解释成相机偏移或
  可视化 bug。复制出的 `task_28d67b31_refined/case` 延长到 800 次，最新场为 780，
  入口 `Uy` 均值约 `0.0308 m/s`，下游中心偏移 `0.0104` 个车宽；仍需后续力系数/网格
  收敛研究，不把它宣称为工程收敛。WSL/OpenFOAM 12 本轮没有生成新的 `forceCoeffs`。
- `tools/wake_diagnostics.py` 以入口横向均值/RMS、下游流线中心和端点中心为指标，
  输出 `balanced`、`inlet_crossflow_detected`、`lateral_bias_detected` 或样本不足状态；
  交互 HTML 与 manifest 均记录该诊断，禁止镜像/平移真实流线来“修图”。
- `tools/drivaernet_adapter.py` 只检查官方仓库元数据、按设计 ID 查找本地原生 STL，并
  对有限性、三角面、单连通和水密性执行门禁；没有 bulk download，也不从 P7 OBJ/GLB
  或体素壳体推断 CFD 外壳。官方浅克隆在 `workspace/external_models/drivaernet_official_upstream/`，
  详情见 [`docs/DRIVAERNETPP_SOURCE.md`](docs/DRIVAERNETPP_SOURCE.md)。
- `examples/run_drivaerml.py --profile showcase` 未显式给 `--iterations` 时现在默认 800，
  `smoke` 仍为 160；文档示例已同步。Windows Anaconda 的 trimesh/Plotly 可选导入增加
  WMI 缓存保护，避免首次导入卡住。

## 0.6. 2026-08-31 当前媒体与色标收尾

- `case/results/static_velocity_metadata.json` 是当前数值依据：入口 `u_free=30 m/s`，
  源点 `|U|` 最大 `43.9123 m/s`；原生多面体追踪器的 `158.504 m/s` 车顶尖峰已由
  后处理 `Tetrahedralize + Cell Locator` 排除，完整流线样本为 `10.9633–35.8485 m/s`。
  显示色标按有效样本动态确定并留 `8%` 头部空间，为 `10.9633–38.7164 m/s`（线性）。
- 当前静帧、动画和交互页统一采用蓝—青—黄—红逐点速度着色（低速 `#2166ac`，高速
  `#d73027`）；交互页
  的固定长度方向箭头使用线段箭头而不是实体 Cone，避免箭头表面叠成暗块。动画输出为
  `120` 帧、`40 fps`，交互页使用车体尺寸驱动的手动纵横比，并支持轨道旋转、滚轮缩放、
  时间滑块和五组预设机位（含后视镜、车尾细节）。
- 收尾产物已同步至 `docs/img/`、`docs/media/`；P7 资产仍是独立的视觉候选，不能沿用
  DrivAerML 的风场或被标作 P7 CFD 结果。

---

## 0'. v0.4.0 重大修订（2026-08-23，项目方向纠偏）

用户复盘初心：**一句话 → 仿真 → 好看的风洞级可视化**。v0.3.0 期间重心
漂移到 Ahmed Cd 学术验证，而可视化环节竟仍是合成假图。本版纠偏要点：

1. **假图删除**：`viz_tools` 三个 plot 函数画的是 tanh/正弦合成场、从未
   读过求解结果（调用处直接传 None）。已删除；真实可视化走新增的
   `tools/windtunnel_viz.py`（pvpython 离屏渲染三机位烟线图，模板随包
   分发于 `tools/pv_templates/`）。
2. **渲染三坑（血泪）**：CellData 必须先 `CellDatatoPointData`（否则
   流线积分为空）；ParaView 落在 **VisRTX 后端时线/半透明全部不可见**
   （不透明 STL 正常，极具迷惑性；显式 `CreateView('RenderView')` +
   Tube 不透明管解决）；烟线种子位置必须按包围盒推导（曾硬编码进车体
   内部，被删单元区追不出线）。STL 解析要兼容二进制（80B 头 + 50B/面）。
3. **死代码删除**：message_bus / state_machine（README 曾虚称"消息总线
   +状态机"，已纠正为顺序协程编排）。
4. **一句话能力补全**：风向角（偏航）旋转入口/移动地面/阻力方向；对象名
   三级提取（引号 > 车型关键词词典 > 兜底）；CLI `--upload-stl/--no-viz`。
5. **workspace 6.6GB→1.5GB**：仅保留 diag_case5（第 11 轮最优算例，
   Cd=0.449，含三机位渲染图）；其余十六个目录的结论均已固化在
   docs/VALIDATION.md。
6. 验证示例图已入仓库 `docs/img/`（README 首屏展示真实渲染效果）。

## 0.5. 2026-08-30 追加审查（真实车辆与结果图）

1. 引入公开 DrivAerML `run_1/drivaer_1.stl`：753,234 个三角面，流式转为
   单区域 binary STL，显式支持尺度、地面对齐和 z 轴旋转；本地准备件的
   `surfaceCheck` 已确认封闭、单连通区域、每条边两面。来源/许可证/哈希在
   `docs/REAL_VEHICLE_MODEL.md` 与工作区 `SOURCE.md`。
2. 新增 `examples/run_drivaerml.py` 和 CLI 上传几何控制项。真实车辆的
   55,504-cell、160 步低成本复算已经通过当前门禁并得到 Cd=0.2338；这只是
   导入/网格/求解链冒烟，不是网格无关性或工业精度结论。
3. `tools/pv_templates/streamline_hd.py` 已改用有限透明采样面、蓝—青—黄—红色标（宽量程
   自动使用物理刻度 `log10`）、中性车体材质和首帧相机初始化；并显式把所有
   StreamTracer 绑定到 CFD 的
   `U` 向量，避免继承 STL 法向导致车顶流线消失；图像仍必须来自实际 OpenFOAM 场。
4. 当前离线回归为 131 tests；短稳态冒烟的场和 forceCoeffs 写盘间隔已按迭代
   数自适应，避免短跑没有可视化场的假失败。

---

## 0. v0.3.0 重大修订（2026-08-22，接手者复核结果）

接手者对 v0.2.0 的 §5/§7 归因做了复核，**原归因被推翻**，要点：

1. **dat 列语义误读**：`coefficient.dat` 的 `Cd(f)/Cd(r)` 列**不是**摩擦/压差
   分解（实测各约为 Cd 之半）。真实分解在求解日志 forceCoeffs 块的
   Pressure/Viscous 列。重审后：**摩擦分量一直正常（Cd_viscous≈0.018），
   压差阻力 0.486 占 Cd 的 96%**。
2. **真主因 = 前缘曲率未解析**：R100 圆角仅 8 段离散 + 表面网格 ~33mm，
   圆角上仅 ~5 个单元；加速吸力峰无法形成，前表面近钝体滞止
   （Cp 均值 +0.62、全正压、无吸力区），前缘压差贡献 +0.42（正常 ~0.1）。
   `examples/surface_cp_zones.py` 可零成本复现该诊断。
3. **次因 = 边界层分辨率**：2 层相对厚度边界层 + 对数律壁面函数
   （实测 y+ 2.4–652 跨缓冲区）。Spalding 连续律壁面函数对照试验仅
   -4.5%（Cd 0.504→0.481），证明壁面函数**类型**不是主因。
4. 修复（v0.3.0 已固化）：STL 圆角 24 段、前缘加密盒 noseBox(level 5)、
   low-Re 壁面预设（15 层、首层按 y+≈1.2 估算 ~12μm、
   nutUSpalding/kLowRe）、max_global_cells 8M、并行 decomposeParDict 生成。

## 1. 项目目标与现状一句话

目标：把 AeroForge-Agent 从 dry-run 概念验证升级为**可真实求解的工程级 CFD
多 Agent 系统**，并用 Ahmed body 基准做端到端验证。

现状：**真实求解链路已完全打通**（WSL OpenFOAM v2412，网格→求解→力系数→报告→
ParaView 动画全自动化）；v0.2.0 的 Cd 偏差根因已修正（见 §0），v0.3.0 修复后
的验证数值见 `docs/VALIDATION.md` 第 9-11 轮记录。

---

## 2. 运行环境（本机特有，换机需重配）

| 项 | 值 / 说明 |
|---|---|
| Python | `E:\Anaconda\python.exe`。PATH 里的 `python` 是 MS Store 桩，**不可用** |
| OpenFOAM | WSL 内 v2412：`/usr/lib/openfoam/openfoam2412`，`RuntimeBridge` 自动探测（60s 超时+重试+缓存，冷启动慢） |
| ParaView | `D:\ParaView\bin\pvpython.exe`（RTX 5060 Laptop 离屏渲染） |
| git push | 直连 github 不通，必须 `-c http.proxy=http://127.0.0.1:7890 -c https.proxy=http://127.0.0.1:7890` |
| git 身份 | 逐仓 `-c user.name/user.email`（aeroforge 用 `Lixiang878 <Lixiang878@users.noreply.github.com>`） |
| 计算产物 | `workspace/task_<hash>/`（.gitignore 排除，不进 GitHub） |

---

## 3. 架构与文件地图

```
src/aeroforge/
├── core/runtime_bridge.py   三态运行时（native/WSL/不可用）；WSL 内重定向日志
├── core/models.py           Pydantic 契约（Task/Geometry/Mesh/Sim/FinalReport）
├── tools/case_builder.py    从零生成 OpenFOAM case（steady/transient 双模式）
├── tools/stl_tools.py       Ahmed body 参数化 STL + 上传 STL 流式转换/水密检查/坐标变换
├── tools/openfoam_tools.py  求解序列 + 残差/forceCoeffs/checkMesh 解析
├── tools/validation.py      Cd 对比判据（20°→0.197 / 25°→0.285，±10%）
└── agents/*                 六阶段顺序编排（需求→几何→物理→网格→求解→分析）
examples/
├── verify_ahmed.py          端到端稳态验证（--slant 20/25）
├── animate_ahmed.py         瞬态 pimpleFoam 动画算例（复用稳态网格+初场）
├── resume_transient.py      中断续算（startFrom latestTime）
├── run_drivaerml.py         公开 DrivAerML 真实车辆 STL 低成本导入冒烟
└── paraview/
    ├── windtunnel_view.py   风洞视角截图（隐藏外壁/烟线/光片/车体/机位）
    ├── render_animation.py  离屏渲染动画序列帧
    └── save_state.py        生成带流线的 .pvsm 状态文件
docs/VALIDATION.md           八轮稳态实验档案（数据+归因+路线）
```

Agent 编排为**顺序协程调用**（确定性）；v0.2.0 遗留的 message_bus /
state_machine 死代码已在 v0.4.0 删除，README 不再宣称"消息总线+状态机"。

---

## 4. 已完成工作清单（commit 序）

| commit | 内容 |
|---|---|
| `5a1cd91` | 修复 ESI snappyHexMesh 尾流加密盒语法（内联 searchableBox 被静默忽略）；风洞设置（大域/滑移地面/低湍流入口）；八轮验证档案 |
| `abd1308` | v0.2.0：真实求解链路（RuntimeBridge/CaseBuilder/stl_tools/validation）+ 26→28 离线测试 |
| `b079dde` | 瞬态 pimpleFoam 模式 + 每个 case 生成 `<case>.foam` ParaView 标记 |
| `cd6a512` | 风洞视角脚本 + 中断续算脚本 |
| `73f9f0b` | 离屏动画渲染器（40 帧 → GIF 已生成于 `case/results/ahmed_wake_animation.gif`） |
| `99b935e` | 流线视角 .pvsm 状态文件生成器 |

同期 portfolio 级变更（其他仓库）：Berth-Scheduler 已并入 SmartPort-MultiAgent
（HiGHS 精确解/Imai 基准/灵敏度），Berth 仓加归档横幅；Profile README 同步。

---

## 5. 验证实验数据（全部真实求解输出，可复算）

稳态八轮（simpleFoam, k-ω SST, 壁面函数）：

| # | 设置 | 角 | 单元 | Cd | 参考 | 偏差 |
|---|---|---|---|---|---|---|
| 1 | 尖角前缘 | 25° | 418k | 1.056 | 0.285 | +271% |
| 2 | +圆角 R100/R50 | 25° | 417k | 0.582 | 0.285 | +104% |
| 3 | +表面 level3 | 25° | 785k | 0.559 | 0.285 | +96% |
| 4 | 改 20° | 20° | 787k | 0.547 | 0.197 | +178% |
| 5 | +阻塞比 4%+低湍流 | 20° | 674k | 0.493 | 0.197 | +150% |
| 6 | +上游滑移地面 | 20° | 676k | 0.491 | 0.197 | +149% |
| 7 | +nut/nu=5 | 20° | 676k | 0.487 | 0.197 | +147% |
| 8 | +wakeBox 生效 | 20° | 1151k | 0.491 | 0.197 | +149% |

瞬态一轮（pimpleFoam, 从稳态场起算, Co≤2, 527 步, 0→0.0783 s, 40 帧）：
**尾段平均 Cd = 0.522, Cl = 0.262**。

关键推论：瞬态均值与稳态同量级 → **稳态假设不是偏差主因**；设置级修正
（#2→#8）边际收益递减 → 偏差更可能来自**模型形态或几何本身**。

---

## 6. 已踩过的坑（都已解决，别再踩）

1. **wsl.exe 重定向输出是 UTF-16** → 日志必须在 WSL 内 bash 重定向
   （`cmd > log 2>&1`），capture 类调用加 `encoding='utf-8', errors='replace'`。
2. **ESI snappyHexMesh 的 refinementRegions 内联几何被静默忽略**（日志
   "entries were not used"）→ searchableBox 必须定义在 `geometry` 节再按名引用。
3. **symmetryPlane 必须共面**：一个 patch 合并两个平行平面会让 blockMesh 直接退出。
4. **forceCoeffs 输出 13 列**（Time Cd Cd_f Cd_r Cl Cl_f Cl_r Cm + 力/矩分量），
   注释头不含列名；解析器按列数判定 + `Cd=Cd_f+Cd_r` 交叉验证。
5. **ParaView 新版 API 坑**：`view.ActiveCamera` 不存在、`active_camera` 是方法、
   `GetActiveCamera()` 才返回可用 Set* 的相机；Clip 用 `Invert`（InsideOut 废弃）；
   OpenFOAM reader **只选 patch 的 MeshRegions 返回空** → 全读后用几何裁剪或直读 STL。
6. PowerShell 5.1 读写文件默认 GBK，会毁掉 UTF-8 中文 → 一律用 Python 或显式 UTF8。
7. `python` 命令是 MS Store 桩 → 用 `E:\Anaconda\python.exe` 全路径。

---

## 7. 接手审查指南（我认为可能不对 / 可以更好的地方）

**A. Cd 偏差归因（最高优先）**。我的归因链：圆角必要（1.056→0.58 证实）→
其余设置级修正无效 → 归因模型形态+无支腿。**请复核**：
1. 画 y+ 分布与基座压力系数 Cp_base，对照文献（Ahmed 25° 基座 Cp≈-0.4 量级）；
   若基座吸力过强，问题可能在尾流/基座分辨率而非湍流模型。
2. 做**网格收敛研究**（3 套网格，GCI）——我只做了单点加密对比，不构成收敛证据。
3. 换**标准 Ahmed STL**（带支腿的公开模型）重跑，隔离几何简化因素。
4. 20° 应是附着流：检查斜面是否有数值分离（ streamline 贴附情况）；若有人为
   分离，先修分离再谈精度。
5. 尝试 k-ω SST **low-Re（y+≈1）** 网格（需 300–500 万单元，本机串行约数小时/轮，
   可接受后台跑）或 IDDES；这是达到 ±10% 最可能的路径。

**B. 验证方法论**。±10% 判据是我自设的；20° 实验值 0.197 与 25° 0.285 均来自
Ahmed 1984，注意不同文献取值略有差异。瞬态只跑了 0.078 s（≈3 对流时间），
统计平均不充分，若走瞬态路线需加长采样。

**C. 代码架构**。六阶段是顺序协程调用（v0.4.0 起如实描述，bus/state_machine
已删）。若要走"真多 Agent"路线，可按阶段边界引入总线 + 状态机驱动的重试/
回退（例如网格质量不过自动降级别重跑）。

**D. ParaView 脚本**。我靠 try/except 双名兼容糊过了版本差异；更干净的做法是
检测 ParaView 版本后分支，或改用 trame/官方 state 模板。

**E. 性能**。WSL 串行求解是瓶颈；可开 `decomposePar` 并行（WSL 核数充足），
bridge 里加 `mpirun -np N` 路径即可，我未做。

---

## 8. 快速复现命令

```powershell
cd e:\GitHub项目\aeroforge-agent
E:\Anaconda\python.exe -m pytest tests -q                 # 以本机新鲜输出为准
E:\Anaconda\python.exe examples/verify_ahmed.py --slant 20   # 稳态验证（~35min）
E:\Anaconda\python.exe examples/animate_ahmed.py             # 瞬态动画算例（~1.5h）
E:\Anaconda\python.exe examples/resume_transient.py          # 续算
D:\ParaView\bin\pvpython.exe examples/paraview/render_animation.py  # 旧版底层动画帧脚本
D:\ParaView\bin\pvpython.exe examples/paraview/save_state.py        # 流线 .pvsm
# 推送：git -c http.proxy=http://127.0.0.1:7890 -c https.proxy=http://127.0.0.1:7890 push origin main
```

现成产物：`workspace/task_6d95b6d1/case/results/` 下
`ahmed_wake_animation.gif`（40 帧动画）、`windtunnel_view.png`（静帧）、
`windtunnel_streamlines.pvsm`（流线状态）、`verification_report.md`。

---

## 9. 给接手者的一句话

链路是通的、数据是真的、报告是诚实的；**精度还没达标，而且我的归因只是假设**。
请先做 §7-A 的复核实验，再决定把算力投给网格、湍流模型还是几何。祝顺利。

---

## 10. 2026-08-30 审查增补

本轮审查新增了收敛证据门禁、偏航开放边界、ASCII/binary STL 统一校验、几何
封闭性/法向修复、显式上传失败保护、运行时超时和状态传播。完整证据与未完成
事项见 [`docs/AUDIT_2026-08-30.md`](docs/AUDIT_2026-08-30.md)。

注意：工作区 `diag_case5` 中历史 `verification_report.md` 的 Cd=0.449 与更晚
`coefficient.dat`（尾段约 0.486）不一致；这是后处理时间选择问题，不能把两者
当作同一轮结果。重做 Ahmed 验证前应清理/隔离旧 `postProcessing`，并固定算例
目录、字典和后处理时间范围。

---

## 11. 2026-08-31 车型资产、流线表示与产品动画增补

- 品牌车型现在必须提供水密 STL 与 `ModelAssetManifest`，在几何导入前核对来源、
  许可证和 SHA-256；不得再把“宝马/奥迪/小鹏”等任务静默替换为简化车。
- 仓库只记录大众、奥迪、宝马、小鹏、理想、问界的候选获取页面及许可风险，
  不捆绑受限源模型，详见 `docs/VEHICLE_ASSET_POLICY.md`。
- CLI 新增 `--vehicle-color`、`--animation`、`--animation-mode`、`--animation-frames`、
  `--animation-fps`。稳态默认是冻结真实 `U(x)` 中的无质量示踪粒子输运，相机环绕
  是显式可选模式；只有 `pimpleFoam` 多物理时间步才可标作瞬态。产物清单记录模式、
  源 U/几何/模板哈希、实际 GIF 延时/MP4 帧率和粒子输运时间。
- 流线种子已从三条 Line 改为与 `internalMesh` 相交的有限近车身 YZ 播种面（15×11），
  覆盖车身可见截面；箭头显式绑定 `U` 方向、关闭速度缩放并固定长度，低速箭头过滤，
  颜色/色标只表示 `|U|`。模板和图注均不把箭头密度当作烟雾浓度。
- 当前可交付演示位于 `docs/media/drivaerml_steady_particles.gif/.mp4`（120 帧、
  40 fps、约 3 s 播放）以及 `docs/media/drivaerml_steady_particles.html`；HTML 可鼠标
  轨道旋转/滚轮缩放，含蓝—青—黄—红 `|U| (m/s)` 色标、输运时间滑块和前视/尾流/俯视/
  后视镜/车尾细节预设。
  `docs/media/drivaerml_steady_orbit.gif/.mp4` 与三机位蓝色车身静帧仍保留。它们来自
  DrivAerML 展示算例，不构成气动力精度证明。
- 测试临时目录由 `pytest.ini` 固定在 `workspace/_scratch/pytest`，MP4 编码临时文件
  使用目标输出目录并在成功/失败后清理；本轮没有新增 C 盘媒体或缓存。

具体车型运行示例：

```powershell
aeroforge "宝马 X3 外流场 30 m/s" `
  --upload-stl D:\models\bmw_x3_closed.stl `
  --model-manifest D:\models\bmw_x3_manifest.json `
  --vehicle-color "#1A80E6" `
  --animation
```
