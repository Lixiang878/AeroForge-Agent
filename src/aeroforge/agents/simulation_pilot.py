import time
from pathlib import Path
from ..core.models import SimReport
from ..core.runtime_bridge import RuntimeBridge
from ..tools.openfoam_tools import run_solver,parse_residuals,parse_force_coeffs
class SimulationPilotAgent:
    """求解：运行 simpleFoam 并解析残差/力系数。

    dry-run 时不伪造任何气动系数（force_coeffs=None, converged=False）。
    网格阶段失败或未通过 checkMesh 时不执行求解。
    """
    async def run(self, config, mesh, **kwargs):
        case=Path(config['case_dir'])
        mesh_status=mesh.get('status','dry-run')
        bridge=RuntimeBridge()
        if not bridge.available:
            return {'status':'dry-run','runtime_backend':'unavailable',
                    'simulation':SimReport(case_dir=case,converged=False,final_residuals={},
                                           force_coeffs=None,flux_error_percent=0,runtime_seconds=0),
                    'notes':['未检测到 OpenFOAM 运行时，求解阶段为 dry-run']}
        if mesh_status!='completed':
            return {'status':'skipped','runtime_backend':bridge.info.backend,
                    'simulation':SimReport(case_dir=case,converged=False,final_residuals={},
                                           force_coeffs=None,flux_error_percent=0,runtime_seconds=0),
                    'notes':[f'网格阶段状态为 {mesh_status}，跳过求解']}
        t0=time.perf_counter()
        res=run_solver(case,bridge,solver=config.get('solver','simpleFoam'))
        elapsed=time.perf_counter()-t0
        log=res.get('log_path')
        residuals=parse_residuals(log) if log else {}
        fc=parse_force_coeffs(case)
        converged=(res['returncode']==0) and bool(residuals)
        return {'status':'completed' if converged else 'failed',
                'runtime_backend':bridge.info.backend,
                'simulation':SimReport(case_dir=case,converged=converged,
                                       final_residuals=residuals,force_coeffs=fc,
                                       flux_error_percent=0,runtime_seconds=round(elapsed,1)),
                'notes':[] if converged else ['求解器未收敛或日志缺失，结果不可信']}
SimulationPilot=SimulationPilotAgent
