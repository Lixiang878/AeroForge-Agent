# AeroForge-Agent 交接文档

> 写给接手的 AI / 工程师：本文档交代**已做工作、当前真实状态、已知坑、未完成事项**，
> 并列出**需要复核的疑点**与验证方法。请带着审查眼光阅读——前任（我）的方案
> 可能有误，欢迎推翻。
> 最后更新：2026-08-22（v0.3.0 诊断修订版）。

---

## 0. v0.3.0 重大修订（2026-08-22，接手者复核结果）

接手者对 v0.2.0 的 §5/§7 归因做了复核，**原归因被推翻**，要点：

1. **dat 列语义误读**：`coefficient.dat` 的 `Cd(f)/Cd(r)` 列**不是**摩擦/压差
   分解（实测各约为 Cd 之半）。真实分解在求解日志 forceCoeffs 块的
   Pressure/Viscous 列。重审后：**摩擦分量一直正常（Cd_viscous≈0.018），
   压差阻力 0.486 占 Cd 的 96%**。
2. **真主因 = 前缘曲率未解析**：R100 圆角仅 8 段离散 + 表面网格 ~33mm，
   圆角上仅 ~5 个单元；加速吸力峰无法形成，前表面近钝体滞止
   （Cp 均值 +0.62、全正压、无吸力区），前缘压差贡献 +0.42（正常 ~0.1）。
   `examples/surface_cp_zones.py` 可零成本复现该诊断。
3. **次因 = 边界层分辨率**：2 层相对厚度边界层 + 对数律壁面函数
   （实测 y+ 2.4–652 跨缓冲区）。Spalding 连续律壁面函数对照试验仅
   -4.5%（Cd 0.504→0.481），证明壁面函数**类型**不是主因。
4. 修复（v0.3.0 已固化）：STL 圆角 24 段、前缘加密盒 noseBox(level 5)、
   low-Re 壁面预设（15 层、首层按 y+≈1.2 估算 ~12μm、
   nutUSpalding/kLowRe）、max_global_cells 8M、并行 decomposeParDict 生成。

## 1. 项目目标与现状一句话

目标：把 AeroForge-Agent 从 dry-run 概念验证升级为**可真实求解的工程级 CFD
多 Agent 系统**，并用 Ahmed body 基准做端到端验证。

现状：**真实求解链路已完全打通**（WSL OpenFOAM v2412，网格→求解→力系数→报告→
ParaView 动画全自动化）；v0.2.0 的 Cd 偏差根因已修正（见 §0），v0.3.0 修复后
的验证数值见 `docs/VALIDATION.md` 第 9-11 轮记录。

---

## 2. 运行环境（本机特有，换机需重配）

| 项 | 值 / 说明 |
|---|---|
| Python | `E:\Anaconda\python.exe`。PATH 里的 `python` 是 MS Store 桩，**不可用** |
| OpenFOAM | WSL 内 v2412：`/usr/lib/openfoam/openfoam2412`，`RuntimeBridge` 自动探测（60s 超时+重试+缓存，冷启动慢） |
| ParaView | `D:\ParaView\bin\pvpython.exe`（RTX 5060 Laptop 离屏渲染） |
| git push | 直连 github 不通，必须 `-c http.proxy=http://127.0.0.1:7890 -c https.proxy=http://127.0.0.1:7890` |
| git 身份 | 逐仓 `-c user.name/user.email`（aeroforge 用 `Lixiang878 <Lixiang878@users.noreply.github.com>`） |
| 计算产物 | `workspace/task_<hash>/`（.gitignore 排除，不进 GitHub） |

---

## 3. 架构与文件地图

```
src/aeroforge/
├── core/runtime_bridge.py   三态运行时（native/WSL/不可用）；WSL 内重定向日志
├── core/models.py           Pydantic 契约（Task/Geometry/Mesh/Sim/FinalReport）
├── tools/case_builder.py    从零生成 OpenFOAM case（steady/transient 双模式）
├── tools/stl_tools.py       Ahmed body 参数化 STL（圆角 R100/R50）+ 水密/外法向检查
├── tools/openfoam_tools.py  求解序列 + 残差/forceCoeffs/checkMesh 解析
├── tools/validation.py      Cd 对比判据（20°→0.197 / 25°→0.285，±10%）
└── agents/*                 六阶段顺序编排（需求→几何→物理→网格→求解→分析）
examples/
├── verify_ahmed.py          端到端稳态验证（--slant 20/25）
├── animate_ahmed.py         瞬态 pimpleFoam 动画算例（复用稳态网格+初场）
├── resume_transient.py      中断续算（startFrom latestTime）
└── paraview/
    ├── windtunnel_view.py   风洞视角截图（隐藏外壁/烟线/光片/车体/机位）
    ├── render_animation.py  离屏渲染动画序列帧
    └── save_state.py        生成带流线的 .pvsm 状态文件
docs/VALIDATION.md           八轮稳态实验档案（数据+归因+路线）
```

Agent 编排目前是**顺序调用**；`core/message_bus.py`、`state_machine.py` 存在但
未被六阶段深度使用（历史遗留的"多 Agent"叙事），是否重构见 §7。

---

## 4. 已完成工作清单（commit 序）

| commit | 内容 |
|---|---|
| `5a1cd91` | 修复 ESI snappyHexMesh 尾流加密盒语法（内联 searchableBox 被静默忽略）；风洞设置（大域/滑移地面/低湍流入口）；八轮验证档案 |
| `abd1308` | v0.2.0：真实求解链路（RuntimeBridge/CaseBuilder/stl_tools/validation）+ 26→28 离线测试 |
| `b079dde` | 瞬态 pimpleFoam 模式 + 每个 case 生成 `<case>.foam` ParaView 标记 |
| `cd6a512` | 风洞视角脚本 + 中断续算脚本 |
| `73f9f0b` | 离屏动画渲染器（40 帧 → GIF 已生成于 `case/results/ahmed_wake_animation.gif`） |
| `99b935e` | 流线视角 .pvsm 状态文件生成器 |

同期 portfolio 级变更（其他仓库）：Berth-Scheduler 已并入 SmartPort-MultiAgent
（HiGHS 精确解/Imai 基准/灵敏度），Berth 仓加归档横幅；Profile README 同步。

---

## 5. 验证实验数据（全部真实求解输出，可复算）

稳态八轮（simpleFoam, k-ω SST, 壁面函数）：

| # | 设置 | 角 | 单元 | Cd | 参考 | 偏差 |
|---|---|---|---|---|---|---|
| 1 | 尖角前缘 | 25° | 418k | 1.056 | 0.285 | +271% |
| 2 | +圆角 R100/R50 | 25° | 417k | 0.582 | 0.285 | +104% |
| 3 | +表面 level3 | 25° | 785k | 0.559 | 0.285 | +96% |
| 4 | 改 20° | 20° | 787k | 0.547 | 0.197 | +178% |
| 5 | +阻塞比 4%+低湍流 | 20° | 674k | 0.493 | 0.197 | +150% |
| 6 | +上游滑移地面 | 20° | 676k | 0.491 | 0.197 | +149% |
| 7 | +nut/nu=5 | 20° | 676k | 0.487 | 0.197 | +147% |
| 8 | +wakeBox 生效 | 20° | 1151k | 0.491 | 0.197 | +149% |

瞬态一轮（pimpleFoam, 从稳态场起算, Co≤2, 527 步, 0→0.0783 s, 40 帧）：
**尾段平均 Cd = 0.522, Cl = 0.262**。

关键推论：瞬态均值与稳态同量级 → **稳态假设不是偏差主因**；设置级修正
（#2→#8）边际收益递减 → 偏差更可能来自**模型形态或几何本身**。

---

## 6. 已踩过的坑（都已解决，别再踩）

1. **wsl.exe 重定向输出是 UTF-16** → 日志必须在 WSL 内 bash 重定向
   （`cmd > log 2>&1`），capture 类调用加 `encoding='utf-8', errors='replace'`。
2. **ESI snappyHexMesh 的 refinementRegions 内联几何被静默忽略**（日志
   "entries were not used"）→ searchableBox 必须定义在 `geometry` 节再按名引用。
3. **symmetryPlane 必须共面**：一个 patch 合并两个平行平面会让 blockMesh 直接退出。
4. **forceCoeffs 输出 13 列**（Time Cd Cd_f Cd_r Cl Cl_f Cl_r Cm + 力/矩分量），
   注释头不含列名；解析器按列数判定 + `Cd=Cd_f+Cd_r` 交叉验证。
5. **ParaView 新版 API 坑**：`view.ActiveCamera` 不存在、`active_camera` 是方法、
   `GetActiveCamera()` 才返回可用 Set* 的相机；Clip 用 `Invert`（InsideOut 废弃）；
   OpenFOAM reader **只选 patch 的 MeshRegions 返回空** → 全读后用几何裁剪或直读 STL。
6. PowerShell 5.1 读写文件默认 GBK，会毁掉 UTF-8 中文 → 一律用 Python 或显式 UTF8。
7. `python` 命令是 MS Store 桩 → 用 `E:\Anaconda\python.exe` 全路径。

---

## 7. 接手审查指南（我认为可能不对 / 可以更好的地方）

**A. Cd 偏差归因（最高优先）**。我的归因链：圆角必要（1.056→0.58 证实）→
其余设置级修正无效 → 归因模型形态+无支腿。**请复核**：
1. 画 y+ 分布与基座压力系数 Cp_base，对照文献（Ahmed 25° 基座 Cp≈-0.4 量级）；
   若基座吸力过强，问题可能在尾流/基座分辨率而非湍流模型。
2. 做**网格收敛研究**（3 套网格，GCI）——我只做了单点加密对比，不构成收敛证据。
3. 换**标准 Ahmed STL**（带支腿的公开模型）重跑，隔离几何简化因素。
4. 20° 应是附着流：检查斜面是否有数值分离（ streamline 贴附情况）；若有人为
   分离，先修分离再谈精度。
5. 尝试 k-ω SST **low-Re（y+≈1）** 网格（需 300–500 万单元，本机串行约数小时/轮，
   可接受后台跑）或 IDDES；这是达到 ±10% 最可能的路径。

**B. 验证方法论**。±10% 判据是我自设的；20° 实验值 0.197 与 25° 0.285 均来自
Ahmed 1984，注意不同文献取值略有差异。瞬态只跑了 0.078 s（≈3 对流时间），
统计平均不充分，若走瞬态路线需加长采样。

**C. 代码架构**。六阶段是顺序函数调用套了 Agent 壳；message_bus/state_machine
未实质使用。若要走"真多 Agent"叙事，应让阶段间走总线并加状态机驱动的重试/
回退（例如网格质量不过自动降级别重跑）。

**D. ParaView 脚本**。我靠 try/except 双名兼容糊过了版本差异；更干净的做法是
检测 ParaView 版本后分支，或改用 trame/官方 state 模板。

**E. 性能**。WSL 串行求解是瓶颈；可开 `decomposePar` 并行（WSL 核数充足），
bridge 里加 `mpirun -np N` 路径即可，我未做。

---

## 8. 快速复现命令

```powershell
cd e:\GitHub项目\aeroforge-agent
E:\Anaconda\python.exe -m pytest tests -q                 # 28 离线测试
E:\Anaconda\python.exe examples/verify_ahmed.py --slant 20   # 稳态验证（~35min）
E:\Anaconda\python.exe examples/animate_ahmed.py             # 瞬态动画算例（~1.5h）
E:\Anaconda\python.exe examples/resume_transient.py          # 续算
D:\ParaView\bin\pvpython.exe examples/paraview/render_animation.py  # 动画帧
D:\ParaView\bin\pvpython.exe examples/paraview/save_state.py        # 流线 .pvsm
# 推送：git -c http.proxy=http://127.0.0.1:7890 -c https.proxy=http://127.0.0.1:7890 push origin main
```

现成产物：`workspace/task_6d95b6d1/case/results/` 下
`ahmed_wake_animation.gif`（40 帧动画）、`windtunnel_view.png`（静帧）、
`windtunnel_streamlines.pvsm`（流线状态）、`verification_report.md`。

---

## 9. 给接手者的一句话

链路是通的、数据是真的、报告是诚实的；**精度还没达标，而且我的归因只是假设**。
请先做 §7-A 的复核实验，再决定把算力投给网格、湍流模型还是几何。祝顺利。
