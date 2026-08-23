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

import math
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
    yaw_angle_deg: float = 0.0                 # 风向角（偏航）：入口矢量/移动地面/阻力方向绕 z 轴旋转
    density: float = 1.225                     # kg/m3（forceCoeffs rhoInf 用）
    nu: float = 1.5e-5                         # m2/s
    turbulence_intensity: float = 0.005        # 入口湍流强度 I（风洞低湍流惯例）
    turbulence_viscosity_ratio: float = 5.0    # 远场 nut/nu（外气动低湍流风洞惯例 1–10）
    solver_mode: str = "steady"                # steady=simpleFoam / transient=pimpleFoam
    end_time: float | None = None              # 瞬态物理时长 (s)；None 时自动取 L/U
    delta_t: float | None = None               # 瞬态步长 (s)；None 时按 CFL≈0.7 估计
    max_co: float = 0.8                        # 瞬态最大库朗数（PIMPLE 可用至 ~2）
    write_interval_t: float | None = None      # 瞬态写盘间隔 (s)；None 时取总时长/40
    n_iterations: int = 600                    # simpleFoam 稳态迭代数
    base_cell_size: float | None = None        # 背景网格尺寸；None 时取 L/base_cells_per_L
    base_cells_per_L: int = 22                 # 特征长度方向背景网格分数
    surface_refine_level: int = 2              # snappy 表面细化级数
    n_cells_between_levels: int = 2
    max_global_cells: int = 8_000_000
    moving_ground: bool = True                 # 地面随来流移动（地面效应更真实）
    upstream_slip_ground: bool = True          # 上游地面滑移（抑制地面边界层堵死离地间隙）
    slip_ground_offset_L: float = 0.75         # 滑移地面在体前 0.75L 处转为移动地面
    wake_refinement: bool = True               # 尾流区局部加密（斜面涡/基座压力关键）
    wake_refine_level: int = 2               # 尾流加密盒的细化级数
    nose_refinement: bool = True               # 前缘局部加密（圆角曲率/滞止线解析关键）
    nose_refine_level: int = 5                 # 前缘加密盒细化级数
    margins: tuple[float, float, float, float] = DEFAULT_MARGINS
    # 壁面处理预设：
    # - "lowRe"：y+≈1 积分到壁面（kOmegaSST 低 Re 路线，15 层边界层，
    #   首层厚度按 y+ 目标自动估算）。Ahmed 验证表明 2 层粗边界层 +
    #   对数律壁面函数会把摩擦阻力高估近一个量级（Cd(f) 0.25 vs 物理
    #   期望 ~0.03），lowRe 为默认推荐。
    # - "wallFunction"：经典对数律壁面函数 + 2 层相对厚度边界层（粗而快，
    #   仅用于快速筛查；y+ 落在 1–30 缓冲区时结果不可信）。
    wall_treatment: str = "lowRe"
    first_layer_yplus: float = 1.2             # lowRe 首层目标 y+（留余量）
    n_wall_layers: int = 15                    # lowRe 边界层层数
    layer_expansion: float = 1.2               # 边界层膨胀比
    n_parallel: int | None = None              # 并行核数；设置时生成 decomposeParDict

    @property
    def characteristic_length(self) -> float:
        b = self.bbox
        if b is None:
            raise ValueError("bbox not set; call build_case or set bbox first")
        return max(b.x_max - b.x_min, b.y_max - b.y_min, b.z_max - b.z_min)

    def first_layer_thickness(self) -> float:
        """由目标 y+ 估算首层绝对厚度：Cf≈0.003（Re~3e6 平板经验），
        u_tau = U*sqrt(Cf/2)，y1 = y+*nu/u_tau。"""
        u_tau = self.velocity * math.sqrt(0.003 / 2.0)
        return self.first_layer_yplus * self.nu / u_tau


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
    (case / "0" / "k").write_text(_field_scalar("k", k_inf, spec.surface, spec.wall_treatment), encoding="utf-8")
    (case / "0" / "omega").write_text(_field_scalar("omega", omega_inf, spec.surface, spec.wall_treatment), encoding="utf-8")
    (case / "0" / "nut").write_text(_field_nut(spec.surface, spec.wall_treatment), encoding="utf-8")

    (case / "constant" / "transportProperties").write_text(
        _transport_properties(spec), encoding="utf-8")
    (case / "constant" / "turbulenceProperties").write_text(
        _turbulence_properties(), encoding="utf-8")

    (case / "system" / "controlDict").write_text(_control_dict(spec, dom), encoding="utf-8")
    (case / "system" / "fvSchemes").write_text(_fv_schemes(spec), encoding="utf-8")
    (case / "system" / "fvSolution").write_text(_fv_solution(spec), encoding="utf-8")
    (case / "system" / "blockMeshDict").write_text(_block_mesh_dict(dom, base, spec), encoding="utf-8")
    (case / "system" / "surfaceFeatureExtractDict").write_text(
        _surface_feature_dict(spec), encoding="utf-8")
    (case / "system" / "snappyHexMeshDict").write_text(
        _snappy_dict(spec, dom), encoding="utf-8")
    if spec.n_parallel:
        (case / "system" / "decomposeParDict").write_text(
            _decompose_dict(spec.n_parallel), encoding="utf-8")
    # ParaView 入口标记文件：双击/直接打开即可用 OpenFOAM reader 播放时间序列
    (case / (case.name + ".foam")).write_text("", encoding="utf-8")
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


def _inlet_vec(spec: CaseSpec) -> str:
    """按风向角计算入口速度矢量字符串（yaw=0 时保持 (U 0 0) 字面值）。"""
    yaw = math.radians(getattr(spec, "yaw_angle_deg", 0.0) or 0.0)
    uy = spec.velocity * math.sin(yaw)
    if abs(uy) < 1e-9:
        return f"{spec.velocity:g} 0 0"
    ux = spec.velocity * math.cos(yaw)
    return f"{ux:.6g} {uy:.6g} 0"


def _drag_dir(spec: CaseSpec) -> str:
    """阻力方向随风向旋转（升力恒为 z）。"""
    yaw = math.radians(getattr(spec, "yaw_angle_deg", 0.0) or 0.0)
    if abs(yaw) < 1e-9:
        return "(1 0 0)"
    return f"({math.cos(yaw):.6g} {math.sin(yaw):.6g} 0)"


def _field_u(spec: CaseSpec) -> str:
    vec = _inlet_vec(spec)
    ground_bc = (f"movingWallVelocity;\n        value           uniform ({vec})"
                 ) if spec.moving_ground else "noSlip"
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

internalField   uniform ({vec});

boundaryField
{{
    inlet
    {{
        type            fixedValue;
        value           uniform ({vec});
    }}
    outlet
    {{
        type            inletOutlet;
        inletValue      uniform (0 0 0);
        value           uniform ({vec});
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


def _field_scalar(name: str, value: float, surface: str, treatment: str = "lowRe") -> str:
    # k: 湍动能 m2/s2 -> [0 2 -2]；omega: 比耗散率 1/s -> [0 0 -1]
    dims = "[0 2 -2 0 0 0 0]" if name == "k" else "[0 0 -1 0 0 0 0]"
    # omegaWallFunction 自带粘性底层 blending，两种处理通用；
    # k 在低 Re 积分到壁面时需 kLowReWallFunction
    if name == "k":
        k_bc = "kLowReWallFunction" if treatment == "lowRe" else "kqRWallFunction"
    else:
        k_bc = "omegaWallFunction"
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
        type            {k_bc};
        value           uniform {value:g};
    }}
}}
"""


def _field_nut(surface: str, treatment: str = "lowRe") -> str:
    # nutUSpaldingWallFunction 基于 Spalding 连续律，y+ 从 <1 到 >100 全范围
    # 一致有效；nutkWallFunction 仅在对数区（y+>30）成立
    nut_bc = "nutUSpaldingWallFunction" if treatment == "lowRe" else "nutkWallFunction"
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
        type            {nut_bc};
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
    drag_dir = _drag_dir(spec)
    if spec.solver_mode == "transient":
        # 瞬态（pimpleFoam）：物理时长默认 3 个对流时间尺度，
        # 可调步长按 CFL≤0.8 控制，写盘间隔对齐动画帧（默认 40 帧）。
        end = spec.end_time or 3.0 * L / spec.velocity
        dt = spec.delta_t or 1e-4
        wi = spec.write_interval_t or end / 40.0
        return f"""/* AeroForge-Agent 自动生成 */
FoamFile
{{
    version     2.0;
    format      ascii;
    class       dictionary;
    object      controlDict;
}}

application     pimpleFoam;

startFrom       startTime;
startTime       0;
stopAt          endTime;
endTime         {end:g};
deltaT          {dt:g};
adjustTimeStep  yes;
maxCo           {spec.max_co:g};
maxDeltaT       {5 * dt:g};

writeControl    adjustableRunTime;
writeInterval   {wi:g};
purgeWrite      0;
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
        writeControl    adjustableRunTime;
        writeInterval   {wi / 2:g};

        patches         ({spec.surface});
        rho             rhoInf;
        rhoInf          {spec.density:g};
        liftDir         (0 0 1);
        dragDir         {drag_dir};
        CofR            (0 0 0);
        pitchAxis       (0 1 0);
        magUInf         {spec.velocity:g};
        lRef            {L:g};
        Aref            {front_area:g};
    }}
}}
"""
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
        dragDir         {drag_dir};
        CofR            (0 0 0);
        pitchAxis       (0 1 0);
        magUInf         {spec.velocity:g};
        lRef            {L:g};
        Aref            {front_area:g};
    }}
}}
"""


def _fv_schemes(spec: CaseSpec | None = None) -> str:
    ddt = "Euler" if (spec and spec.solver_mode == "transient") else "steadyState"
    return f"""/* AeroForge-Agent 自动生成 */
FoamFile
{{
    version     2.0;
    format      ascii;
    class       dictionary;
    object      fvSchemes;
}}

ddtSchemes
{{
    default         {ddt};
}}

gradSchemes
{{
    default         Gauss linear;
}}

divSchemes
{{
    default         none;
    div(phi,U)      bounded Gauss linearUpwind grad(U);
    div(phi,k)      bounded Gauss upwind;
    div(phi,omega)  bounded Gauss upwind;
    div((nuEff*dev2(T(grad(U))))) Gauss linear;
}}

laplacianSchemes
{{
    default         Gauss linear corrected;
}}

interpolationSchemes
{{
    default         linear;
}}

snGradSchemes
{{
    default         corrected;
}}

wallDist
{{
    method          meshWave;
}}
"""


def _fv_solution(spec: CaseSpec | None = None) -> str:
    if spec and spec.solver_mode == "transient":
        algo = """PIMPLE
{
    nOuterCorrectors    2;
    nCorrectors         2;
    nNonOrthogonalCorrectors 0;
}
"""
    else:
        algo = """SIMPLE
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
    return f"""/* AeroForge-Agent 自动生成 */
FoamFile
{{
    version     2.0;
    format      ascii;
    class       dictionary;
    object      fvSolution;
}}

solvers
{{
    p
    {{
        solver          GAMG;
        smoother        DICGaussSeidel;
        tolerance       1e-7;
        relTol          0.1;
    }}
    pFinal
    {{
        solver          GAMG;
        smoother        DICGaussSeidel;
        tolerance       1e-7;
        relTol          0;
    }}
    "(U|k|omega)"
    {{
        solver          smoothSolver;
        smoother        symGaussSeidel;
        tolerance       1e-8;
        relTol          0.1;
    }}
    UFinal
    {{
        solver          smoothSolver;
        smoother        symGaussSeidel;
        tolerance       1e-8;
        relTol          0;
    }}
    kFinal
    {{
        solver          smoothSolver;
        smoother        symGaussSeidel;
        tolerance       1e-8;
        relTol          0;
    }}
    omegaFinal
    {{
        solver          smoothSolver;
        smoother        symGaussSeidel;
        tolerance       1e-8;
        relTol          0;
    }}
}}

{algo}"""


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


def _decompose_dict(n: int) -> str:
    return f"""/* AeroForge-Agent 自动生成 */
FoamFile
{{
    version     2.0;
    format      ascii;
    class       dictionary;
    object      decomposeParDict;
}}

numberOfSubdomains {n};

method          scotch;
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


def _nose_box(spec: CaseSpec) -> tuple[str, float, float, float, float, float, float] | None:
    """前缘加密盒参数：罩住前鼻圆角与滞止线，半径外扩 0.2L。

    前缘圆角曲率若不被表面网格解析（如 R100 圆角弧上仅 ~5 个单元），
    加速吸力峰消失、滞止区虚大，压差阻力可虚高 ~0.2——Ahmed 验证
    八轮平台期的主要根源之一。
    """
    if not spec.nose_refinement:
        return None
    b = spec.bbox
    L = b.x_max - b.x_min
    pad = 0.2 * L
    return ("noseBox", b.x_min - pad, b.y_min - pad, 0.0,
            b.x_min + pad, b.y_max + pad, b.z_max + pad)


def _snappy_dict(spec: CaseSpec, dom: dict) -> str:
    # locationInMesh：物体正上方域顶附近，保证在流体域内
    cx = (spec.bbox.x_min + spec.bbox.x_max) / 2.0
    lz = dom["z_max"] * 0.9
    level = spec.surface_refine_level
    if spec.wall_treatment == "lowRe":
        first = spec.first_layer_thickness()
        layer_block = (
            f"    relativeSizes       false;\n"
            f"    layers\n    {{\n"
            f"        \"{spec.surface}\"\n        {{\n"
            f"            nSurfaceLayers {spec.n_wall_layers};\n"
            f"        }}\n    }}\n"
            f"    expansionRatio        {spec.layer_expansion:g};\n"
            f"    firstLayerThickness {first:.3e};\n"
            f"    minThickness          {first / 2:.3e};\n")
        relax_iter, layer_iter = 8, 70
    else:
        layer_block = (
            f"    relativeSizes       true;\n"
            f"    layers\n    {{\n"
            f"        \"{spec.surface}\"\n        {{\n"
            f"            nSurfaceLayers 2;\n"
            f"        }}\n    }}\n"
            f"    expansionRatio        {spec.layer_expansion:g};\n"
            f"    finalLayerThickness   0.3;\n"
            f"    minThickness          0.1;\n")
        relax_iter, layer_iter = 5, 50
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
    nb = _nose_box(spec)
    if nb:
        _, nx0, ny0, nz0, nx1, ny1, nz1 = nb
        nose_geometry = (
            f"    noseBox\n    {{\n"
            f"        type searchableBox;\n"
            f"        min ({nx0:g} {ny0:g} {nz0:g});\n"
            f"        max ({nx1:g} {ny1:g} {nz1:g});\n"
            f"    }}\n")
        nose_region = (
            f"        noseBox\n        {{\n"
            f"            mode inside;\n"
            f"            levels ((1 {spec.nose_refine_level}));\n"
            f"        }}\n")
    else:
        nose_geometry = ""
        nose_region = ""
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
{wake_geometry}{nose_geometry}}};

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
            level {level + 1 if spec.wall_treatment == "lowRe" else level};
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
{wake_region}{nose_region}    }}

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
{layer_block}    nGrow                 0;
    featureAngle          60;
    slipFeatureAngle      30;
    nRelaxIter            {relax_iter};
    nSmoothSurfaceNormals 1;
    nSmoothNormals        3;
    nSmoothThickness      10;
    maxFaceThicknessRatio 0.5;
    maxThicknessToMedialRatio 0.3;
    minMedialAxisAngle    90;
    nBufferCellsNoExtrude 0;
    nLayerIter            {layer_iter};
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
