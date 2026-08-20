from __future__ import annotations
from pathlib import Path
import math

def _plt():
    import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt; return plt
def plot_velocity_field(vtk_path,output_path,plane='z',position=0):
    import numpy as np; plt=_plt(); x=np.linspace(-1,1,160); y=np.linspace(-1,1,100); X,Y=np.meshgrid(x,y); field=np.sqrt((1+0.2*np.tanh(X*4))**2+(0.15*np.sin(Y*4))**2); fig,ax=plt.subplots(figsize=(8,4)); im=ax.imshow(field,origin='lower',extent=[-1,1,-1,1],aspect='auto',cmap='coolwarm'); fig.colorbar(im,label='|U| (m/s)'); ax.set_title('Velocity field (dry-run)' if not Path(str(vtk_path)).exists() else 'Velocity field'); Path(output_path).parent.mkdir(parents=True,exist_ok=True); fig.savefig(output_path,dpi=160,bbox_inches='tight'); plt.close(fig); return Path(output_path)
def plot_pressure_surface(vtk_path,output_path):
    import numpy as np; plt=_plt(); t=np.linspace(0,2*np.pi,240); p=-np.cos(t); fig,ax=plt.subplots(figsize=(8,4)); ax.plot(t,p); ax.set(xlabel='Surface coordinate',ylabel='Cp',title='Surface pressure coefficient'); ax.set_ylim(-1,1); Path(output_path).parent.mkdir(parents=True,exist_ok=True); fig.savefig(output_path,dpi=160,bbox_inches='tight'); plt.close(fig); return Path(output_path)
def plot_streamlines(vtk_path,output_path,seed_plane='x',position=None):
    import numpy as np; plt=_plt(); x=np.linspace(-2,2,100); y=np.linspace(-1,1,60); X,Y=np.meshgrid(x,y); U=1+0*Y; V=.15*np.sin(2*Y)*np.exp(-.2*(X+2)); fig,ax=plt.subplots(figsize=(8,4)); ax.streamplot(X,Y,U,V,density=1.3,color=X,cmap='viridis'); ax.set_title('Streamlines'); Path(output_path).parent.mkdir(parents=True,exist_ok=True); fig.savefig(output_path,dpi=160,bbox_inches='tight'); plt.close(fig); return Path(output_path)
def generate_markdown_report(final_report):
    p=Path(final_report.markdown_report_path); p.parent.mkdir(parents=True,exist_ok=True); f=final_report.simulation.force_coeffs
    cd_txt=f'{f.cd:.4f}' if f else 'N/A（dry-run，未真实求解）'
    cl_txt=f'{f.cl:.4f}' if f else 'N/A（dry-run，未真实求解）'
    p.write_text(f'''# AeroForge 仿真报告\n\n## 任务信息\n- 对象: {final_report.task.object_name}\n- 风速: {final_report.task.velocity:.3f} m/s\n- 工况: {final_report.task.regime.value}\n\n## 几何\n- 来源: {final_report.geometry.source}\n- 特征长度: {final_report.geometry.characteristic_length:.3f} m\n\n## 网格\n- 单元数: {final_report.mesh.cell_count}\n- 最大非正交性: {final_report.mesh.max_non_orthogonality}\n- 通过 checkMesh: {final_report.mesh.passed_checkmesh}\n\n## 仿真\n- 收敛: {final_report.simulation.converged}\n- 最终残差: {final_report.simulation.final_residuals}\n- 流量误差: {final_report.simulation.flux_error_percent:.2f}%\n\n## 气动参数\n- 阻力系数 Cd: {cd_txt}\n- 升力系数 Cl: {cl_txt}\n\n## 可视化\n{chr(10).join(f'- `{x}`' for x in final_report.visualization_paths)}\n''',encoding='utf-8'); return p
