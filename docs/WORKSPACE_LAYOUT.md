# 工作区布局与清理约定

`workspace/` 是本项目的 E 盘本地工作区，已由 `.gitignore` 整体排除，不把大体积网格、求解场、帧序列和下载资产提交到仓库。仓库中的 `docs/img/`、`docs/media/` 才是对外展示交付物。

## 当前保留内容

| 路径 | 用途 | 保留级别 |
|---|---|---|
| `workspace/drivaerml_showcase2/task_28d67b31_refined/` | DrivAerML run_1/refined 求解场、静帧、流线 JSON 与 manifest | 当前展示算例 |
| `workspace/drivaerml_run_2/task_5e31083c/` | DrivAerML run_2 的 800 次 simpleFoam 求解场、静帧、流线 JSON 与 manifest | 当前展示算例 |
| `workspace/external_models/drivaerml_run_1/` | run_1 原始 STL、预处理 STL 与来源记录 | CFD 几何源 |
| `workspace/external_models/drivaerml_run_2/` | run_2 原始 STL、质量门禁与来源记录 | CFD 几何源 |
| `workspace/external_models/drivaernet_official_upstream/` | DrivAerNet++ 官方仓库浅克隆 | 源码/元数据源 |
| `workspace/external_models/xpeng_p7_candidate/` | 用户提供的 P7 下载原件、材质展示资产和明确标记为 `cfd_ready=false` 的候选外壳 | 视觉候选，不可冒充 CFD 壁面 |
| `workspace/diag_case5/`、`workspace/audit_*`、旧 run 目录 | 历史审计、失败门禁和对照算例 | 证据保留 |

## 清理规则

1. `docs/` 中已有 SHA-256 相同的 HTML/GIF/MP4 时，workspace 只保留流线 JSON、manifest 和求解场；渲染帧、编码视频和自包含 HTML 视为中间副本，移入回收站。
2. 失败网格只保留 `report.md`、`log.*`、字典和可复核配置；不保留不能进入求解器的 `polyMesh`、特征边和重复 STL。
3. `__pycache__/`、`.pytest_cache/`、`*.pyc` 和 `workspace/_scratch/*` 均为可再生缓存，测试或渲染结束后清理；`workspace/_scratch/` 父目录保留以满足 `pytest.ini` 的 `--basetemp`。
4. 下载、渲染和测试临时目录统一放在 E 盘；不在 C 盘创建项目专用缓存。删除动作优先发送到 Windows 回收站，避免误删原始资产。

## 重新生成展示媒体

从保留的 `streamline_data.json` 和求解场重新运行项目脚本即可生成 `docs/img/`、`docs/media/` 交付物；不要把旧帧序列重新复制回 workspace。具体模型来源、许可证和质量门禁见 [`REAL_VEHICLE_MODEL.md`](REAL_VEHICLE_MODEL.md) 与 [`VEHICLE_ASSET_POLICY.md`](VEHICLE_ASSET_POLICY.md)。
