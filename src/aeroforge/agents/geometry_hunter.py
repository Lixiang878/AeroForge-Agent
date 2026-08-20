from pathlib import Path
from ..core.models import GeometryInfo
from ..tools.geometry_tools import create_car_stl,create_cylinder_stl,create_naca_stl,bbox_diagonal
from ..tools.stl_tools import ahmed_body_stl,read_stl_bbox
class GeometryHunterAgent:
    """几何获取：参数化生成（Ahmed 基准 / 简化车 / 圆柱 / NACA），输出 STL + 包围盒。"""
    async def run(self, parsed, **kwargs):
        task=parsed['task']; out=Path(kwargs.get('workspace','workspace'))/task.task_id/'geometry'/'model.stl'; out.parent.mkdir(parents=True,exist_ok=True)
        name=task.object_name.lower()
        if task.upload_stl_path and Path(task.upload_stl_path).exists():
            import shutil; shutil.copy2(task.upload_stl_path,out); source='upload'
        elif 'ahmed' in name:
            slant=25.0
            import re as _re
            m=_re.search(r'(\d+(?:\.\d+)?)\s*(?:°|度|deg)',task.object_name)
            if m: slant=float(m.group(1))
            ahmed_body_stl(out,slant_angle_deg=slant); source=f'parametric_ahmed_{slant:g}deg'
        elif 'naca' in name: create_naca_stl(out); source='parametric_naca'
        elif 'cylinder' in name: create_cylinder_stl(out); source='parametric_cylinder'
        else: create_car_stl(out); source='parametric_simplified_car'
        bbox=read_stl_bbox(out)
        return {'status':'completed','geometry':GeometryInfo(stl_path=out,bbox=bbox,characteristic_length=bbox_diagonal(bbox),source=source)}
GeometryHunter=GeometryHunterAgent
