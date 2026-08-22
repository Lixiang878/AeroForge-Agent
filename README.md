# AeroForge-Agent

**离线优先的 CFD 多 Agent 工作流：从一句自然语言到真实 OpenFOAM 求解与基准验证。**

> 接手 / 审查者请先读 [`HANDOVER.md`](HANDOVER.md)：已做工作、当前真实状态、
> 已知坑、未达标项与复核指南都在那里。

AeroForge-Agent 是一个 CFD 工作流多 Agent 系统：需求解析 → 参数化几何 → 从零生成
OpenFOAM 算例 → 网格（blockMesh + snappyHexMesh）→ 稳态 RANS 求解（simpleFoam,
k-ω SST）→ 气动力提取与报告。检测到 OpenFOAM 运行时（本机或 WSL）即执行**真实求解**；
检测不到则显式降级为 dry-run——**绝不把 dry-run 伪装成收敛的 CFD 结果**。

[English](#english) · [中文](#中文)

## 基准验证（Ahmed body）

用经典 Ahmed body（Ahmed et al. 1984, SAE 840300，Re≈2.78e6）做端到端验证
（`examples/verify_ahmed.py`），几何为含前鼻圆角的参数化 STL（纯 Python 生成）：

| 验证角 | 实验参考 Cd | 定位 | 判据 |
|--------|------------|------|------|
| **20°（默认）** | 0.197 | 附体流动，稳态 RANS 适用区 | **定量通过判据：偏差 ≤ ±10%** |
| 25°（`--slant 25`） | 0.285 | 分离/再附双稳态过渡区 | 如实报告；粗网格壁面函数稳态 RANS 已知高估分离（文献散布 0.30–0.55+） |

求解：simpleFoam, k-ω SST 稳态 RANS；网格为背景六面体 + snappyHexMesh
（castellated + snap + 边界层 + 尾流加密盒）；力系数由 `forceCoeffs` 按迎风
面积归一后取稳态尾段均值。验证报告自动生成（`results/verification_report.md`），
含网格规模、checkMesh 结论、残差与求解耗时。

**当前验证状态（如实声明）**：十二轮可追溯实验（见 [`docs/VALIDATION.md`](docs/VALIDATION.md)）。
v0.2.0 的八轮把 Cd 从尖角的 1.056 修正到 0.49 平台期，当时归因于"RANS 模型
形态+无支腿几何"。v0.3.0 复核**推翻了该归因**：力系数压差/摩擦分解显示摩擦
一直正常（0.018）、压差占 96%；真主因是**前缘圆角曲率未被网格解析**（8 段
离散+6.5mm 级表面单元使吸力峰消失、前表面钝体滞止）。对照实验链（Spalding
壁面函数 -4.5%、仅加密几何 -1.2%、前缘盒 level5 **-8.4% 至 Cd=0.449**）验证
了新归因。剩余偏差（+128%）由前缘分辨率上限、无支腿简化与稳态 RANS 固有
散布主导，达 ±10% 需 level6 前缘（~800 万单元）或瞬态求解+时均，已列入
改进路线。所有数值均为真实求解输出。诚实边界见下文「设计边界」。

---

<a id="english"></a>
## English

### What it does

Six agents, one pipeline:

```
RequirementParser → GeometryHunter → PhysicsConfig → MeshSmith → SimulationPilot → ResultAnalyst
   NL task parse     parametric STL    build full      blockMesh +   simpleFoam     Cd/Cl + report
                     (Ahmed/car/       OpenFOAM case   snappyHexMesh (k-omega SST)  + markdown
                      NACA/cylinder/   from scratch    + checkMesh
                      uploaded STL)
```

- **RuntimeBridge** routes every OpenFOAM call to an available backend:
  native install, or **WSL on Windows** (auto-detected, e.g. `openfoam2412`),
  with explicit dry-run when nothing is found.
- **CaseBuilder** writes the entire case from templates: `0/` fields with
  proper BCs (moving ground, symmetry planes, wall functions),
  `constant/` properties, `system/` (controlDict with `forceCoeffs`,
  fvSchemes/fvSolution tuned for steady RANS, blockMeshDict sized from the
  geometry bounding box, surfaceFeatureExtractDict, snappyHexMeshDict).
- Mesh quality is gated by `checkMesh`: if it fails, the solver is not run.
- Force coefficients are parsed from `postProcessing/forceCoeffs` with
  header-aware column detection (steady tail averaged).

### Quick start

```bash
pip install -e '.[dev]'
pytest -q                        # offline unit tests (no OpenFOAM needed)

python examples/demo_bmw_x3.py            # agent pipeline demo
python examples/verify_ahmed.py           # end-to-end validation, 20 slant angle
python examples/verify_ahmed.py --slant 25  # classic 25-degree reporting case
python examples/animate_ahmed.py          # transient pimpleFoam run for ParaView animation
```

Every generated case contains a `<case>.foam` marker: open it in ParaView
(OpenFOAM reader) to play the time-resolved wake dynamics (vortex shedding)
after a transient run.

OpenFOAM paths:

- **Linux**: install OpenFOAM (e.g. v2412) so `simpleFoam` is on PATH.
- **Windows**: install a distro + OpenFOAM inside WSL; RuntimeBridge
  discovers `/usr/lib/openfoam/openfoam*` automatically.

Without OpenFOAM the pipeline still runs and produces a fully inspectable
case directory — but every result is clearly marked dry-run.

### Design boundary (honesty statement)

This is a reproducible **RANS engineering workflow**, validated against the
classical Ahmed body. It does not claim industrial CFD accuracy: turbulence
model choice, near-wall resolution and geometry simplifications (Ahmed body
without legs) all affect Cd. The 25-degree case sits in the bistable
separation regime where steady wall-function RANS is known to overpredict
separation (published spread 0.30-0.55+); the quantitative pass criterion
therefore uses the attached-flow 20-degree case. Dry-run outputs and
real-solver outputs are never mixed or relabelled.

---

<a id="中文"></a>
## 中文

### 架构

六个 Agent 由 `OrchestratorAgent` 顺序编排：需求解析（自然语言 → 结构化任务）、
几何获取（Ahmed/简化车/圆柱/NACA 参数化生成或上传 STL）、物理配置（**从零生成
完整 OpenFOAM 算例**，不再克隆 tutorial）、网格（blockMesh → surfaceFeatureExtract
→ snappyHexMesh → checkMesh 质量门禁）、求解（simpleFoam k-ω SST，解析残差与
力系数）、分析报告（Markdown + 可视化）。

核心模型用 Pydantic v2 定义契约；通信层为 asyncio 消息总线 + 状态机（概念验证级，
可替换为分布式实现而不改 Agent 契约）。

### 关键设计

- **RuntimeBridge 三态运行时**：native / WSL / 不可用。Windows 上自动发现 WSL 内
  OpenFOAM，日志在 WSL 内部重定向（规避 wsl.exe UTF-16 转码问题），路径经
  `wslpath` 转换。
- **CaseBuilder 模板化算例生成**：风洞域按几何包围盒自动外扩（上游 3L / 下游 7L /
  侧向 2.5W / 顶部 5H，阻塞比≈4%），入口湍流按强度-长度尺度公式给定，地面可选
  移动壁面（地面效应），`forceCoeffs` 函数对象自动按迎风面积归一。
- **低 Re 壁面预设（v0.3.0 默认）**：15 层绝对厚度边界层，首层按目标 y+ 自动
  估算（Ahmed 40 m/s 下 ~12μm）；`nutUSpaldingWallFunction`（全 y+ 范围有效）+
  `kLowReWallFunction`；经典 2 层壁面函数保留为 `wall_treatment="wallFunction"`
  快速筛查回退。
- **前缘加密盒 + 尾流加密盒**：`noseBox`（level 5）保证圆角曲率可解析——
  Ahmed 验证表明这是压差阻力精度的关键；`wakeBox` 覆盖斜面涡与基座回流。
- **力系数压差/摩擦分解**：从求解日志 forceCoeffs 块解析（v2412 dat 文件的
  Cd(f)/Cd(r) 列并非摩擦/压差，勿误读——本项目 v0.2.0 曾因此误判）。
- **质量门禁**：checkMesh 不通过则终止求解；dry-run 时所有气动系数为 N/A，
  报告明确标注。
- **基准验证**：Ahmed body 20°（定量判据角，参考 Cd=0.197）/25°（如实报告角），
  验证结论写入 `verification_report.md`。

### 快速开始

```bash
pip install -e '.[dev]'
pytest -q                        # 离线单元测试（无需 OpenFOAM）

python examples/demo_bmw_x3.py            # Agent 流水线演示
python examples/verify_ahmed.py           # 端到端真实验证（20°，需 OpenFOAM）
python examples/verify_ahmed.py --slant 25  # 经典 25° 工况（如实报告）
python examples/animate_ahmed.py          # 瞬态 pimpleFoam：生成 ParaView 可播放的动态过程
```

**ParaView 动态可视化**：每个生成的算例目录都含 `<case>.foam` 标记文件；
瞬态运行完成后用 ParaView 直接打开该文件（OpenFOAM reader），时间轴播放即可
看到尾流涡脱落/摆动的动态过程（变量选 U，可用 Slice/StreamTracer 观察涡结构）。

OpenFOAM 接入：Linux 直接装到 PATH；Windows 在 WSL 中安装（如 v2412），
RuntimeBridge 自动探测 `/usr/lib/openfoam/openfoam*`。无 OpenFOAM 时全流程
仍可离线运行并产出可审阅的算例目录，但结果一律标注 dry-run。

### 设计边界（诚实声明）

本项目是**可复现的 RANS 工程流程**，以经典 Ahmed body 做验证；不宣称工业 CFD
精度——湍流模型选择、近壁分辨率与几何简化（Ahmed 无支腿）都会影响 Cd。
25° 工况处于分离双稳态过渡区，粗网格壁面函数稳态 RANS 已知高估分离
（文献散布 0.30–0.55+），故定量通过判据取 20° 附体角，25° 结果如实报告。
dry-run 与真实求解的输出严格分离、不做混标。

## License

MIT
