from pathlib import Path
from ..core.models import Regime
from ..core.runtime_bridge import RuntimeBridge
from ..tools.case_builder import CaseSpec,build_case
class PhysicsConfigAgent:
    """物理配置：从零生成完整 OpenFOAM case（0/constant/system + triSurface）。

    case 生成是纯文件操作，离线也可完成（dry-run 时产出可审阅的算例目录）；
    是否真实执行由后续 MeshSmith/SimulationPilot 依据 RuntimeBridge 判定。
    """
    async def run(self, parsed, geometry, **kwargs):
        task=parsed['task']; g=geometry['geometry']
        notes=[]
        if task.regime==Regime.TRANSIENT:
            solver='simpleFoam'
            notes.append('当前工程路径为稳态 RANS（k-ω SST）；瞬态请求按稳态近似处理并在报告中声明')
        else:
            solver='simpleFoam'
        case=Path(kwargs.get('workspace','workspace'))/task.task_id/'case'; case.mkdir(parents=True,exist_ok=True)
        spec=CaseSpec(
            stl_path=Path(g.stl_path),surface='body',bbox=g.bbox,
            velocity=task.velocity,density=task.fluid.density,
            nu=task.fluid.kinematic_viscosity,
            yaw_angle_deg=float(getattr(task,'yaw_angle_deg',0.0) or 0.0),
            n_iterations=int(kwargs.get('n_iterations',600)),
            base_cell_size=kwargs.get('base_cell_size'),
            base_cells_per_L=int(kwargs.get('base_cells_per_L',22)),
            surface_refine_level=int(kwargs.get('surface_refine_level',2)),
            wall_treatment=str(kwargs.get('wall_treatment','lowRe')))
        build_case(case,spec)
        runtime=RuntimeBridge()
        return {'status':'completed','solver':solver,'case_dir':case,'spec':spec,
                'task':task,'runtime_backend':runtime.info.backend,'notes':notes}
