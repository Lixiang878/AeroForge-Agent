import time
from pathlib import Path
from ..core.models import SimReport
from ..core.runtime_bridge import RuntimeBridge
from ..tools.openfoam_tools import (
    run_solver,
    parse_residuals,
    parse_continuity_error,
    parse_force_coeffs,
    parse_force_breakdown,
    _latest_force_coeff_file,
)

_RESIDUAL_TOLERANCE = 1e-3
_MAX_FLUX_ERROR_PERCENT = 0.5
_REQUIRED_RESIDUAL_FIELDS = frozenset(("Ux", "Uy", "Uz", "p", "k", "omega"))


def _force_coeff_signature(case: Path):
    path = _latest_force_coeff_file(case)
    if path is None:
        return None
    try:
        stat = path.stat()
    except OSError:
        return None
    return (path, stat.st_mtime_ns, stat.st_size)


class SimulationPilotAgent:
    """求解：运行配置的 simpleFoam/pimpleFoam 并解析残差/力系数。

    dry-run 时不伪造任何气动系数（force_coeffs=None, converged=False）。
    网格阶段失败或未通过 checkMesh 时不执行求解。
    """
    async def run(self, config, mesh, **kwargs):
        case=Path(config['case_dir'])
        mesh_status=mesh.get('status','dry-run')
        mesh_report = mesh.get('mesh')
        bridge=RuntimeBridge()
        if not bridge.available:
            return {'status':'dry-run','runtime_backend':'unavailable',
                    'simulation':SimReport(case_dir=case,converged=False,final_residuals={},
                                           force_coeffs=None,flux_error_percent=0,runtime_seconds=0,
                                           notes=['未检测到 OpenFOAM 运行时，求解阶段为 dry-run']),
                    'notes':['未检测到 OpenFOAM 运行时，求解阶段为 dry-run']}
        mesh_ready = (getattr(mesh_report, 'passed_checkmesh', False)
                      and getattr(mesh_report, 'cell_count', 0) > 0)
        if mesh_status != 'completed' or not mesh_ready:
            if mesh_status != 'completed':
                note = f'网格阶段状态为 {mesh_status}，跳过求解'
            else:
                note = '网格报告未通过 checkMesh 或缺少有效单元数，跳过求解'
            return {'status':'skipped','runtime_backend':bridge.info.backend,
                    'simulation':SimReport(case_dir=case,converged=False,final_residuals={},
                                           force_coeffs=None,flux_error_percent=0,runtime_seconds=0,
                                           notes=[note]),
                    'notes':[note]}
        before_force_coeff = _force_coeff_signature(case)
        t0=time.perf_counter()
        res=run_solver(case,bridge,solver=config.get('solver','simpleFoam'))
        elapsed=time.perf_counter()-t0
        log=res.get('log_path')
        residuals=parse_residuals(log) if log else {}
        continuity_error = parse_continuity_error(log) if log else None
        fc=parse_force_coeffs(case)
        stale_force_coeff = (fc is not None
                             and before_force_coeff is not None
                             and _force_coeff_signature(case) == before_force_coeff)
        if stale_force_coeff:
            # 重跑失败/提前退出时，旧 postProcessing 文件可能仍存在；不能
            # 用它配合本次日志晋升为新结果。
            fc = None
        if fc is not None and log:
            bd=parse_force_breakdown(log)
            fc.cd_pressure=bd.get('cd_pressure')
            fc.cd_viscous=bd.get('cd_viscous')
        log_text = Path(log).read_text(encoding='utf-8', errors='ignore') if log and Path(log).exists() else ''
        missing_residuals = sorted(_REQUIRED_RESIDUAL_FIELDS.difference(residuals))
        high_residual = bool(residuals) and max(residuals.values()) > _RESIDUAL_TOLERANCE
        converged = (
            res.get('returncode') == 0
            and log_text.rstrip().endswith('End')
            and bool(residuals)
            and not missing_residuals
            and not high_residual
            and continuity_error is not None
            and continuity_error <= _MAX_FLUX_ERROR_PERCENT
            and fc is not None
        )
        notes = []
        if not converged:
            if res.get('timed_out'):
                notes.append('求解器超时，结果不完整')
            if res.get('returncode') != 0:
                notes.append(f"求解器返回码为 {res.get('returncode')}")
            if high_residual:
                notes.append(f"最终残差超过 {_RESIDUAL_TOLERANCE:g} 收敛门限")
            if missing_residuals:
                notes.append(f"残差字段缺失: {', '.join(missing_residuals)}")
            if continuity_error is None:
                notes.append('日志缺少全局连续性误差')
            elif continuity_error > _MAX_FLUX_ERROR_PERCENT:
                notes.append(f'通量误差 {continuity_error:.3g}% 超过 {_MAX_FLUX_ERROR_PERCENT:g}%')
            if fc is None:
                notes.append('缺少 forceCoeffs 输出' if not stale_force_coeff
                             else 'forceCoeffs 输出未在本次求解更新')
            if log_text and not log_text.rstrip().endswith('End'):
                notes.append('日志未以 End 结束')
            if not notes:
                notes.append('求解器未满足收敛门禁')
        return {'status':'completed' if converged else 'failed',
                'runtime_backend':bridge.info.backend,
                'simulation':SimReport(case_dir=case,converged=converged,
                                       final_residuals=residuals,force_coeffs=fc,
                                       flux_error_percent=round(continuity_error or 0.0, 6),
                                       runtime_seconds=round(elapsed,1), notes=notes),
                'notes':notes}
SimulationPilot=SimulationPilotAgent
