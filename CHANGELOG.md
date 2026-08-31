# Changelog

## Unreleased - 2026-08-31

### Visualization and vehicle asset refinement
- Re-rendered the DrivAerML showcase with a light paper-style composition,
  Viridis colouring (Cividis fallback), a data-driven physical speed range with
  8% headroom, and automatic log10 scaling only when the sampled `|U|` span is
  wide. Scalar bars are larger, framed, and labelled in m/s; direction arrows
  remain fixed-length and neutral.
- Increased the default playback rate to 40 fps (120 frames, about 3 s) while
  retaining the same `IntegrationTime`-based tracer interpolation and release
  cadence, so motion is faster without changing the underlying CFD field.
- Added `p7_visual_sanitized.glb` as a material-preserving, visual-only derivative
  of the user-supplied XPeng P7 OBJ. The non-finite material group was excluded;
  the original OBJ remains the provenance record and neither asset is accepted as
  a CFD wall until a separately repaired watertight exterior passes `surfaceCheck`.

## Unreleased - 2026-08-30

### Reliability audit
- Added a fail-closed asset manifest for named production vehicles: source URL,
  license, SHA-256, units, axes and rights must accompany an uploaded STL;
  missing or mismatched evidence no longer falls back to the simplified car.
- Added configurable uniform body paint (`--vehicle-color`) and a production
  animation path (`--animation`): actual OpenFOAM `U` and `IntegrationTime` drive
  steady-field tracers, with camera orbit as an explicit alternative. Transient
  frames retain physical pimpleFoam times; GIF/optional MP4 outputs carry field,
  geometry, template and media hashes plus distinct transport/playback timing.
- Reject transient-to-steady relabelling, mismatched CFD/display geometry and
  mismatched requested/manifest vehicle identity. Corrected the nose direction
  to upstream -X (freestream +X) and made manifest units control scale conversion.
- Documented legally safer acquisition candidates for Volkswagen, Audi, BMW,
  XPeng, Li Auto and AITO without bundling or redistributing restricted meshes.
- Added evidence-based solver gates for residuals, global continuity, `End`, mesh status, and fresh force-coefficient output; non-converged coefficients are hidden from reports and CLI output.
- Corrected transient mode selection (`pimpleFoam`), yaw far-field boundary conditions and projected reference area, translated-domain top margin, numeric WSL OpenFOAM version selection, and pipeline status propagation.
- Hardened ASCII/binary STL validation and repaired the generated car, Ahmed, cylinder, and NACA surfaces used by the examples (closure/connectivity/orientation).
- Added audit regressions for STL streaming/normalization, upload controls, short-run
  field/force write intervals, and pipeline gates; the full suite now has 160 tests.
- Added a reproducible DrivAerML public-vehicle import path (CC BY-SA 4.0), with
  watertight/surfaceCheck evidence, optional scale/ground/rotation transforms, and
  `examples/run_drivaerml.py` (explicit smoke/showcase profiles).
- Replaced the three-layer streamline seed with one finite 15×11 near-body YZ
  seeding plane clipped to `internalMesh`; removed spherical nodes and added
  fixed-length arrows oriented by `U`. Streamline colour remains the fixed,
  measured `|U|` range, with explicit steady-field tracer-advection metadata.
- Decoupled steady-particle releases from video frame count: 64 releases per
  transport cycle, at least two frame intervals of trail history, and stable
  path/release arrow selection rendered with `GlyphMode=All Points`; the
  verified showcase is now 120 frames at 40 fps.
- Added a self-contained Plotly orbit viewer (`interactive_viz.py` plus the
  pvpython exporter) with a physical `|U| (m/s)` colourbar, fixed-length
  U-oriented arrows, play/pause and transport-time slider, preset cameras,
  mouse orbit and wheel zoom. It exports the actual OpenFOAM field and a
  bounded VTK display mesh, never a synthetic velocity field.
- Recorded the user-supplied XPeng P7 ZIP on the E: volume with hashes and
  an asset audit. Its OBJ/MTL is a visual candidate only: one component has
  non-finite coordinates and the assembled surface is not watertight, so it
  is not passed into the DrivAerML CFD case.
- Kept pytest basetemp and MP4 encoding scratch files on the E: project volume;
  failed encodes clean their destination-local temporary file. The current full
  suite count is recorded by the final verification command below.
- Reworked the ParaView template around finite field sampling, a neutral vehicle
  material, Viridis colouring (Cividis fallback; log10 when the sampled speed range is wide), stable
  camera framing, and depth/opacity controls;
  it still renders only actual OpenFOAM fields. StreamTracer now explicitly selects
  the CFD `U` vector instead of inheriting STL surface normals, so roof and upper
  streamlines are retained.
- Replaced the repository README preview images with a verified DrivAerML showcase
  render; the denser showcase case is documented as illustrative, not mesh-independent.
- See [`docs/AUDIT_2026-08-30.md`](docs/AUDIT_2026-08-30.md) for evidence and unresolved CFD-accuracy work.

## 0.4.0 - 2026-08-23

**回归初心：一句话 → 仿真 → 风洞级可视化。** v0.3.0 期间项目重心漂移到
Ahmed Cd 定量验证的学术路线上，可视化环节反而仍是合成假图。本版把主线
拉回"好看的真实场可视化"，并清理虚饰与冗余。

### Fixed（可视化三连坑——v0.2.0 假图 + 渲染不可见根因）
- **删除假图**：`viz_tools` 的 `plot_velocity_field/plot_streamlines/
  plot_pressure_surface` 用 tanh/正弦合成场画"CFD 图"且调用时传入 None，
  从未读过任何真实数据。已彻底删除，报告改为嵌入真实渲染图。
- **CellData 陷阱**：OpenFOAM reader 输出的场在 CellData，必须先
  `CellDatatoPointData` 再喂 `StreamTracer/Slice`，否则流线积分为空、
  切片无法着色。
- **VisRTX 渲染后端画不出线**：ParaView 落在 VisRTX 后端时线与半透明
  全部不可见（不透明 STL 正常，极具迷惑性）。修复：显式
  `CreateView('RenderView')`（OpenGL）+ 流线转 **Tube 不透明管**
  （同时更接近风洞烟线质感）。
- **种子位置硬编码错误**：烟线种子曾落在车体内部（被删单元区），
  一条流线都追不出来；现按 STL 包围盒自动推导上游烟线源。
- **二进制 STL 解析**：渲染脚本只认 ASCII STL；现自动识别二进制格式
  （80B 头 + uint32 面数 + 50B/面）。

### Added
- **windtunnel_viz 模块**：pvpython 自动发现（PATH/常见安装目录）→
  模板脚本（随包分发）离屏渲染三机位 2400×1350 烟线图 → 产物校验。
  无收敛场/无 pvpython → skipped + 原因入报告，绝不造假图。
- **风洞烟线构图**：中线垂直烟幕 + 两层横向排线，速度 Cool-Warm 着色
  （量程自适应 1.08×自由流），深色地面 + 中心纵剖衬底 + 色标图例；
  三机位（3/4 前侧 / 后上尾流 / 正侧）按包围盒自动取景。
- **风向角（偏航）一句话支持**：`风向角 30°` 同时旋转入口矢量、移动
  地面与 forceCoeffs 阻力方向（升力恒 z）；`SimulationTask.yaw_angle_deg`
  → `CaseSpec.yaw_angle_deg`。
- **对象名三级提取**：引号 > 车型/物体关键词词典（宝马/奔驰/Ahmed/
  NACA/圆柱…，中英混排含 `宝马 X3` 空格合并）> 去停用词兜底。
- **CLI 升级**：`aeroforge "…" --upload-stl x.stl --no-viz`，输出报告
  路径、Cd 及压差/摩擦分解、可视化图路径或跳过原因。
- 测试 32→41（可视化诚实性 / 偏航矢量旋转 / 对象名与风向角解析 /
  dry-run 零假图契约）。

### Removed
- `core/message_bus.py`、`core/state_machine.py`：编排层从未使用的
  死代码（README 曾宣称"消息总线+状态机通信层"，与事实不符，一并纠正）。
- workspace 十六个 task_*/diag_* 旧算例目录（6.6GB→1.5GB，仅保留最优
  验证算例 diag_case5；全部结论已固化在 docs/VALIDATION.md）。

## 0.3.0 - 2026-08-22

### Fixed（Cd 偏差根因修复——推翻 v0.2.0 的归因）
- **力系数分解语义纠错**：v2412 `coefficient.dat` 的 `Cd(f)/Cd(r)` 列并非
  摩擦/压差分解（实测各约为 Cd 之半）；真实分解在求解日志 forceCoeffs 块的
  Pressure/Viscous 列。据此重审 v0.2.0 八轮实验：摩擦分量一直正常
  （~0.018），**96% 的 Cd 来自压差阻力**，"壁面函数高估摩擦"的旧假设不成立。
- **前缘曲率未解析（真正主因）**：R100 前鼻圆角仅 8 段离散 + 表面网格
  ~33mm，圆角上仅约 5 个单元，加速吸力峰无法形成，整个前表面近钝体滞止
  （Cp 均值 +0.62、无负压区），前缘压差贡献 ~0.42（正常 ~0.1）。
  修复：`arc_segments` 8→24、新增前缘加密盒 `noseBox`（level 5）。
- **边界层分辨率**：2 层相对厚度边界层 + 对数律壁面函数（y+ 2.4–652 跨
  缓冲区）不足以支撑外气动精度；新增 low-Re 壁面处理预设（见 Added）。

### Added
- **low-Re 壁面预设**（`CaseSpec.wall_treatment="lowRe"`，新默认）：15 层
  绝对厚度边界层，首层厚度按目标 y+（1.2）与平板经验 Cf 自动估算
  （40 m/s 下约 12μm）；nut→nutUSpaldingWallFunction（全 y+ 范围有效）、
  k→kLowReWallFunction。原 2 层壁面函数配置保留为
  `wall_treatment="wallFunction"` 快速筛查回退。
- **前缘加密盒 noseBox**：罩住前鼻圆角与滞止线（外扩 0.2L，level 5）。
- **压差/摩擦分解解析**（`parse_force_breakdown`）：从求解日志提取
  Pressure/Viscous 分解入 `ForceCoeffs.cd_pressure/cd_viscous`，
  验证报告自动展示。
- **并行求解配置生成**：`CaseSpec.n_parallel` 设置时自动生成
  `system/decomposeParDict`（scotch）。
- **表面分区 Cp 诊断工具** `examples/surface_cp_zones.py`：读收敛场按
  外法向分区（前表面/顶面/斜面/基座/侧面/底面）输出面积加权 Cp 与压差
  阻力贡献，用于偏差归因（零求解成本）。
- 新增 4 个离线测试（low-Re 层参数估算 / wallFunction 回退 / 分解解析 /
  缺失日志回退），共 32 tests。

### Changed
- `verify_ahmed.py` 默认参数升级为推荐配置：表面 level 4、迭代 2500。
- `max_global_cells` 默认 3M→8M（低 Re 网格规模需要）。

## 0.2.0 - 2026-08-20

### Added
- **真实 OpenFOAM 求解路径**：RuntimeBridge 三态运行时（native / WSL / 不可用），
  Windows 上自动探测 WSL 内 OpenFOAM（v2412），日志在 WSL 内部重定向以规避
  wsl.exe 的 UTF-16 转码问题。
- **CaseBuilder**：从零生成完整算例（0/constant/system + triSurface），替代
  "克隆 motorBike tutorial" 的旧路径；风洞域按包围盒自动外扩，入口湍流按
  强度-长度尺度公式给定，`forceCoeffs` 按迎风面积自动归一。
- **Ahmed body 参数化几何**（纯 Python 生成封闭 binary STL，含前鼻圆角
  R100/R50 与流形封闭性/外法向一致性检查）与 `examples/verify_ahmed.py`
  端到端基准验证（支持 20°/25° 两个验证角，自动生成 verification_report.md）。
- **验证档案** `docs/VALIDATION.md`：八轮真实 OpenFOAM 实验的可追溯记录
  （Cd 1.056 → 0.58 → 0.56 → 0.55 → 0.49 → 平台期 0.49；设置级修正全部
  同向逼近实验值，剩余偏差归因于稳态 RANS/壁面函数模型形态与无支腿
  简化几何，改进路线如实记录）。
- 网格质量门禁：checkMesh 不通过即终止求解。
- 风洞工程设置：阻塞比≈4% 大域、上游地面滑移（模拟边界层吸除）、
  低湍流入口（I=0.5%，远场 nut/nu=5）、尾流加密盒。
- **瞬态动画能力**：CaseBuilder 支持 transient 模式（pimpleFoam / Euler /
  PIMPLE / CFL 自适应步长）；`examples/animate_ahmed.py` 复用已收敛稳态场
  作初场继续瞬态演化，按动画帧写盘；每个算例目录生成 `<case>.foam`
  标记文件，ParaView 直接打开即可播放涡脱落/尾迹摆动的动态过程。
- 新增 16 个离线单元测试（STL 工具 / CaseBuilder / RuntimeBridge / 解析器 / 验证）。

### Changed
- 流水线顺序调整为 需求解析 → 几何 → 物理配置(建 case) → 网格 → 求解 → 分析。
- dry-run 不再伪造气动系数（原 Cd=0.4 假值已移除），报告中显式标注 N/A。
- 力系数解析改为表头感知的列定位 + 稳态尾段均值。

### Fixed
- symmetryPlane patch 非共面导致 blockMesh 崩溃（侧壁拆分为 sideLow/sideHigh）。
- wslpath 只接受绝对路径：runtime_path 统一先 resolve。
- WSL 冷启动探测超时（60s + 重试 + 进程内缓存）。
- wsl.exe 重定向产生 UTF-16 日志：改为在 WSL 内部 bash 重定向日志。
- omega 场量纲错误（[0 0 -1]，原误用 k 的量纲导致 simpleFoam 崩溃）。
- movingWallVelocity 边界条件字典格式错误。
- forceCoeffs 列解析：按 ESI OpenFOAM v2412 实际 13 列格式定位 Cd/Cl/Cm
  （经 Cd=Cd_f+Cd_r、Cl=Cl_f+Cl_r 数值关系交叉验证）。
- snappyHexMesh 尾流加密盒被静默忽略：内联 searchableBox 写法在 ESI 版
  无效（“entries were not used”），改为 geometry 节定义 + refinementRegions
  按名引用后加密首次生效（网格 67 万 → 115 万单元）。

## 0.1.0 - 2026-08-19

- Initial offline-first CFD multi-agent workflow.
