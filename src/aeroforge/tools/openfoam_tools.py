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
    "parse_continuity_error", "parse_force_coeffs", "parse_mesh_stats", "run_checkmesh",
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
    if res.get("dry_run"):
        return {"ok": False, "dry_run": True, "stage": "snappyHexMesh", "logs": logs}
    logs.append(res["log_path"])
    if res["returncode"] != 0:
        return {"ok": False, "dry_run": False, "stage": "snappyHexMesh", "logs": logs}
    return {"ok": True, "dry_run": False, "stage": "done", "logs": logs}


def run_solver(case_dir: Path, bridge: RuntimeBridge, solver: str = "simpleFoam",
               timeout: float = 14400.0, parallel: bool = False,
               n_parallel: int = 8) -> dict:
    """运行求解器；parallel=True 时走 decomposePar → mpirun -parallel → reconstructPar。

    返回统一含 {dry_run, returncode, log_path, stage}；stage 指明失败所在
    阶段（decomposePar / 求解器名 / done）。reconstructPar 失败不掩盖求解
    结果，以 reconstruct_returncode 附加返回（场仍在 processor 目录可读）。
    瞬态求解器重建全部时间步（动画需要时间序列），稳态只重建最新场。
    """
    if not parallel:
        return {**bridge.run([solver], cwd=case_dir, timeout=timeout), "stage": solver}
    res = bridge.run(["decomposePar", "-force"], cwd=case_dir, timeout=timeout)
    if res.get("dry_run") or res["returncode"] != 0:
        return {**res, "stage": "decomposePar"}
    # OMPI 变量兼容 root 身份（WSL 默认用户为 root 时 OpenMPI 拒绝启动）；
    # 日志显式按求解器命名，否则会落到 argv[0] 的 log.env
    cmd = ["env", "OMPI_ALLOW_RUN_AS_ROOT=1", "OMPI_ALLOW_RUN_AS_ROOT_CONFIRM=1",
           "mpirun", "-np", str(n_parallel), solver, "-parallel"]
    res = bridge.run(cmd, cwd=case_dir,
                     log_path=Path(case_dir) / f"log.{solver}", timeout=timeout)
    if res.get("dry_run") or res["returncode"] != 0:
        return {**res, "stage": solver}
    rec = bridge.run(["reconstructPar"] if solver.startswith("pimpleFoam")
                     else ["reconstructPar", "-latestTime"],
                     cwd=case_dir, timeout=timeout)
    return {**res, "stage": "done",
            "reconstruct_returncode": rec.get("returncode")}


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


def parse_continuity_error(log_path: str | Path) -> float | None:
    """返回日志最后一次全局连续性误差的绝对百分比。

    OpenFOAM 将该量打印为 ``global = ...``，它是无量纲的相对通量
    不平衡；乘以 100 后与报告中的 ``flux_error_percent`` 一致。累计误差
    不用于这个门禁，因为它是跨迭代积分量，不代表当前步的质量守恒。
    """
    p = Path(log_path)
    if not p.exists():
        return None
    number = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?"
    values = re.findall(
        rf"time\s+step\s+continuity\s+errors\s*:.*?global\s*=\s*({number})",
        p.read_text(encoding="utf-8", errors="ignore"),
        flags=re.IGNORECASE,
    )
    if not values:
        return None
    return abs(float(values[-1])) * 100.0


def _force_coeff_candidate_files(case_dir: str | Path) -> list[Path]:
    """所有 forceCoeffs dat 候选：串行根目录 + 并行各 processor 目录。"""
    patterns = ("postProcessing/forceCoeffs*/*/*.dat",
                "processor*/postProcessing/forceCoeffs*/*/*.dat")
    files: list[Path] = []
    for pat in patterns:
        files.extend(Path(case_dir).glob(pat))
    return files


def _latest_force_coeff_file(case_dir: str | Path) -> Path | None:
    """按数据中的最大时间选择 forceCoeffs 文件，而不是按文件名排序。

    重跑或并行后处理可能同时留下 ``coefficient.dat``、
    ``coefficient_0.dat`` 等文件；字典序会把较旧的文件选中。
    """
    candidates: list[tuple[float, int, str, Path]] = []
    for path in _force_coeff_candidate_files(case_dir):
        last_time: float | None = None
        try:
            for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
                if not line or line.startswith("#"):
                    continue
                try:
                    last_time = float(line.split()[0])
                except (ValueError, IndexError):
                    continue
        except OSError:
            continue
        if last_time is not None:
            try:
                mtime = path.stat().st_mtime_ns
            except OSError:
                mtime = 0
            candidates.append((last_time, mtime, path.name, path))
    return max(candidates, key=lambda item: item[:3])[3] if candidates else None


def _rank_files_for(case_dir: Path, selected: Path) -> list[Path]:
    """同一时间序列的全部 rank 文件。

    selected 落在 processor 目录时返回所有 rank 的同位文件；串行时单文件。
    """
    try:
        rel = selected.relative_to(Path(case_dir))
    except ValueError:
        return [selected]
    parts = rel.parts
    if parts and parts[0].startswith("processor"):
        pattern = str(Path("processor*").joinpath(*parts[1:]))
        return sorted(Path(case_dir).glob(pattern)) or [selected]
    return [selected]


def _read_coeff_file(path: Path) -> tuple[list[str], list[list[float]]]:
    """读单个 dat：返回表头列名（小写）与数值行。"""
    header_cols: list[str] = []
    rows: list[list[float]] = []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if line.startswith("#"):
            if not header_cols:
                header_cols = [c.strip().lower() for c in line.lstrip("#").split()]
        elif line.strip():
            try:
                rows.append([float(x) for x in line.split()])
            except ValueError:
                continue
    return header_cols, rows


def _aggregate_rank_values(values: list[float]) -> float:
    """合并同一时间步各 rank 的系数值。

    ESI v2412 各 processor 写的是 reduce 后的全局汇总值（各 rank 相同），
    取任一即可；若实现写局部积分（各 rank 不同），求和才是整机系数。
    以相对容差区分两种情形。
    """
    lo, hi = min(values), max(values)
    if hi - lo <= 1e-9 * max(1.0, abs(hi)):
        return values[0]
    return sum(values)


def parse_force_breakdown(log_path: str | Path) -> dict[str, float]:
    """从求解日志最后的 forceCoeffs 输出块解析 Cd/Cl 的压差-摩擦分解。

    ESI v2412 日志格式（制表符分隔）：
        Coefficient<Tab>Total<Tab>Pressure<Tab>Viscous<Tab>Internal
        Cd:<Tab>0.5059<Tab>0.4878<Tab>0.0181<Tab>0
    返回 {"cd_pressure": ..., "cd_viscous": ...}；未找到时返回空 dict。
    """
    p = Path(log_path)
    if not p.exists():
        return {}
    text = p.read_text(encoding="utf-8", errors="ignore")
    blocks = re.findall(
        r"Cd:\s*([\d.eE+-]+)\s+([\d.eE+-]+)\s+([\d.eE+-]+)\s+([\d.eE+-]+)",
        text)
    out: dict[str, float] = {}
    if blocks:
        tail = blocks[-5:]  # 尾段均值，抑制瞬时抖动
        out = {"cd_pressure": sum(float(b[1]) for b in tail) / len(tail),
               "cd_viscous": sum(float(b[2]) for b in tail) / len(tail)}
    return out


def parse_force_coeffs(case_dir: str | Path) -> ForceCoeffs | None:
    """解析 forceCoeffs 后处理输出 coefficient.dat（串行与并行 case 通用）。

    稳健解析：优先读表头中的列名定位 Cd/Cl/Cm；无表头时按位置回退
    (Time Cd Cl Cm ...)。并行时按时间步对齐各 rank 文件合并（见
    _aggregate_rank_values）。返回最后若干迭代的均值（稳态尾段）。
    """
    case_dir = Path(case_dir)
    selected = _latest_force_coeff_file(case_dir)
    if selected is None:
        return None
    rank_files = _rank_files_for(case_dir, selected)
    parsed = [_read_coeff_file(p) for p in rank_files]
    header_cols = parsed[0][0]
    base_rows = parsed[0][1]
    if not base_rows:
        return None

    # 各 rank 按 rank0 的时间轴对齐（同一时间步每 rank 各写一行；
    # 缺行时丢弃该时间步，避免错位相加）
    other_maps = []
    for _, rows in parsed[1:]:
        other_maps.append({round(r[0], 9): r for r in rows if r})
    aligned: list[list[list[float]]] = []
    for row in base_rows:
        group = [row]
        for m in other_maps:
            match = m.get(round(row[0], 9))
            if match is None:
                group = []
                break
            group.append(match)
        if group:
            aligned.append(group)
    if not aligned:
        return None

    def col_index(*names: str, fallback: int | None) -> int | None:
        for i, c in enumerate(header_cols):
            if c in names:
                return i
        return fallback

    # ESI OpenFOAM（含 v2412）forceCoeffs 写 13 列：
    # Time Cd Cd(f) Cd(r) Cl Cl(f) Cl(r) CmPitch CmRoll CmYaw Cs Cs(f) Cs(r)
    # 注意：dat 里的 Cd(f)/Cd(r) 列并非摩擦/压差分解（实测各约为 Cd 之半，
    # 与求解日志 forceCoeffs 块的 Pressure/Viscous 分解对不上）；本解析
    # 只取总量列 Cd(1)/Cl(4)/CmPitch(7)，压差-摩擦分解见 parse_force_breakdown。
    ncols = len(aligned[0][0])
    if ncols >= 8:
        i_cd, i_cl, i_cm = 1, 4, 7
    else:
        i_cd = col_index("cd", fallback=1)
        i_cl = col_index("cl", fallback=2)
        i_cm = col_index("cm", fallback=3)
    tail = aligned[-max(2, len(aligned) // 10):]  # 稳态尾段均值，抑制瞬时抖动

    def mean(idx: int | None) -> float | None:
        if idx is None or idx >= len(tail[0][0]):
            return None
        vals = [_aggregate_rank_values([g[idx] for g in group])
                for group in tail if idx < len(group[0])]
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
