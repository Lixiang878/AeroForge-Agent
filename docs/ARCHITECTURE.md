# Architecture

## 流水线

六个确定性阶段，由 OrchestratorAgent 顺序编排：

```
RequirementParser   自然语言 → SimulationTask（速度/工况/对象，Pydantic 校验）
GeometryHunter      参数化 STL（Ahmed/车/圆柱/NACA）或上传 → 包围盒 + 特征长度
PhysicsConfig       CaseBuilder 从零写完整算例（0/ constant/ system/ triSurface/）
MeshSmith           RuntimeBridge 执行 blockMesh → surfaceFeatureExtract
                    → snappyHexMesh -overwrite → checkMesh（质量门禁）
SimulationPilot     simpleFoam（k-ω SST 稳态 RANS）→ 残差 + forceCoeffs 解析
ResultAnalyst       Markdown 报告 + 可视化（dry-run 时显式标注）
```

## 运行时桥接（RuntimeBridge）

- 三态：`native`（PATH 中有 simpleFoam）/ `wsl`（Windows + WSL 内 OpenFOAM）/
  `unavailable`（显式 dry-run）。
- WSL 路径：`wslpath -u` 转换（失败时规则回退盘符 → /mnt/<drv>）；日志在
  bash 内部重定向（`cmd > log 2>&1`），规避 wsl.exe 重定向产生 UTF-16 的问题。
- 探测结果进程内缓存；冷启动超时 60s + 重试一次。

## 契约与诚实性

- Pydantic v2 模型定义 Task/Report 契约；dry-run 用显式状态表示，
  绝不把未求解结果报告为"已收敛 CFD"。
- checkMesh 失败 → 求解阶段跳过；力系数缺失 → 报告标注 N/A。

## 通信层

当前消息总线为进程内 asyncio Queue，适配概念验证规模。分布式部署可在
不修改 Agent 契约的前提下替换该层。
