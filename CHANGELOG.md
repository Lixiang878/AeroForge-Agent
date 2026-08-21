# Changelog

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
