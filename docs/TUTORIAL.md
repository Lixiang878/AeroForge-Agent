# AeroForge-Agent 使用教程

一句话 → 真实 OpenFOAM 求解 → 风洞级可视化。本文档覆盖本地运行、并行求解、
真实车辆 STL 与可视化产物的完整用法。

## 1. 环境准备

| 组件 | 必需 | 说明 |
|---|---|---|
| Python 3.10+ | 是 | `pip install -e '.[dev]'`（依赖见 pyproject.toml） |
| OpenFOAM | 求解必需 | Linux 装到 PATH；Windows 在 WSL 内安装（如 ESI v2412），`RuntimeBridge` 自动探测 |
| ParaView（含 pvpython） | 可选 | 高清渲染用；缺失时流程照常完成，报告如实说明渲染跳过 |

无 OpenFOAM 时全链路自动降级 dry-run：报告与 CLI 显式标注，不虚构气动系数。

## 2. 快速开始

```bash
pytest -q                                  # 离线单元测试（无需 OpenFOAM/ParaView）
aeroforge "做 Ahmed body 迎风仿真，风速 40 m/s，风向角 0 度"
aeroforge "车辆外流场 30 m/s" --upload-stl body.stl --model-manifest model.json --animation
```

产物（报告 Markdown、静帧、可选动画/交互 HTML）位于
`workspace/task_<hash>/case/results/`，路径在 CLI 输出末尾列出。

## 3. 真实车辆 STL

品牌车型必须提供**水密 STL + 资产清单 JSON**（来源 URL、许可证、SHA-256、
单位、轴向）；缺项或哈希不符即停止，不静默回退到简化车。公开可再分发数据
推荐 DrivAerML（CC BY-SA 4.0）：

```bash
python examples/run_drivaerml.py body_drivaerml_run_1.stl                 # 冒烟（160 步）
python examples/run_drivaerml.py body.stl --profile showcase              # 尾流展示（800 步）
python examples/run_drivaerml.py body.stl --profile showcase --n-parallel 8
```

## 4. 并行求解（v0.5.0）

`--n-parallel N`（N>1）启用并行：case 自动生成 `decomposeParDict`（scotch），
求解序列变为 `decomposePar -force → mpirun -np N <solver> -parallel → reconstructPar`。
稳态只重建最新场，瞬态（pimpleFoam）重建全部时间步供动画使用。

- CLI：`aeroforge "车辆外流场 30 m/s" --n-parallel 8`
- example：`run_drivaerml.py --n-parallel 8`
- 编程接口：`CaseSpec(n_parallel=N)`；`SimulationPilot` 自动接线。

行为与边界（实测记录）：

- **核数建议 ≤ 物理核数**；Windows + WSL 12GB 内存配额下 8 核是稳妥档。
- 力系数解析同时兼容两种 functionObject 并行行为：ESI v2412 各 rank 写
  reduce 后的全局汇总值（取单份）；若实现写局部积分则自动求和。
- 并行执行与数值正确性已在真实 WSL 算例验证：19 万单元 case 前 12 步
  Cd 演化与串行一致（iter10：并行 -2431 vs 串行 -2273）。
- **稳定裕度警告**：粗网格 + 均匀初场 + 大 `deltaT` 的 case 数值裕度低，
  分区求解的细微差异可能放大为发散（实测同一 showcase case 串行前 80 步
  Cd 在 ±3000 震荡后收敛，8 域并行在第 ~49 步发散）。长程并行求解请配合
  合理网格/边界层设置或更保守的松弛因子；发散时求解门禁会如实报失败，
  不会把发散数据晋升为结果。

## 5. 可视化产物

- **静帧**：pvpython 离屏三机位烟线图，蓝—青—黄—红 `|U|` 色标，只画真实场。
- **动画**：`--animation`；稳态默认为冻结 `U(x)` 场中的示踪粒子输运
  （120 帧/40 fps），`--animation-mode steady_orbit` 为相机环绕；
  瞬态 `--animation-mode transient` 只读 pimpleFoam 真实物理时间步，
  不把瞬态改标稳态。产物带清单（场/几何/模板哈希与时间口径）。
- **交互 HTML**：自包含 Plotly 页面，轨道旋转/缩放/时间滑块/预设机位，
  四种模式（连续流线/速度点云/尾流截面/组合），全部导出自真实 OpenFOAM 场。

## 6. 扩展开发

- 加几何：在 `geometry_tools.py` 实现 `create_*_stl` 三角面生成器并在
  `GeometryHunterAgent` 注册。
- 加求解器：在 `PhysicsConfigAgent` 把工况映射到 OpenFOAM 工具，并在
  `openfoam_tools.py` 扩展日志解析（残差/力系数/门禁）。
- 回归：`pytest -q` 离线全绿是合入门槛；涉及渲染的改动需用已求解 case
  重新渲染并目视确认（见 `docs/WORKSPACE_LAYOUT.md` 的产物区约定）。
