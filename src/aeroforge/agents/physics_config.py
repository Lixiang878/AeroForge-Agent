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
        solver = 'pimpleFoam' if task.regime == Regime.TRANSIENT else 'simpleFoam'
        case=Path(kwargs.get('workspace','workspace'))/task.task_id/'case'; case.mkdir(parents=True,exist_ok=True)
        spec=CaseSpec(
            stl_path=Path(g.stl_path),surface='body',bbox=g.bbox,
            velocity=task.velocity,density=task.fluid.density,
            nu=task.fluid.kinematic_viscosity,
            yaw_angle_deg=float(getattr(task,'yaw_angle_deg',0.0) or 0.0),
            solver_mode=task.regime.value,
            end_time=kwargs.get('end_time'),
            delta_t=kwargs.get('delta_t'),
            n_iterations=int(kwargs.get('n_iterations',600)),
            base_cell_size=kwargs.get('base_cell_size'),
            base_cells_per_L=int(kwargs.get('base_cells_per_L',22)),
            surface_refine_level=int(kwargs.get('surface_refine_level',2)),
            n_cells_between_levels=int(kwargs.get('n_cells_between_levels',2)),
            max_global_cells=int(kwargs.get('max_global_cells',8_000_000)),
            max_co=float(kwargs.get('max_co',0.8)),
            write_interval_t=kwargs.get('write_interval_t'),
            moving_ground=bool(kwargs.get('moving_ground',True)),
            upstream_slip_ground=bool(kwargs.get('upstream_slip_ground',True)),
            slip_ground_offset_L=float(kwargs.get('slip_ground_offset_L',0.75)),
            wake_refinement=bool(kwargs.get('wake_refinement',True)),
            wake_refine_level=int(kwargs.get('wake_refine_level',2)),
            nose_refinement=bool(kwargs.get('nose_refinement',True)),
            nose_refine_level=int(kwargs.get('nose_refine_level',5)),
            margins=tuple(kwargs.get('margins',(3.0,7.0,2.5,5.0))),
            wall_treatment=str(kwargs.get('wall_treatment','lowRe')),
            first_layer_yplus=float(kwargs.get('first_layer_yplus',1.2)),
            n_wall_layers=int(kwargs.get('n_wall_layers',15)),
            layer_expansion=float(kwargs.get('layer_expansion',1.2)),
            n_parallel=(int(kwargs['n_parallel'])
                        if kwargs.get('n_parallel') is not None else None))
        build_case(case,spec)
        runtime=RuntimeBridge()
        return {'status':'completed','solver':solver,'case_dir':case,'spec':spec,
                'task':task,'runtime_backend':runtime.info.backend,'notes':notes}
