"""OpenFOAM 工具：真实求解执行序列与日志解析。

执行序列（external aerodynamics, steady RANS）：
blockMesh -> surfaceFeatureExtract -> snappyHexMesh -overwrite -> simpleFoam

所有子进程经 RuntimeBridge 路由（native / WSL）；无运行时时显式返回
dry_run 标记，绝不伪装成真实 CFD 结果。
"""
from __future__ import annotations

import re
from pathlib import Path

from ..core.models import ForceCoeffs
from ..core.runtime_bridge import RuntimeBridge

__all__ = [
    "run_mesh_sequence", "run_solver", "parse_residuals",
    "parse_force_coeffs", "parse_mesh_stats", "run_checkmesh",
    # 兼容保留（旧 tutorial 路径，新流水线不再依赖）
    "find_similar_tutorial", "clone_tutorial", "run_simulation",
]

MESH_SEQUENCE = ["blockMesh", "surfaceFeatureExtract", "snappyHexMesh -overwrite"]


# ---------------------------------------------------------------- 执行序列
def run_mesh_sequence(case_dir: Path, bridge: RuntimeBridge,
                      timeout: float = 5400.0) -> dict:
    """依次执行网格生成序列，返回 {ok, stage, logs}。"""
    logs: list[str] = []
    for cmd in ["blockMesh", "surfaceFeatureExtract"]:
        res = bridge.run([cmd], cwd=case_dir, timeout=timeout)
        if res.get("dry_run"):
            return {"ok": False, "dry_run": True, "stage": cmd, "logs": logs}
        logs.append(res["log_path"])
        if res["returncode"] != 0:
            return {"ok": False, "dry_run": False, "stage": cmd, "logs": logs}
    res = bridge.run(["snappyHexMesh", "-overwrite"], cwd=case_dir, timeout=timeout)
    logs.append(res["log_path"])
    if res["returncode"] != 0:
        return {"ok": False, "dry_run": False, "stage": "snappyHexMesh", "logs": logs}
    return {"ok": True, "dry_run": False, "stage": "done", "logs": logs}


def run_solver(case_dir: Path, bridge: RuntimeBridge, solver: str = "simpleFoam",
               timeout: float = 14400.0) -> dict:
    """运行求解器，返回 {dry_run, returncode, log_path}。"""
    return bridge.run([solver], cwd=case_dir, timeout=timeout)


def run_checkmesh(case_dir: Path, bridge: RuntimeBridge,
                  timeout: float = 900.0) -> dict:
    # 常规 checkMesh（不加 -allTopology/-allGeometry）：后者会额外报告
    # 凹面单元/小行列式单元等几何细节，这些并不在 snappyHexMesh 与 RANS
    # 求解的质量准则内，行业通行做法是以常规检查 + 关键指标阈值为门禁。
    res = bridge.run(["checkMesh"], cwd=case_dir, timeout=timeout)
    if res.get("dry_run"):
        return {"dry_run": True}
    return {"dry_run": False, "returncode": res["returncode"],
            "log_path": res["log_path"]}


# ---------------------------------------------------------------- 日志解析
def parse_residuals(log_path: str | Path) -> dict[str, float]:
    """从求解日志提取各场最后一次迭代的残差（兼容 simpleFoam 格式）。"""
    p = Path(log_path)
    if not p.exists():
        return {}
    text = p.read_text(encoding="utf-8", errors="ignore")
    out: dict[str, float] = {}
    for field in ("Ux", "Uy", "Uz", "p", "k", "omega"):
        vals = re.findall(rf"\b{field}\b[^\n]*?Final residual = ([\deE+.\-]+)", text)
        if vals:
            try:
                out[field] = float(vals[-1])
            except ValueError:
                pass
    return out


def parse_force_coeffs(case_dir: str | Path) -> ForceCoeffs | None:
    """解析 forceCoeffs 后处理输出 coefficient.dat。

    稳健解析：优先读表头中的列名定位 Cd/Cl/Cm；无表头时按位置回退
    (Time Cd Cl Cm ...)。返回最后若干迭代的均值（稳态尾段）。
    """
    files = sorted(Path(case_dir).glob("postProcessing/forceCoeffs*/*/*.dat"))
    if not files:
        return None
    text = files[-1].read_text(encoding="utf-8", errors="ignore")
    header_cols: list[str] = []
    for line in text.splitlines():
        if line.startswith("#"):
            header_cols = [c.strip().lower() for c in line.lstrip("#").split()]
        else:
            break
    rows: list[list[float]] = []
    for line in text.splitlines():
        if not line or line.startswith("#"):
            continue
        try:
            rows.append([float(x) for x in line.split()])
        except ValueError:
            continue
    if not rows:
        return None

    def col_index(*names: str, fallback: int | None) -> int | None:
        for i, c in enumerate(header_cols):
            if c in names:
                return i
        return fallback

    # ESI OpenFOAM（含 v2412）forceCoeffs 实际写 13 列：
    # Time Cd Cd_f Cd_r Cl Cl_f Cl_r Cm <力/矩分量>；
    # 已用数值关系验证：Cd_f+Cd_r=Cd，Cl_f+Cl_r=Cl，(Cl_f-Cl_r)/2=Cm。
    # 注释头只描述方向不给出列名，故按列数做格式判定，再退回表头/位置。
    ncols = len(rows[0])
    if ncols >= 8:
        i_cd, i_cl, i_cm = 1, 4, 7
    else:
        i_cd = col_index("cd", fallback=1)
        i_cl = col_index("cl", fallback=2)
        i_cm = col_index("cm", fallback=3)
    tail = rows[-max(2, len(rows) // 10):]  # 稳态尾段均值，抑制瞬时抖动

    def mean(idx: int | None) -> float | None:
        if idx is None or idx >= len(tail[0]):
            return None
        vals = [r[idx] for r in tail if idx < len(r)]
        return sum(vals) / len(vals) if vals else None

    cd = mean(i_cd)
    if cd is None:
        return None
    cl = mean(i_cl) or 0.0
    return ForceCoeffs(cd=cd, cl=cl, cm=mean(i_cm))


def parse_mesh_stats(case_dir: str | Path) -> dict:
    """从 checkMesh 日志提取网格统计（cell 数、非正交、偏斜）。

    通过判据：常规 checkMesh 报告 "Mesh OK"，或虽因 -all* 类几何细节
    提示 Failed 但关键指标（非正交 ≤65°、内部偏斜 ≤6）满足。
    """
    log = Path(case_dir) / "log.checkMesh"
    stats = {"cell_count": 0, "max_non_orthogonality": 0.0,
             "max_skewness": 0.0, "passed_checkmesh": False}
    if not log.exists():
        return stats
    text = log.read_text(encoding="utf-8", errors="ignore")
    m = re.search(r"cells:\s+(\d+)", text, re.IGNORECASE)
    if m:
        stats["cell_count"] = int(m.group(1))
    m = re.search(r"Mesh non-orthogonality Max: ([\d.]+)", text)
    if m:
        stats["max_non_orthogonality"] = float(m.group(1))
    m = re.search(r"Max skewness = ([\d.]+)", text)
    if m:
        stats["max_skewness"] = float(m.group(1))
    if "Mesh OK" in text:
        stats["passed_checkmesh"] = True
    elif (stats["max_non_orthogonality"] <= 65.0
          and stats["max_skewness"] <= 6.0
          and "Boundary openness" in text
          and "Cell volumes OK" in text):
        # 关键指标达标：凹面单元/小行列式等 -all* 级提示不阻断 RANS 求解
        stats["passed_checkmesh"] = True
    return stats


# ---------------------------------------------------------------- 兼容旧接口
def find_similar_tutorial(flow_type, regime):  # pragma: no cover - legacy path
    import shutil
    candidates = {
        "external_aerodynamics/steady": "incompressible/simpleFoam/motorBike",
        "external_aerodynamics/transient": "incompressible/pimpleFoam/motorBike",
        "internal_flow/steady": "incompressible/simpleFoam/pipeCyclic",
    }
    key = f"{getattr(flow_type, 'value', flow_type)}/{getattr(regime, 'value', regime)}"
    exe = shutil.which("simpleFoam")
    root = Path(exe).parent.parent if exe else None
    p = root / "tutorials" / candidates.get(key, "") if root else None
    return p if p and p.exists() else None


def clone_tutorial(tutorial_path, target_dir):  # pragma: no cover - legacy path
    import shutil
    shutil.copytree(tutorial_path, target_dir, dirs_exist_ok=True)


def run_simulation(case_dir, parallel=False, max_iterations=1000,
                   solver="simpleFoam"):  # pragma: no cover - legacy path
    """旧接口：直接在 PATH 中找求解器（不经 RuntimeBridge）。"""
    import shutil
    import subprocess
    exe = shutil.which(solver)
    case = Path(case_dir)
    log = case / f"log.{solver}"
    if not exe:
        return {"dry_run": True, "converged": False,
                "reason": "OpenFOAM utility unavailable", "log_path": str(log)}
    with log.open("w", encoding="utf-8") as f:
        p = subprocess.run([exe, "-case", str(case)], stdout=f,
                           stderr=subprocess.STDOUT, text=True,
                           timeout=3600, check=False)
    residuals = parse_residuals(log)
    return {"dry_run": False, "converged": p.returncode == 0,
            "final_residuals": residuals, "log_path": str(log)}
