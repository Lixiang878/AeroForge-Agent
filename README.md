# AeroForge-Agent

**离线优先的 CFD 多 Agent 工作流：从一句自然语言到真实 OpenFOAM 求解与基准验证。**

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

**当前验证状态（如实声明）**：五轮可追溯实验（见 [`docs/VALIDATION.md`](docs/VALIDATION.md)）
显示每次工程修正都使 Cd 单调趋向实验值（尖角 1.056 → 圆角 0.58 → 网格/尾流
加密 0.56 → 扩域+低湍流 0.49），但绝对精度尚未达到 ±10% 容差；剩余偏差的
主要来源（上游地面边界层、壁面函数 y+、几何简化）与改进路线均记录在案。
诚实边界见下文「设计边界」。

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
```

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
- **CaseBuilder 模板化算例生成**：风洞域按几何包围盒自动外扩（上游 3L / 下游 6L /
  侧向 1.5W / 顶部 2.5H），入口湍流按强度-长度尺度公式给定，地面可选移动壁面
  （地面效应），`forceCoeffs` 函数对象自动按迎风面积归一。
- **质量门禁**：checkMesh 不通过则终止求解；dry-run 时所有气动系数为 N/A，
  报告明确标注。
- **基准验证**：Ahmed body 25°，参考 Cd=0.285，±10% 容差，验证结论写入
  `verification_report.md`。

### 快速开始

```bash
pip install -e '.[dev]'
pytest -q                        # 离线单元测试（无需 OpenFOAM）

python examples/demo_bmw_x3.py            # Agent 流水线演示
python examples/verify_ahmed.py           # 端到端真实验证（20°，需 OpenFOAM）
python examples/verify_ahmed.py --slant 25  # 经典 25° 工况（如实报告）
```

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
