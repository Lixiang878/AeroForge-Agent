# Architecture

## 流水线

六个确定性阶段，由 OrchestratorAgent 顺序编排：

```
RequirementParser   自然语言 → SimulationTask（速度/风向角/工况/对象，Pydantic 校验）
GeometryHunter      参数化 STL（Ahmed/车/圆柱/NACA）或水密上传 STL →
                    品牌资产 manifest/许可/SHA-256 门禁 →
                    流式单区域转换（尺度/地面对齐/z 旋转）→ 包围盒 + 特征长度
PhysicsConfig       CaseBuilder 从零写完整算例（0/ constant/ system/ triSurface/；
                    风向角旋转入口矢量/移动地面/阻力方向）
MeshSmith           RuntimeBridge 执行 blockMesh → surfaceFeatureExtract
                    → snappyHexMesh -overwrite → checkMesh（质量门禁）
SimulationPilot     simpleFoam / pimpleFoam（k-ω SST）→ 残差、连续性、End、
                    forceCoeffs 收敛门禁（含压差/摩擦分解）
ResultAnalyst       windtunnel_viz 调 pvpython 离屏渲染三机位烟线图及动画；
                    interactive_viz 导出真实 U/IntegrationTime 的自包含 3-D HTML →
                    Markdown 报告嵌图/链接（dry-run/未收敛不渲染、不伪造）
```

## 运行时桥接（RuntimeBridge）

- 三态：`native`（PATH 中有 simpleFoam）/ `wsl`（Windows + WSL 内 OpenFOAM）/
  `unavailable`（显式 dry-run）。
- WSL 路径：`wslpath -u` 转换（失败时规则回退盘符 → /mnt/<drv>）；日志在
  bash 内部重定向（`cmd > log 2>&1`），规避 wsl.exe 重定向产生 UTF-16 的问题。
- 探测结果进程内缓存；冷启动超时 60s + 重试一次。

## 契约与诚实性

- Pydantic v2 模型定义 Task/Report 契约；dry-run/failed 用显式状态表示，
  绝不把未求解或未收敛结果报告为"已收敛 CFD"。
- 量产品牌车型必须提交模型资产清单，包含来源、许可证、源文件 SHA-256、单位、
  轴向和权利声明；缺少清单或哈希不匹配即停止，不允许退化为参数化简化车。
- checkMesh 失败、单元数缺失或网格报告不一致 → 求解阶段跳过；
  残差/连续性/日志结束标记/本次 forceCoeffs 任一缺失 → 结果不晋升。

## 可视化（windtunnel_viz）

- 模板脚本随包分发（`tools/pv_templates/streamline_hd.py` 和
  `streamline_animation.py`），自动定位
  pvpython（PATH / 常见安装目录）离屏渲染 2400×1350 三机位烟线图；
  `geometry_preview.py` 只渲染 STL 几何，不把它标作 CFD 结果。
- 两个已踩过的坑：OpenFOAM reader 的场在 CellData，必须先
  CellDatatoPointData 再喂 StreamTracer/Slice；ParaView 若落在 VisRTX
  渲染后端，线与半透明画不出来——需显式 `CreateView('RenderView')`，
  流线建议用 Tube 转不透明管（同时更接近风洞烟线质感）。
- 诚实边界：无收敛场 / 无 pvpython → 状态 skipped + 原因写入报告，
  绝不回退到合成假图（v0.2.0 曾有此问题，v0.4.0 已移除）。
- 结果模板使用有限透明近场采样面、感知均匀的 Viridis 连续色标（Cividis 回退）、稳定首帧相机和
  可配置统一车漆；速度跨度较大时切换带物理刻度的 `log10` 色标。色标与烟线来自
  真实 `U` 场，默认英雄图隐藏粗网格色块，采样面保留作诊断。
- 动画按 `controlDict` 的实际 `application` 确定源场语义：`simpleFoam` 的
  `auto` 选择 `steady_particles`，基于实际 `StreamTracer` 的 `IntegrationTime`
  和全局统一输运时钟推进无质量示踪粒子；`steady_orbit` 是可选相机环绕。
  `pimpleFoam` 只进入真实物理时间步模式，少于 3 个时跳过，不能改标稳态。
- 输出 GIF/可用时的 MP4，并以 `render_manifest.json` 记录源场/几何/模板哈希、
  求解时刻、粒子输运时间和实际视频帧延时。原始 STL 与 CFD 表面不一致则拒绝渲染；
  无质量粒子不包含湍流脉动、扩散、浮力或烟雾物理，不能称作真实烟雾实验。
- `interactive_viz.py` 调用 `export_streamline_data.py` 从 ParaView 获取实际 `U`、
  `IntegrationTime` 和有限近车身 YZ 播种面，车身仅做有界 VTK 抽稀以适配浏览器；
  Plotly 使用轨道相机、输运时间滑块和物理速度色标（同样采用 Viridis/Cividis 回退与 log10 规则）。HTML 是冻结稳态 RANS 的
  无质量示踪展示，不与 P7 等未对齐视觉模型混用。

## 编排

六个阶段为顺序 asyncio 协程调用（确定性、可离线测试）。曾经存在的
message_bus/state_machine 从未被编排层使用，v0.4.0 已删除；如需分布式
重试/恢复，按阶段边界引入即可，Agent 契约不变。
