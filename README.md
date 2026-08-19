# AeroForge-Agent

AeroForge-Agent 是一个离线优先的 CFD 工作流多 Agent 概念验证系统：从自然语言任务解析开始，依次完成参数化几何、网格字典、OpenFOAM 配置、求解监控和后处理报告。

## 快速开始

```bash
pip install -e '.[dev]'
python examples/demo_bmw_x3.py
pytest -q
```

无 OpenFOAM 时，系统会生成明确标注的 dry-run 结果与合成可视化；安装 OpenFOAM v2412 后可接入真实 `blockMesh`、`snappyHexMesh`、`simpleFoam` 或 `pimpleFoam`。

## 架构

`RequirementParser → GeometryHunter → MeshSmith → PhysicsConfig → SimulationPilot → ResultAnalyst`，由 `OrchestratorAgent` 顺序编排。核心模型使用 Pydantic v2，通信基础设施提供 asyncio Queue 消息总线和状态机。

## 设计边界

本项目是概念验证，不宣称 dry-run 结果具有工业 CFD 精度。真实求解器、网格质量和力系数必须在 OpenFOAM 环境中复核。
