# AeroForge-Agent

**一句话 → CFD 仿真 → 风洞级可视化。**

> 接手 / 审查者请先读 [`HANDOVER.md`](HANDOVER.md)：已做工作、当前真实状态、
> 已知坑、未达标项与复核指南都在那里。

你说一句自然语言，AeroForge 完成剩下的全部流程：参数化几何 → 从零生成
OpenFOAM 算例 → 网格（blockMesh + snappyHexMesh + checkMesh 质量门禁）→
稳态 RANS 求解（simpleFoam, k-ω SST）→ 气动力（Cd 压差/摩擦分解）→
**真实场的风洞烟线高清渲染**。检测到 OpenFOAM 运行时（本机或 WSL）即执行
真实求解；检测不到则显式降级为 dry-run——**绝不把 dry-run 伪装成收敛的
CFD，也绝不用合成场伪造可视化**。

```bash
aeroforge "做一辆 宝马X3 的迎风仿真，风速 120 km/h，风向角 0 度" \
          --upload-stl x3.stl        # 真实车型建议上传 STL
```

## 效果（真实求解场离屏渲染，非示意图）

| 3/4 前侧 | 正侧（中线烟幕） | 后上尾流 |
|---|---|---|
| ![front](docs/img/streamline_hd_front.png) | ![side](docs/img/streamline_hd_side.png) | ![wake](docs/img/streamline_hd_wake.png) |

经典风洞烟线构图：中线垂直烟幕 + 两层横向排线（种子位置按几何包围盒
自动推导），速度着色 Cool-Warm 学术色表，Tube 烟线管 + 中心纵剖衬底，
2400×1350 离屏渲染。收敛求解完成后自动生成并嵌入 Markdown 报告；
无收敛场或未安装 ParaView 时如实跳过并在报告说明原因。

[English](#english) · [中文](#中文)

---

<a id="english"></a>
## English

### What it does

Six deterministic stages, one sentence in, wind-tunnel pictures out:

```
RequirementParser → GeometryHunter → PhysicsConfig → MeshSmith → SimulationPilot → ResultAnalyst
   speed / yaw /      parametric      full case from   blockMesh +      simpleFoam        pvpython HD
   object from NL     STL or upload   scratch           snappy + gates   k-omega SST       smoke-line renders
```

- **RuntimeBridge** routes every OpenFOAM call to an available backend:
  native install, or **WSL on Windows** (auto-detected), with explicit
  dry-run when nothing is found.
- **Wind angle (yaw)** rotates the inlet vector, moving ground and drag
  direction together (`风向角 30°` just works).
- Force coefficients come with a **pressure/viscous breakdown** parsed
  from the solver log (the `.dat` `Cd(f)/Cd(r)` columns are NOT that
  split — we document the trap).
- Mesh quality is gated by `checkMesh`; failed mesh → no solver run.
- Visualization renders the **actual converged field** via pvpython
  (ParaView). No fake synthetic plots — those were removed in v0.4.0.

### Quick start

```bash
pip install -e '.[dev]'
pytest -q                                    # offline unit tests (no OpenFOAM needed)

python examples/demo_bmw_x3.py               # one-sentence demo (upload a real STL!)
python examples/paraview/streamline_hd.py <case_dir>   # re-render any solved case
python examples/verify_ahmed.py              # end-to-end validation vs experiment
python examples/animate_ahmed.py             # transient run for ParaView animation
```

OpenFOAM: Linux → PATH; Windows → install inside WSL (RuntimeBridge
discovers it). ParaView (for visualization) is optional; without it the
pipeline still runs and the report says exactly why renders are missing.

### Design boundary (honesty statement)

This is a reproducible **RANS engineering workflow**, validated against
the classical Ahmed body (see below). It does not claim industrial CFD
accuracy: turbulence model choice, near-wall resolution and geometry
simplifications all matter. Parameterized car shapes are simplified
boxes — upload an STL for real vehicle geometry. Dry-run and real-solver
outputs are never mixed or relabelled.

### Credibility: Ahmed body validation

Classical benchmark (Ahmed et al. 1984, SAE 840300; Re≈2.78e6). Twelve
traceable experiment rounds (full story in
[`docs/VALIDATION.md`](docs/VALIDATION.md)) took Cd from a naive 1.056
to **0.449** at the 20° attached-flow angle (experiment 0.197), with the
v0.3.0 root-cause revision: pressure drag dominates (96%), and the
leading residual error is unresolved nose curvature — *not* friction or
model form as first attributed. Reaching ±10% requires level-6 nose
refinement (~8M cells) or transient + time averaging; both are on the
roadmap. Every number above is a real solver output.

---

<a id="中文"></a>
## 中文

### 架构

六个阶段由 `OrchestratorAgent` 顺序编排（确定性、可离线测试）：
需求解析（自然语言 → 速度/风向角/工况/对象名，车型关键词词典 + 引号 +
裸文本三级提取）、几何获取（参数化 Ahmed/简化车/圆柱/NACA 或上传 STL）、
物理配置（从零生成完整 OpenFOAM 算例；风向角旋转入口矢量/移动地面/阻力
方向）、网格（blockMesh → surfaceFeatureExtract → snappyHexMesh →
checkMesh 质量门禁）、求解（simpleFoam k-ω SST；残差、力系数及压差/摩擦
分解）、分析与可视化（pvpython 三机位烟线图嵌入 Markdown 报告）。

核心契约用 Pydantic v2 定义；编排为直接协程调用（v0.2.0 的
message_bus/state_machine 从未被使用，v0.4.0 已删除）。

### 快速开始

```bash
pip install -e '.[dev]'
pytest -q                                    # 离线单元测试（无需 OpenFOAM）

python examples/demo_bmw_x3.py               # 一句话体验（真实车型建议 --upload-stl）
python examples/paraview/streamline_hd.py <case_dir>   # 对已求解算例重新渲染
python examples/verify_ahmed.py              # 端到端基准验证
python examples/animate_ahmed.py             # 瞬态运行动画素材
```

OpenFOAM 接入：Linux 装到 PATH；Windows 在 WSL 中安装（自动探测）。
ParaView 可选（可视化用）；缺失时流程照常跑完，报告如实说明渲染跳过原因。

### 关键设计

- **RuntimeBridge 三态运行时**：native / WSL / 不可用，显式 dry-run。
- **风向角一句话支持**：`风向角 30°` 同时旋转入口、移动地面与阻力方向，
  升力方向不变；侧向域 2.5W，大偏航角时建议自行扩大侧向边界。
- **可视化只画真实场**：pvpython 自动发现（PATH/常见目录）→ 模板脚本
  离屏渲染 → 产物校验；两处已固化的坑——CellData 必须先转 PointData，
  VisRTX 后端画不了线（显式建 OpenGL RenderView + Tube 烟线管）。
- **力系数压差/摩擦分解**来自求解日志（v2412 dat 的 Cd(f)/Cd(r) 列并非
  摩擦/压差，勿误读——本项目 v0.2.0 曾因此误判）。
- **低 Re 壁面预设**（默认）+ 前缘/尾流加密盒；经典壁面函数保留为
  `wall_treatment="wallFunction"` 快速回退。
- **基准验证**：Ahmed body 20° 定量判据角 / 25° 如实报告角，十二轮可追溯
  实验与 v0.3.0 归因修订见 [`docs/VALIDATION.md`](docs/VALIDATION.md)。

### 设计边界（诚实声明）

本项目是**可复现的 RANS 工程流程**，不宣称工业 CFD 精度。参数化"车"是
简化方体（真实车型请上传 STL）；Ahmed 验证当前 Cd=0.449 vs 实验 0.197，
剩余偏差的前缘分辨率根因与改进路线已量化记录。dry-run 与真实求解输出
严格分离，可视化不用合成场伪造。

## License

MIT
