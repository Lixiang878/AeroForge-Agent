# Changelog

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
