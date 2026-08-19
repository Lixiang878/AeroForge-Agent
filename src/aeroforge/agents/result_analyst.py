from pathlib import Path
from ..core.models import FinalReport,MeshReport
from ..tools.viz_tools import plot_velocity_field,plot_pressure_surface,plot_streamlines,generate_markdown_report
class ResultAnalystAgent:
    async def run(self, simulation, parsed, geometry, mesh, **kwargs):
        task=parsed['task']; d=Path(geometry['geometry'].stl_path).parents[1]/'results'; d.mkdir(parents=True,exist_ok=True)
        paths=[plot_velocity_field(None,d/'velocity_slice.png'),plot_pressure_surface(None,d/'pressure_surface.png'),plot_streamlines(None,d/'streamlines.png')]
        report=FinalReport(task=task,geometry=geometry['geometry'],mesh=MeshReport(mesh_path=d,passed_checkmesh=False),simulation=simulation['simulation'],visualization_paths=paths,markdown_report_path=d/'report.md'); generate_markdown_report(report)
        return {'status':'completed','report':report}
ResultAnalyst=ResultAnalystAgent
