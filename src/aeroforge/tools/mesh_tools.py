from __future__ import annotations
import re, shutil, subprocess
from pathlib import Path
from ..core.models import BoundingBox, MeshReport

def write_blockmesh_dict(bbox: BoundingBox, char_length: float, resolution: int, output_dir: Path):
    out=Path(output_dir); out.mkdir(parents=True,exist_ok=True); nx=max(4,int((bbox.x_max-bbox.x_min)*resolution/char_length)); ny=max(4,int((bbox.y_max-bbox.y_min)*resolution/char_length)); nz=max(4,int((bbox.z_max-bbox.z_min)*resolution/char_length))
    text=f'''FoamFile {{ version 2.0; format ascii; class dictionary; object blockMeshDict; }}\nconvertToMeters 1;\nvertices (({bbox.x_min} {bbox.y_min} {bbox.z_min}) ({bbox.x_max} {bbox.y_min} {bbox.z_min}) ({bbox.x_max} {bbox.y_max} {bbox.z_min}) ({bbox.x_min} {bbox.y_max} {bbox.z_min}) ({bbox.x_min} {bbox.y_min} {bbox.z_max}) ({bbox.x_max} {bbox.y_min} {bbox.z_max}) ({bbox.x_max} {bbox.y_max} {bbox.z_max}) ({bbox.x_min} {bbox.y_max} {bbox.z_max}));\nblocks ((hex (0 1 2 3 4 5 6 7) ({nx} {ny} {nz}) simpleGrading (1 1 1)));\nboundary ();\n'''
    p=out/'blockMeshDict'; p.write_text(text,encoding='utf-8'); return p
def write_snappy_dict(stl_path,output_dir,refinement_level=3):
    p=Path(output_dir)/'snappyHexMeshDict'; p.parent.mkdir(parents=True,exist_ok=True); p.write_text(f'''FoamFile {{ version 2.0; format ascii; class dictionary; object snappyHexMeshDict; }}\ncastellatedMesh true; snap true; addLayers false;\ngeometry {{ model.stl {{ type triSurfaceMesh; name model; }} }}\ncastellatedMeshControls {{ maxLocalCells 1000000; maxGlobalCells 2000000; refinementSurfaces {{ model {{ level ({refinement_level} {refinement_level}); }} }} }}\nsnapControls {{ nSmoothPatch 3; }}\naddLayersControls {{ relativeSizes true; }}\nmeshQualityControls {{ }}\n''',encoding='utf-8'); return p
def parse_checkmesh(text,mesh_path):
    def val(pattern):
        m=re.search(pattern,text,re.I); return float(m.group(1)) if m else 0.0
    cells=int(val(r'(?:(?:cells)|(?:cells:))\s*[:=]?\s*(\d+)')); non=val(r'maximum non-orthogonality\s*[:=]\s*([\d.]+)'); skew=val(r'maximum skewness\s*[:=]\s*([\d.]+)')
    return MeshReport(mesh_path=Path(mesh_path),cell_count=cells,max_non_orthogonality=non,max_skewness=skew,passed_checkmesh=non<85 and skew<8)
def run_mesh_pipeline(case_dir,**kwargs):
    case=Path(case_dir); exe=shutil.which('checkMesh'); report=case/'meshReport.txt'
    if not exe: return MeshReport(mesh_path=case,passed_checkmesh=False)
    p=subprocess.run([exe,'-case',str(case)],capture_output=True,text=True,timeout=3600,check=False); return parse_checkmesh(p.stdout+p.stderr,case)
