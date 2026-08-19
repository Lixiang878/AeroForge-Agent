from aeroforge.tools.geometry_tools import *
def test_geometries(tmp_path):
 for fn in (create_car_stl,create_cylinder_stl,create_naca_stl):
  p=fn(tmp_path/(fn.__name__+'.stl')); b=validate_stl(p); assert b.x_max>b.x_min and bbox_diagonal(b)>0
