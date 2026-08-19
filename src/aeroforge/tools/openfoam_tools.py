from __future__ import annotations
import re, shutil, subprocess
from pathlib import Path
from ..core.models import ForceCoeffs

def find_similar_tutorial(flow_type,regime):
    candidates={'external_aerodynamics/steady':'incompressible/simpleFoam/motorBike','external_aerodynamics/transient':'incompressible/pimpleFoam/motorBike','internal_flow/steady':'incompressible/simpleFoam/pipeCyclic'}
    key=f'{getattr(flow_type,"value",flow_type)}/{getattr(regime,"value",regime)}'; root=Path(shutil.which('simpleFoam') or '').parent.parent if shutil.which('simpleFoam') else None
    p=root/'tutorials'/candidates.get(key,'') if root else None; return p if p and p.exists() else None
def clone_tutorial(tutorial_path,target_dir):
    import shutil as s; s.copytree(tutorial_path,target_dir,dirs_exist_ok=True)
def run_simulation(case_dir,parallel=False,max_iterations=1000,solver='simpleFoam'):
    exe=shutil.which(solver); case=Path(case_dir); log=case/f'log.{solver}'
    if not exe: return {'dry_run':True,'converged':False,'reason':'OpenFOAM utility unavailable','log_path':str(log)}
    with log.open('w',encoding='utf-8') as f: p=subprocess.run([exe,'-case',str(case)],stdout=f,stderr=subprocess.STDOUT,text=True,timeout=3600,check=False)
    residuals=parse_residuals(log); return {'dry_run':False,'converged':p.returncode==0,'final_residuals':residuals,'log_path':str(log)}
def parse_residuals(log_path):
    text=Path(log_path).read_text(encoding='utf-8',errors='ignore'); out={}
    for field in ('Ux','Uy','Uz','p','k','omega'):
        vals=re.findall(rf'\b{field}\b.*?Final residual = ([\deE+.-]+)',text)
        if vals: out[field]=float(vals[-1])
    return out
def parse_force_coeffs(case_dir):
    files=list(Path(case_dir).glob('postProcessing/forceCoeffs/*/coefficient.dat'))+list(Path(case_dir).glob('postProcessing/forceCoeffs/*/coefficient*.dat'))
    if not files: return None
    rows=[]
    for line in files[-1].read_text(encoding='utf-8',errors='ignore').splitlines():
        if line and not line.startswith('#'):
            try: rows.append([float(x) for x in line.split()])
            except ValueError: pass
    if not rows: return None
    row=rows[-1]; return ForceCoeffs(cd=row[1] if len(row)>1 else 0,cl=row[4] if len(row)>4 else 0,cm=row[7] if len(row)>7 else None)
def configure_boundary_conditions(case_dir,velocity,fluid): return Path(case_dir)
def add_force_coeffs_function(case_dir,char_length,velocity): return Path(case_dir)
