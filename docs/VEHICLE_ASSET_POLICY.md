# 具体车型三维资产接入与许可边界

更新日期：2026-08-31

## 结论

截至本次检索，没有发现上述品牌由厂商官方公开发布、许可明确且可直接用于本流程的
量产整车 CFD 几何。已找到第三方作者以 CC BY 4.0 发布的 **2022 XPeng P7**，用户
已在登录会话中下载并完成本地审查；它不是厂商 CAD，当前 OBJ 含非有限坐标且不水密，
仍不能直接作为 CFD 外壳。具体车型的“可下载”和“可计算”仍是两道独立门禁。

因此仓库不自动抓取品牌模型，也不保存来源不明的 STL。具体车型任务必须同时
提供本地模型和资产清单；缺少模型、许可证或 SHA-256 不一致时，在网格前停止，
不得退化为简化方块车。

补充检索了公开研究数据：官方 [DrivAerNet++ 仓库](https://github.com/roharon/drivaernet)
提供大量参数化 STL 与 CFD 数据，但许可是 CC BY-NC 4.0，且不是大众/奥迪/宝马/小鹏等
量产车型；它适合作为研究基准，不应被描述成品牌车替代品。

## 下载格式怎么选

格式决定的是材质/场景封装方式，不决定网格是否能计算。当前建议按用途选择：

| 格式 | 适合用途 | 当前门禁结论 |
|---|---|---|
| **GLB** | 单文件浏览器/ParaView 外观展示，材质和纹理可内嵌 | 首选视觉交付；仍需另导出并修复 CFD 外壳 |
| **GLTF** | 与 GLB 相同，但纹理可能是外部文件 | 可用于展示；下载时必须把 `.bin` 与纹理目录一起留存 |
| **OBJ+MTL** | 最适合保留原始来源、材质组和可审计文本 | 适合源文件审查；经常分件、开口或带非法坐标，不能直接求解 |
| **USDZ** | Apple AR/移动端封装 | 不作为本流程的求解输入；需回到原始网格再转换 |

对小鹏 P7，当前 ZIP 只有 OBJ/MTL，因此保留 OBJ 作为来源审计，并生成带嵌入
材质/纹理的 `p7_visual_sanitized.glb` 作为展示文件。真正计算仍需要从有权使用的
源文件导出**外部车身 CFD STL/STEP**，删除内饰/玻璃等非外流场部件、确认米制和
`-X/+Z` 轴向、修复封闭后通过 `surfaceCheck`。不能把“能在网页里显示”当成“可用于
snappyHexMesh”。

为了继续使用 P7 进行后续几何实验，当前还保留了一个单独的
`p7_cfd_candidate.stl`：它由视觉 GLB 经体素填充和 Marching Cubes 近似重建，已形成
单一水密表面，但不等同原始车身 CAD，且单位/轴向与外流场部件仍未确认。该文件及
`p7_cfd_candidate_manifest.json` 只作为待审候选，固定标记 `cfd_ready=false`，不能
绕过工程门禁，也不能与 DrivAerML 风场混用。

## 已核对的代表性来源

| 品牌/车型 | 代表性来源 | 当前处理结论 |
|---|---|---|
| 大众 ID.4 2021 | [CGTrader](https://www.cgtrader.com/3d-models/car/suv/volkswagen-id4-2021-e81351cd-55f6-4cfd-a3b0-088257ef8767) | 用户自行购买/下载；禁止把源模型放入公共仓库；未证明 CFD 水密。 |
| 奥迪 A6 Sedan 2019 | [CGTrader](https://www.cgtrader.com/3d-models/car/luxury-car/audi-a6-sedan-2019) | 用户自行购买/下载；页面给出毫米单位，但仍需外壳清理和封闭修复。 |
| 宝马 M4 Competition | [原 Sketchfab 页面](https://sketchfab.com/3d-models/bmw-m4-competition-m-package-5c0a2dafb1ad408d9fc9eeef9aee531b) | 2026-08-31 原页面返回 deleted 状态、模型 API 404；第三方 GitHub 署名不能代替已删除的上游核验。本轮未下载。 |
| 小鹏 P7 2022 | [作者 Sketchfab 页面](https://sketchfab.com/3d-models/2022-xpeng-p7-e787dac0c6f84be7b39362fca9dc93da) / [模型 API](https://api.sketchfab.com/v3/models/e787dac0c6f84be7b39362fca9dc93da) | 用户已下载 ZIP 并在 E 盘留存任务副本；原 OBJ/MTL+54 纹理含 `-nan(ind)` 且非水密（165,713 条边界边）。另有体素重建的 `p7_cfd_candidate.stl`（162,936 面、单连通、水密），但为近似候选，仍标记 `cfd_ready=false`，不能直接 CFD。 |
| 理想 L9 | [CGTrader](https://www.cgtrader.com/3d-models/car/suv/li-l9) | 用户自行购买/下载；页面给出外形尺寸，但未声明水密且禁止源文件再分发。 |
| 问界 M5 | [CGTrader](https://www.cgtrader.com/3d-models/car/car/aito-m5) | 用户自行购买/下载；渲染网格，不是经验证的工程 CAD。 |

CGTrader 的 [Royalty Free License](https://help.cgtrader.com/hc/en-us/articles/360015124437-Royalty-Free-License)
允许把模型用于不可单独提取的集成产品和渲染图/动态图，但明确禁止把下载得到的
源模型单独出售、赠送或重新分发。平台模型的许可证并不自动证明上传者拥有品牌
外观、商标或原始 CAD 的完整权利链。

CC BY 4.0 要求作者署名、许可链接及修改说明。P7 的公开许可与当前 API 状态支持
将它作为本地研究候选；仍需检查下载包来源说明，不得冒称官方 CAD 或品牌认可。
当前只在项目 E 盘任务目录留存用户提供的源副本，不把该源文件提交到公共仓库。

## 推荐的双几何流程

1. `CFD surface`：封闭、去内饰、单位为米、车头朝 `-X`、竖直方向 `+Z` 的 STL；
   只用于 snappyHexMesh/OpenFOAM。
2. `visual asset`：用户有权使用的 OBJ/GLB，可保留玻璃、轮胎和纹理；只用于展示。
3. 两套几何必须记录同一坐标变换和对齐误差。当前版本先支持 CFD STL 的统一车漆；
   多材质 GLB/OBJ 对齐属于后续阶段。

STL 本身通常不保存可靠的 PBR 材质或纹理。本轮新增的 `--vehicle-color #RRGGBB`
是在 ParaView 渲染阶段应用统一车漆，不会改变 CFD 表面或求解结果。

## 资产清单

参考 [`vehicle_model_manifest.example.json`](vehicle_model_manifest.example.json)。具体车型运行时：

```powershell
aeroforge "宝马 X3 外流场 30 m/s" `
  --upload-stl D:\models\bmw_x3_closed.stl `
  --model-manifest D:\models\bmw_x3_manifest.json `
  --vehicle-color "#1A80E6" `
  --animation
```

清单必须记录模型标识、品牌/车型/年款、来源、源文件 SHA-256、许可证、单位、
坐标轴、是否允许修改/再分发和 CFD-ready 状态。公开发布前还应保留作者署名、
修改说明，以及“与品牌方无隶属或认可关系”的声明。
导入器核对请求车型与清单品牌/型号一致，但清单中的授权声明不是自动法律核验，
`cfd_ready` 也不是对实际网格质量的证明。

当前导入器支持 `m/cm/mm` 并按清单自动换算到米；如果同时显式给出
`--upload-scale`，数值必须与清单单位一致。当前只接收车头 `-X`、车顶 `+Z` 的
外壳，其他轴向必须先在建模软件中转换，且许可证必须允许转换/派生处理。
这里 `forward_axis` 指车辆鼻端方向：车头在上游 `x_min`，自由流从上游沿 `+X`
吹向车尾。清单只记录声明，导入后仍须通过几何截图确认实际鼻端，不能仅凭字符串
判定迎风朝向正确。

## CFD 接入门禁

- 文件必须存在、数值有限、无退化三角形并形成水密闭合外壳。
- 单位、轴向、离地间隙和尺度必须与清单一致。
- 内饰、座椅、发动机、不可见重叠面和零厚度装饰件不能直接进入外流场网格。
- 漂亮的展示网格不能替代三套网格、y+、统计收敛和参考数据对照。
- 所有输出统一称为“数值风洞/CFD 风场”，不得称为真实风洞实验数据。
