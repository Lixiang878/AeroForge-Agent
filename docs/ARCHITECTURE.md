# Architecture

## 流水线

六个确定性阶段，由 OrchestratorAgent 顺序编排：

```
RequirementParser   自然语言 → SimulationTask（速度/风向角/工况/对象，Pydantic 校验）
GeometryHunter      参数化 STL（Ahmed/车/圆柱/NACA）或上传 → 包围盒 + 特征长度
PhysicsConfig       CaseBuilder 从零写完整算例（0/ constant/ system/ triSurface/；
                    风向角旋转入口矢量/移动地面/阻力方向）
MeshSmith           RuntimeBridge 执行 blockMesh → surfaceFeatureExtract
                    → snappyHexMesh -overwrite → checkMesh（质量门禁）
SimulationPilot     simpleFoam（k-ω SST 稳态 RANS）→ 残差 + forceCoeffs 解析
                    （含压差/摩擦分解）
ResultAnalyst       windtunnel_viz 调 pvpython 离屏渲染三机位烟线图 →
                    Markdown 报告嵌图（dry-run/未收敛不渲染、不伪造）
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

## 可视化（windtunnel_viz）

- 模板脚本随包分发（`tools/pv_templates/streamline_hd.py`），自动定位
  pvpython（PATH / 常见安装目录）离屏渲染 2400×1350 三机位烟线图。
- 两个已踩过的坑：OpenFOAM reader 的场在 CellData，必须先
  CellDatatoPointData 再喂 StreamTracer/Slice；ParaView 若落在 VisRTX
  渲染后端，线与半透明画不出来——需显式 `CreateView('RenderView')`，
  流线建议用 Tube 转不透明管（同时更接近风洞烟线质感）。
- 诚实边界：无收敛场 / 无 pvpython → 状态 skipped + 原因写入报告，
  绝不回退到合成假图（v0.2.0 曾有此问题，v0.4.0 已移除）。

## 编排

六个阶段为顺序 asyncio 协程调用（确定性、可离线测试）。曾经存在的
message_bus/state_machine 从未被编排层使用，v0.4.0 已删除；如需分布式
重试/恢复，按阶段边界引入即可，Agent 契约不变。
