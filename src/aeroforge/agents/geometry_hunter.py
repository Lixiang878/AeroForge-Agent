from pathlib import Path
from ..core.models import GeometryInfo
from ..tools.geometry_tools import create_car_stl,create_cylinder_stl,create_naca_stl,validate_stl,bbox_diagonal
class GeometryHunterAgent:
    async def run(self, parsed, **kwargs):
        task=parsed['task']; out=Path(kwargs.get('workspace','workspace'))/task.task_id/'geometry'/'model.stl'; out.parent.mkdir(parents=True,exist_ok=True)
        if 'naca' in task.object_name.lower(): create_naca_stl(out); source='parametric_naca'
        elif 'cylinder' in task.object_name.lower(): create_cylinder_stl(out); source='parametric_cylinder'
        else: create_car_stl(out); source='parametric_simplified_car'
        bbox=validate_stl(out)
        return {'status':'completed','geometry':GeometryInfo(stl_path=out,bbox=bbox,characteristic_length=bbox_diagonal(bbox),source=source)}
GeometryHunter=GeometryHunterAgent
