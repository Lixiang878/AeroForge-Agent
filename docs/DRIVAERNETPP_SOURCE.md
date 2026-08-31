# DrivAerNet++ 官方数据源接入

更新日期：2026-08-31

## 已核验的官方来源

本项目将 [MIT DeCoDE Lab 的 DrivAerNet 官方仓库](https://github.com/Mohamedelrefaie/DrivAerNet)
作为 DrivAerNet++ 的代码、参数表和设计划分来源。当前已在 E 盘保留浅克隆：

```text
workspace/external_models/drivaernet_official_upstream/
```

本地审查记录：

| 项目 | 结果 |
|---|---|
| 仓库 commit | `8b8c053053aa0f27c30f73af00be070a20205858` |
| README 声明的设计数 | 8,150 |
| Croissant 元数据声明的设计数 | 8,000 |
| 参数表行数 | 4,165 |
| train / val / test 划分 | 5,819 / 1,148 / 1,154 个 ID |
| 数据集许可 | CC BY-NC 4.0，仅限非商业研究/教育 |
| GitHub clone 是否包含完整 STL | 否 |

README 与 Croissant 元数据的设计总数目前分别为 8,150 和 8,000，本地参数表行数与
split ID 数也不一致；流程把它们记录为审查元数据，不能由其中任一数字推断某个 STL
已经下载或可计算。
原生 STL 和完整 CFD 数据通过 [Harvard Dataverse/Globus 数据集](https://dataverse.harvard.edu/dataset.xhtml?persistentId=doi:10.7910/DVN/OYU2FG)
单独分发；本项目没有尝试下载数百 GB 的压缩包，更没有把它们放到 C 盘。

## 选一个设计再导入

只把用户明确选择的一个设计子集下载到 E 盘，例如：

```powershell
$repo = "workspace/external_models/drivaernet_official_upstream"
$meshRoot = "workspace/external_models/drivaernetpp_selected/meshes"
$env:PYTHONPATH = "src"
E:\Anaconda\python.exe -c `
  "from aeroforge.tools.drivaernet_adapter import inspect_drivaernet_repo; import json; print(json.dumps(inspect_drivaernet_repo(r'$repo'), ensure_ascii=False, indent=2))"
```

下载后，必须先按设计 ID 精确发现并验证原生 STL；不会从 OBJ/GLB 或体素壳体推断 CFD
外壳：

```powershell
$env:PYTHONPATH = "src"
E:\Anaconda\python.exe -c `
  "from aeroforge.tools.drivaernet_adapter import discover_native_stl, validate_native_stl; p=discover_native_stl(r'$meshRoot', 'E_S_WWC_WM_005'); print(p); print(validate_native_stl(p))"
```

质量门禁通过后，可直接运行单设计流程（默认 `showcase` 为 800 次稳态迭代；`smoke`
仍为 160 次）：

```powershell
python examples/run_drivaernetpp.py `
  --dataset-dir workspace/external_models/drivaernetpp_selected/meshes `
  --design-id E_S_WWC_WM_005 `
  --profile showcase
```

质量门禁要求有限坐标、非退化三角面、单连通分量和水密表面；失败时返回
`cfd_ready=false`，不会自动修复后继续求解。通过门禁的 STL 才能交给
`snappyHexMesh`，并且仍需重新确认尺度、车头方向、地面间隙、三套网格、y+ 和收敛。

## 与小鹏 P7 的关系

DrivAerNet++ 是参数化研究车辆，不是大众、奥迪、宝马、小鹏、理想或问界的量产车型。
它可以替代当前粗糙 P7 候选作为**可追溯 CFD 基准车**，但不能在论文或报告中写成某个
品牌车型。P7 的高细节 OBJ/GLB 继续用于外观展示；当前 `p7_cfd_candidate.stl`
明确标记为体素近似、`cfd_ready=false`。若必须计算 P7，应从有权使用的 CAD/外壳 STL
重新导出，而不是继续平滑这个候选文件。
