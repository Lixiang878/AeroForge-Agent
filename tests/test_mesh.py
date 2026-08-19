from aeroforge.core.models import BoundingBox
from aeroforge.tools.mesh_tools import write_blockmesh_dict,write_snappy_dict

def test_dicts(tmp_path):
 b=BoundingBox(x_min=-1,x_max=2,y_min=-1,y_max=1,z_min=0,z_max=1); a=write_blockmesh_dict(b,1,20,tmp_path); s=write_snappy_dict(tmp_path/'model.stl',tmp_path); assert 'vertices' in a.read_text() and 'refinementSurfaces' in s.read_text()
