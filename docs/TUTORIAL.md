# Tutorial

To add a geometry, implement a triangle generator and expose a `create_*_stl` function in `geometry_tools.py`, then select it in `GeometryHunterAgent`. To add a solver, map a regime to its OpenFOAM utility in `PhysicsConfigAgent` and extend log parsing in `openfoam_tools.py`.
