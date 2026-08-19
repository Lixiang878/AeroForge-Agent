from pathlib import Path
from ..tools.mesh_tools import write_blockmesh_dict,write_snappy_dict
class MeshSmithAgent:
    async def run(self, geometry, parsed, **kwargs):
        g=geometry['geometry']; d=Path(g.stl_path).parents[1]/'mesh'; d.mkdir(parents=True,exist_ok=True); write_blockmesh_dict(g.bbox,g.characteristic_length,20,d); write_snappy_dict(g.stl_path,d,3)
        return {'status':'dry-run','mesh_dir':d,'geometry':g}
MeshSmith=MeshSmithAgent
