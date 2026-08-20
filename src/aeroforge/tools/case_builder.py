"""CaseBuilder：从零生成 OpenFOAM case 目录（不克隆 tutorial）。

生成内容：
- constant/triSurface/<surface>.stl     几何表面（供 snappyHexMesh）
- 0/{U,p,k,omega,nut}                   边界条件（正则匹配壁面 patch 组）
- constant/{transportProperties,turbulenceProperties}
- system/{controlDict,fvSchemes,fvSolution,blockMeshDict,
          surfaceFeatureExtractDict,snappyHexMeshDict}

约定：x 为来流方向、y 展向、z 垂向，地面为 z=0 的 `ground` patch。
湍流模型：RANS k-omega SST（外气动工程流程的标准选择）。
注意：symmetryPlane 要求 patch 共面，故侧壁拆为 sideLow/sideHigh 两个 patch。
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from ..core.models import BoundingBox

__all__ = ["CaseSpec", "build_case", "domain_from_bbox"]

# 风洞域相对物体尺寸的外扩倍数（上游/下游/侧向单边/顶部）；
# 取值保证横截面阻塞比 ≈ 4%（汽车风洞工程惯例 <5%）
DEFAULT_MARGINS = (3.0, 7.0, 2.5, 5.0)


@dataclass
class CaseSpec:
    """一个算例的完整输入契约。"""

    stl_path: Path
    surface: str = "body"
    bbox: BoundingBox | None = None
    velocity: float = 20.0                     # m/s，来流速度
    density: float = 1.225                     # kg/m3（forceCoeffs rhoInf 用）
    nu: float = 1.5e-5                         # m2/s
    turbulence_intensity: float = 0.005        # 入口湍流强度 I（风洞低湍流惯例）
    turbulence_viscosity_ratio: float = 5.0    # 远场 nut/nu（外气动低湍流风洞惯例 1–10）
    n_iterations: int = 600                    # simpleFoam 稳态迭代数
    base_cell_size: float | None = None        # 背景网格尺寸；None 时取 L/base_cells_per_L
    base_cells_per_L: int = 22                 # 特征长度方向背景网格分数
    surface_refine_level: int = 2              # snappy 表面细化级数
    n_cells_between_levels: int = 2
    max_global_cells: int = 3_000_000
    moving_ground: bool = True                 # 地面随来流移动（地面效应更真实）
    upstream_slip_ground: bool = True          # 上游地面滑移（抑制地面边界层堵死离地间隙）
    slip_ground_offset_L: float = 0.75         # 滑移地面在体前 0.75L 处转为移动地面
    wake_refinement: bool = True               # 尾流区局部加密（斜面涡/基座压力关键）
    wake_refine_level: int = 2               # 尾流加密盒的细化级数
    margins: tuple[float, float, float, float] = DEFAULT_MARGINS

    @property
    def characteristic_length(self) -> float:
        b = self.bbox
        if b is None:
            raise ValueError("bbox not set; call build_case or set bbox first")
        return max(b.x_max - b.x_min, b.y_max - b.y_min, b.z_max - b.z_min)


def domain_from_bbox(bbox: BoundingBox, margins: tuple[float, float, float, float],
                     ) -> dict:
    """由物体包围盒计算风洞域角点。"""
    L = bbox.x_max - bbox.x_min
    W = bbox.y_max - bbox.y_min
    H = bbox.z_max - bbox.z_min
    up, down, side, top = margins
    return {
        "x_min": bbox.x_min - up * L, "x_max": bbox.x_max + down * L,
        "y_min": bbox.y_min - side * W, "y_max": bbox.y_max + side * W,
        "z_min": 0.0, "z_max": max(bbox.z_max * top, H * top),
        "L": L, "W": W, "H": H,
    }


def build_case(case_dir: str | Path, spec: CaseSpec) -> Path:
    """生成完整 case 目录，返回 case 根路径。"""
    case = Path(case_dir)
    if spec.bbox is None:
        raise ValueError("spec.bbox is required")
    dom = domain_from_bbox(spec.bbox, spec.margins)
    base = spec.base_cell_size or dom["L"] / spec.base_cells_per_L

    for sub in ("0", "constant/triSurface", "system"):
        (case / sub).mkdir(parents=True, exist_ok=True)

    shutil.copy2(spec.stl_path, case / "constant" / "triSurface" / f"{spec.surface}.stl")

    (case / "0" / "U").write_text(_field_u(spec), encoding="utf-8")
    (case / "0" / "p").write_text(_field_p(spec.surface), encoding="utf-8")
    k_inf, omega_inf = _turbulence_inlet(spec)
    (case / "0" / "k").write_text(_field_scalar("k", k_inf, spec.surface), encoding="utf-8")
    (case / "0" / "omega").write_text(_field_scalar("omega", omega_inf, spec.surface), encoding="utf-8")
    (case / "0" / "nut").write_text(_field_nut(spec.surface), encoding="utf-8")

    (case / "constant" / "transportProperties").write_text(
        _transport_properties(spec), encoding="utf-8")
    (case / "constant" / "turbulenceProperties").write_text(
        _turbulence_properties(), encoding="utf-8")

    (case / "system" / "controlDict").write_text(_control_dict(spec, dom), encoding="utf-8")
    (case / "system" / "fvSchemes").write_text(_fv_schemes(), encoding="utf-8")
    (case / "system" / "fvSolution").write_text(_fv_solution(), encoding="utf-8")
    (case / "system" / "blockMeshDict").write_text(_block_mesh_dict(dom, base, spec), encoding="utf-8")
    (case / "system" / "surfaceFeatureExtractDict").write_text(
        _surface_feature_dict(spec), encoding="utf-8")
    (case / "system" / "snappyHexMeshDict").write_text(
        _snappy_dict(spec, dom), encoding="utf-8")
    return case


# ---------------------------------------------------------------- 内部工具
def _turbulence_inlet(spec: CaseSpec) -> tuple[float, float]:
    """入口 k/omega：由湍流强度 I 与远场粘度比 nut/nu 定义。

    外气动低湍流风洞惯例：I≈0.5%，nut/nu≈1–10（避免远场涡粘过大
    导致人为的边界层增厚与提前分离）。
    """
    I = spec.turbulence_intensity
    U = spec.velocity
    k = 1.5 * (I * U) ** 2
    omega = k / (spec.turbulence_viscosity_ratio * spec.nu)
    return k, omega


def _field_u(spec: CaseSpec) -> str:
    ground_bc = ("movingWallVelocity;\n        value           uniform (%g 0 0)"
                 % spec.velocity) if spec.moving_ground else "noSlip"
    upstream_ground = ("symmetryPlane" if spec.upstream_slip_ground
                       else ground_bc)
    return f"""/* AeroForge-Agent 自动生成 */
FoamFile
{{
    version     2.0;
    format      ascii;
    class       volVectorField;
    object      U;
}}

dimensions      [0 1 -1 0 0 0 0];

internalField   uniform ({spec.velocity} 0 0);

boundaryField
{{
    inlet
    {{
        type            fixedValue;
        value           uniform ({spec.velocity} 0 0);
    }}
    outlet
    {{
        type            inletOutlet;
        inletValue      uniform (0 0 0);
        value           uniform ({spec.velocity} 0 0);
    }}
    "(top|sideLow|sideHigh)"
    {{
        type            symmetryPlane;
    }}
    groundUpstream
    {{
        type            {upstream_ground};
    }}
    ground
    {{
        type            {ground_bc};
    }}
    {spec.surface}
    {{
        type            noSlip;
    }}
}}
"""


def _field_p(surface: str) -> str:
    return f"""/* AeroForge-Agent 自动生成 */
FoamFile
{{
    version     2.0;
    format      ascii;
    class       volScalarField;
    object      p;
}}

dimensions      [0 2 -2 0 0 0 0];

internalField   uniform 0;

boundaryField
{{
    inlet
    {{
        type            zeroGradient;
    }}
    outlet
    {{
        type            fixedValue;
        value           uniform 0;
    }}
    "(top|sideLow|sideHigh|groundUpstream)"
    {{
        type            symmetryPlane;
    }}
    "(ground|{surface})"
    {{
        type            zeroGradient;
    }}
}}
"""


def _field_scalar(name: str, value: float, surface: str) -> str:
    # k: 湍动能 m2/s2 -> [0 2 -2]；omega: 比耗散率 1/s -> [0 0 -1]
    dims = "[0 2 -2 0 0 0 0]" if name == "k" else "[0 0 -1 0 0 0 0]"
    return f"""/* AeroForge-Agent 自动生成 */
FoamFile
{{
    version     2.0;
    format      ascii;
    class       volScalarField;
    object      {name};
}}

dimensions      {dims};

internalField   uniform {value:g};

boundaryField
{{
    inlet
    {{
        type            fixedValue;
        value           uniform {value:g};
    }}
    outlet
    {{
        type            inletOutlet;
        inletValue      uniform {value:g};
        value           uniform {value:g};
    }}
    "(top|sideLow|sideHigh|groundUpstream)"
    {{
        type            symmetryPlane;
    }}
    "(ground|{surface})"
    {{
        type            {"kqRWallFunction" if name == "k" else "omegaWallFunction"};
        value           uniform {value:g};
    }}
}}
"""


def _field_nut(surface: str) -> str:
    return f"""/* AeroForge-Agent 自动生成 */
FoamFile
{{
    version     2.0;
    format      ascii;
    class       volScalarField;
    object      nut;
}}

dimensions      [0 2 -1 0 0 0 0];

internalField   uniform 0;

boundaryField
{{
    inlet
    {{
        type            calculated;
        value           uniform 0;
    }}
    outlet
    {{
        type            calculated;
        value           uniform 0;
    }}
    "(top|sideLow|sideHigh|groundUpstream)"
    {{
        type            symmetryPlane;
    }}
    "(ground|{surface})"
    {{
        type            nutkWallFunction;
        value           uniform 0;
    }}
}}
"""


def _transport_properties(spec: CaseSpec) -> str:
    return f"""/* AeroForge-Agent 自动生成 */
FoamFile
{{
    version     2.0;
    format      ascii;
    class       dictionary;
    object      transportProperties;
}}

transportModel  Newtonian;

nu              {spec.nu:g};
"""


def _turbulence_properties() -> str:
    return """/* AeroForge-Agent 自动生成 */
FoamFile
{
    version     2.0;
    format      ascii;
    class       dictionary;
    object      turbulenceProperties;
}

simulationType  RAS;

RAS
{
    model           kOmegaSST;
    turbulence      on;
    printCoeffs     on;
}
"""


def _control_dict(spec: CaseSpec, dom: dict) -> str:
    L = dom["L"]
    front_area = ((spec.bbox.y_max - spec.bbox.y_min)
                  * (spec.bbox.z_max - spec.bbox.z_min))
    write_interval = max(50, spec.n_iterations // 10)
    return f"""/* AeroForge-Agent 自动生成 */
FoamFile
{{
    version     2.0;
    format      ascii;
    class       dictionary;
    object      controlDict;
}}

application     simpleFoam;

startFrom       latestTime;
startTime       0;
stopAt          endTime;
endTime         {spec.n_iterations};
deltaT          1;

writeControl    timeStep;
writeInterval   {write_interval};
purgeWrite      2;
writeFormat     ascii;
writePrecision  6;
timeFormat      general;
timePrecision   6;

runTimeModifiable false;

functions
{{
    forceCoeffs1
    {{
        type            forceCoeffs;
        libs            ("libforces.so");
        writeControl    timeStep;
        writeInterval   10;

        patches         ({spec.surface});
        rho             rhoInf;
        rhoInf          {spec.density:g};
        liftDir         (0 0 1);
        dragDir         (1 0 0);
        CofR            (0 0 0);
        pitchAxis       (0 1 0);
        magUInf         {spec.velocity:g};
        lRef            {L:g};
        Aref            {front_area:g};
    }}
}}
"""


def _fv_schemes() -> str:
    return """/* AeroForge-Agent 自动生成 */
FoamFile
{
    version     2.0;
    format      ascii;
    class       dictionary;
    object      fvSchemes;
}

ddtSchemes
{
    default         steadyState;
}

gradSchemes
{
    default         Gauss linear;
}

divSchemes
{
    default         none;
    div(phi,U)      bounded Gauss linearUpwind grad(U);
    div(phi,k)      bounded Gauss upwind;
    div(phi,omega)  bounded Gauss upwind;
    div((nuEff*dev2(T(grad(U))))) Gauss linear;
}

laplacianSchemes
{
    default         Gauss linear corrected;
}

interpolationSchemes
{
    default         linear;
}

snGradSchemes
{
    default         corrected;
}

wallDist
{
    method          meshWave;
}
"""


def _fv_solution() -> str:
    return """/* AeroForge-Agent 自动生成 */
FoamFile
{
    version     2.0;
    format      ascii;
    class       dictionary;
    object      fvSolution;
}

solvers
{
    p
    {
        solver          GAMG;
        smoother        DICGaussSeidel;
        tolerance       1e-7;
        relTol          0.01;
    }
    "(U|k|omega)"
    {
        solver          smoothSolver;
        smoother        symGaussSeidel;
        tolerance       1e-8;
        relTol          0.1;
    }
}

SIMPLE
{
    nNonOrthogonalCorrectors 0;
    consistent      yes;
}

relaxationFactors
{
    equations
    {
        U               0.9;
        k               0.7;
        omega           0.7;
    }
}
"""


def _block_mesh_dict(dom: dict, base: float, spec: CaseSpec) -> str:
    ny = max(8, int(round((dom["y_max"] - dom["y_min"]) / base)))
    nz = max(8, int(round((dom["z_max"] - dom["z_min"]) / base)))

    use_split = spec.upstream_slip_ground and spec.bbox is not None
    if use_split:
        # 上游地面为滑移面（模拟风洞边界层吸除，避免地面边界层堵死
        # 离地间隙），在体前 slip_ground_offset_L 处转为移动地面。
        L = spec.bbox.x_max - spec.bbox.x_min
        xs = spec.bbox.x_min - spec.slip_ground_offset_L * L
        xs = max(dom["x_min"] + 4 * base, xs)
        nx1 = max(4, int(round((xs - dom["x_min"]) / base)))
        nx2 = max(8, int(round((dom["x_max"] - xs) / base)))
        return f"""/* AeroForge-Agent 自动生成 */
FoamFile
{{
    version     2.0;
    format      ascii;
    class       dictionary;
    object      blockMeshDict;
}}

scale   1;

vertices
(
    ({dom['x_min']:g} {dom['y_min']:g} 0)
    ({xs:g} {dom['y_min']:g} 0)
    ({dom['x_max']:g} {dom['y_min']:g} 0)
    ({dom['x_min']:g} {dom['y_max']:g} 0)
    ({xs:g} {dom['y_max']:g} 0)
    ({dom['x_max']:g} {dom['y_max']:g} 0)
    ({dom['x_min']:g} {dom['y_min']:g} {dom['z_max']:g})
    ({xs:g} {dom['y_min']:g} {dom['z_max']:g})
    ({dom['x_max']:g} {dom['y_min']:g} {dom['z_max']:g})
    ({dom['x_min']:g} {dom['y_max']:g} {dom['z_max']:g})
    ({xs:g} {dom['y_max']:g} {dom['z_max']:g})
    ({dom['x_max']:g} {dom['y_max']:g} {dom['z_max']:g})
);

blocks
(
    hex (0 1 4 3 6 7 10 9) ({nx1} {ny} {nz}) simpleGrading (1 1 1)
    hex (1 2 5 4 7 8 11 10) ({nx2} {ny} {nz}) simpleGrading (1 1 1)
);

edges
(
);

boundary
(
    inlet
    {{
        type patch;
        faces
        (
            (0 6 9 3)
        );
    }}
    outlet
    {{
        type patch;
        faces
        (
            (2 8 11 5)
        );
    }}
    groundUpstream
    {{
        type symmetryPlane;
        faces
        (
            (0 3 4 1)
        );
    }}
    ground
    {{
        type wall;
        faces
        (
            (1 4 5 2)
        );
    }}
    top
    {{
        type symmetryPlane;
        faces
        (
            (6 7 10 9)
            (7 8 11 10)
        );
    }}
    sideLow
    {{
        type symmetryPlane;
        faces
        (
            (0 1 7 6)
            (1 2 8 7)
        );
    }}
    sideHigh
    {{
        type symmetryPlane;
        faces
        (
            (3 4 10 9)
            (4 5 11 10)
        );
    }}
);

mergePatchPairs
(
);
"""

    nx = max(8, int(round((dom["x_max"] - dom["x_min"]) / base)))
    return f"""/* AeroForge-Agent 自动生成 */
FoamFile
{{
    version     2.0;
    format      ascii;
    class       dictionary;
    object      blockMeshDict;
}}

scale   1;

vertices
(
    ({dom['x_min']:g} {dom['y_min']:g} 0)
    ({dom['x_max']:g} {dom['y_min']:g} 0)
    ({dom['x_max']:g} {dom['y_max']:g} 0)
    ({dom['x_min']:g} {dom['y_max']:g} 0)
    ({dom['x_min']:g} {dom['y_min']:g} {dom['z_max']:g})
    ({dom['x_max']:g} {dom['y_min']:g} {dom['z_max']:g})
    ({dom['x_max']:g} {dom['y_max']:g} {dom['z_max']:g})
    ({dom['x_min']:g} {dom['y_max']:g} {dom['z_max']:g})
);

blocks
(
    hex (0 1 2 3 4 5 6 7) ({nx} {ny} {nz}) simpleGrading (1 1 1)
);

edges
(
);

boundary
(
    inlet
    {{
        type patch;
        faces
        (
            (0 4 7 3)
        );
    }}
    outlet
    {{
        type patch;
        faces
        (
            (2 6 5 1)
        );
    }}
    ground
    {{
        type wall;
        faces
        (
            (0 3 2 1)
        );
    }}
    top
    {{
        type symmetryPlane;
        faces
        (
            (4 5 6 7)
        );
    }}
    sideLow
    {{
        type symmetryPlane;
        faces
        (
            (1 5 4 0)
        );
    }}
    sideHigh
    {{
        type symmetryPlane;
        faces
        (
            (3 7 6 2)
        );
    }}
);

mergePatchPairs
(
);
"""


def _surface_feature_dict(spec: CaseSpec) -> str:
    return f"""/* AeroForge-Agent 自动生成 */
FoamFile
{{
    version     2.0;
    format      ascii;
    class       dictionary;
    object      surfaceFeatureExtractDict;
}}

{spec.surface}.stl
{{
    extractionMethod    extractFromSurface;

    includedAngle       150;

    subsetFeature       false;

    writeObj            yes;
}}
"""


def _wake_box(spec: CaseSpec, dom: dict) -> tuple[str, float, float, float, float, float, float] | None:
    """尾流加密盒参数：从斜面前缘延伸到下游 1.2L，覆盖斜面涡与基座回流区。"""
    if not spec.wake_refinement:
        return None
    b = spec.bbox
    L = b.x_max - b.x_min
    W = b.y_max - b.y_min
    H = b.z_max - b.z_min
    x0 = b.x_max - 0.4 * L
    x1 = min(b.x_max + 1.2 * L, dom["x_max"] - 0.2 * L)
    y0 = b.y_min - 0.8 * W
    y1 = b.y_max + 0.8 * W
    z1 = min(b.z_max + 0.6 * H, dom["z_max"] - 0.2 * H)
    return ("wakeBox", x0, y0, 0.0, x1, y1, z1)


def _snappy_dict(spec: CaseSpec, dom: dict) -> str:
    # locationInMesh：物体正上方域顶附近，保证在流体域内
    cx = (spec.bbox.x_min + spec.bbox.x_max) / 2.0
    lz = dom["z_max"] * 0.9
    level = spec.surface_refine_level
    wb = _wake_box(spec, dom)
    if wb:
        _, wx0, wy0, wz0, wx1, wy1, wz1 = wb
        # ESI 版语法：searchableBox 定义在 geometry 节，refinementRegions 按名引用；
        # 内联式写法会被静默忽略（'entries were not used'）导致尾流未加密。
        wake_geometry = (
            f"    wakeBox\n    {{\n"
            f"        type searchableBox;\n"
            f"        min ({wx0:g} {wy0:g} {wz0:g});\n"
            f"        max ({wx1:g} {wy1:g} {wz1:g});\n"
            f"    }}\n")
        wake_region = (
            f"        wakeBox\n        {{\n"
            f"            mode inside;\n"
            f"            levels ((1 {spec.wake_refine_level}));\n"
            f"        }}\n")
    else:
        wake_geometry = ""
        wake_region = ""
    return f"""/* AeroForge-Agent 自动生成 */
FoamFile
{{
    version     2.0;
    format      ascii;
    class       dictionary;
    object      snappyHexMeshDict;
}}

castellatedMesh true;
snap            true;
addLayers       true;

geometry
{{
    {spec.surface}.stl
    {{
        type triSurfaceMesh;
        name {spec.surface};
    }}
{wake_geometry}}};

castellatedMeshControls
{{
    maxLocalCells       1000000;
    maxGlobalCells      {spec.max_global_cells};
    minRefinementCells  10;
    maxLoadUnbalance    0.10;
    nCellsBetweenLevels {spec.n_cells_between_levels};

    features
    (
        {{
            file "{spec.surface}.eMesh";
            level {level};
        }}
    );

    refinementSurfaces
    {{
        {spec.surface}
        {{
            level ({level} {level});
        }}
    }}

    resolveFeatureAngle 30;

    refinementRegions
    {{
{wake_region}    }}

    locationInMesh ({cx:g} 0 {lz:g});

    allowFreeStandingZoneFaces true;
}}

snapControls
{{
    nSmoothPatch            3;
    tolerance               2.0;
    nSolveIter              30;
    nRelaxIter              5;
    nFeatureSnapIter        10;
    implicitFeatureSnap     false;
    explicitFeatureSnap     true;
    multiRegionFeatureSnap  false;
}}

addLayersControls
{{
    relativeSizes       true;
    layers
    {{
        "{spec.surface}"
        {{
            nSurfaceLayers 2;
        }}
    }}
    expansionRatio        1.2;
    finalLayerThickness   0.3;
    minThickness          0.1;
    nGrow                 0;
    featureAngle          60;
    slipFeatureAngle      30;
    nRelaxIter            5;
    nSmoothSurfaceNormals 1;
    nSmoothNormals        3;
    nSmoothThickness      10;
    maxFaceThicknessRatio 0.5;
    maxThicknessToMedialRatio 0.3;
    minMedialAxisAngle    90;
    nBufferCellsNoExtrude 0;
    nLayerIter            50;
}}

meshQualityControls
{{
    maxNonOrtho         65;
    maxBoundarySkewness 20;
    maxInternalSkewness 6;
    maxConcave          80;
    minFlatness         0.5;
    minVol              1e-13;
    minTetQuality       1e-15;
    minArea             -1;
    minTwist            0.02;
    minDeterminant      0.001;
    minFaceWeight       0.05;
    minVolRatio         0.01;
    minTriangleTwist    -1;
    nSmoothScale        4;
    errorReduction      0.75;
}}

autoBlockMesh false;
debug           0;

mergeTolerance  1e-6;
"""
