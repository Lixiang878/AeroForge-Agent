from pathlib import Path
from ..core.models import FinalReport,MeshReport
from ..tools.viz_tools import generate_markdown_report
from ..tools.windtunnel_viz import render_case
class ResultAnalystAgent:
    """分析与报告：真实求解收敛后调用 pvpython 渲染高清烟线图。

    dry-run / 未收敛 / 无 pvpython 时不渲染、不造假图，仅在报告中说明。
    """
    async def run(self, simulation, parsed, geometry, mesh, **kwargs):
        task=parsed['task']; d=Path(geometry['geometry'].stl_path).parents[1]/'results'; d.mkdir(parents=True,exist_ok=True)
        sim=simulation['simulation']; viz_paths=[]; viz_note=''
        if kwargs.get('render',True) is False:
            viz_note='按参数跳过高清可视化'
        elif sim.converged:
            r=render_case(sim.case_dir,u_free=task.velocity)
            viz_paths=r['images']; viz_note=r['note']
        else:
            viz_note='求解未收敛或为 dry-run，高清可视化未执行（不伪造图像）'
        mesh_report=mesh.get('mesh') if isinstance(mesh.get('mesh'),MeshReport) else MeshReport(mesh_path=d,passed_checkmesh=False)
        report=FinalReport(task=task,geometry=geometry['geometry'],mesh=mesh_report,simulation=sim,
                           visualization_paths=viz_paths,markdown_report_path=d/'report.md',
                           visualization_note=viz_note)
        generate_markdown_report(report,viz_note=viz_note)
        return {'status':'completed','report':report}
ResultAnalyst=ResultAnalystAgent
