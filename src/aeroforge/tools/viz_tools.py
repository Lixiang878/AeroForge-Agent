from __future__ import annotations

import os
from pathlib import Path


def generate_markdown_report(final_report, viz_note: str = "") -> Path:
    """生成 Markdown 报告：嵌真实渲染图、Cd 压差/摩擦分解、诚实标注 dry-run。

    v0.2.0 的 plot_velocity_field / plot_streamlines / plot_pressure_surface
    用合成函数画"假 CFD 图"，v0.4.0 起删除；真实可视化见 windtunnel_viz。
    """
    p = Path(final_report.markdown_report_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    sim = final_report.simulation
    # 求解未通过收敛门禁时，日志中可能仍留下中间 forceCoeffs；这些值只
    # 能作为诊断数据，不能晋升为报告中的结果，避免用户误把部分迭代当成
    # 可复现的气动系数。
    f = sim.force_coeffs if sim.converged else None
    na_reason = ('N/A（dry-run，未真实求解）'
                 if any('dry-run' in note for note in sim.notes)
                 else 'N/A（未通过收敛门禁）')
    cd_txt = f'{f.cd:.4f}' if f else na_reason
    cl_txt = f'{f.cl:.4f}' if f else na_reason
    if f and f.cd_pressure is not None:
        bd_txt = (f'- 压差阻力: {f.cd_pressure:.4f}\n- 摩擦阻力: '
                  f'{f.cd_viscous:.4f}' if f.cd_viscous is not None else '')
    else:
        bd_txt = '- 分解: N/A（需求解日志）'

    if sim.converged:
        sim_txt = (f'- 收敛: 是\n- 最终残差: {sim.final_residuals}\n'
                   f'- 最终全局连续性误差: {sim.flux_error_percent:g}%\n'
                   f'- 求解耗时: {sim.runtime_seconds:.0f}s')
    else:
        gate_notes = "；".join(sim.notes) if sim.notes else "未满足收敛门禁"
        sim_txt = ('- 收敛: 否（dry-run 或未收敛；以下气动系数均为 N/A，'
                   f'不虚构数值）\n- 门禁说明: {gate_notes}')

    viz_lines = []
    def report_relative(path: str | Path) -> str:
        return Path(os.path.relpath(Path(path), p.parent)).as_posix()

    if final_report.visualization_paths:
        viz_lines.append('真实场离屏渲染（ParaView，2400×1350）：\n')
        for x in final_report.visualization_paths:
            viz_lines.append(f'![{Path(x).stem}]({report_relative(x)})\n')
    if final_report.animation_paths:
        viz_lines.append('真实场动画（稳态场相机环绕或真实物理时间步，见说明）：\n')
        for x in final_report.animation_paths:
            if Path(x).suffix.lower() == '.gif':
                viz_lines.append(f'![{Path(x).stem}]({report_relative(x)})\n')
            else:
                viz_lines.append(f'[{Path(x).name}]({report_relative(x)})\n')
    if getattr(final_report, 'interactive_paths', None):
        viz_lines.append('交互式三维风洞视图（鼠标轨道旋转、滚轮缩放、播放/拖动输运时间）：\n')
        for x in final_report.interactive_paths:
            viz_lines.append(f'[{Path(x).name}]({report_relative(x)})\n')
    viz_lines.append(viz_note or '')

    p.write_text(f'''# AeroForge 仿真报告

## 任务
- 对象: {final_report.task.object_name}
- 风速: {final_report.task.velocity:.3g} m/s
- 工况: {final_report.task.regime.value}

## 几何
- 来源: {final_report.geometry.source}
- 特征长度: {final_report.geometry.characteristic_length:.3f} m

## 网格
- 单元数: {final_report.mesh.cell_count}
- 最大非正交性: {final_report.mesh.max_non_orthogonality}
- 通过 checkMesh: {final_report.mesh.passed_checkmesh}

## 仿真
{sim_txt}

## 气动参数
- 阻力系数 Cd: {cd_txt}
- 升力系数 Cl: {cl_txt}
{bd_txt}

## 可视化
{chr(10).join(viz_lines)}
''', encoding='utf-8')
    return p
