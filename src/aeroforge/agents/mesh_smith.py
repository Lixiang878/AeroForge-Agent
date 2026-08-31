from pathlib import Path
from ..core.models import MeshReport
from ..core.runtime_bridge import RuntimeBridge
from ..tools.openfoam_tools import run_mesh_sequence,run_checkmesh,parse_mesh_stats
class MeshSmithAgent:
    """网格：blockMesh -> surfaceFeatureExtract -> snappyHexMesh -> checkMesh。

    无 OpenFOAM 运行时 -> 显式 dry-run（保留 case 目录供审阅），
    绝不把 dry-run 报告成有效网格。
    """
    async def run(self, config, parsed, **kwargs):
        case=Path(config['case_dir'])
        bridge=RuntimeBridge()
        if not bridge.available:
            return {'status':'dry-run','runtime_backend':'unavailable',
                    'mesh':MeshReport(mesh_path=case,passed_checkmesh=False),
                    'notes':['未检测到 OpenFOAM 运行时，网格阶段为 dry-run']}
        seq=run_mesh_sequence(case,bridge)
        if not seq['ok']:
            return {'status':'failed','runtime_backend':bridge.info.backend,
                    'mesh':MeshReport(mesh_path=case,passed_checkmesh=False),
                    'notes':[f"网格序列在 {seq['stage']} 失败，日志: {seq['logs'][-1] if seq['logs'] else 'N/A'}"]}
        check = run_checkmesh(case, bridge)
        if check.get('dry_run') or check.get('returncode') != 0:
            return {'status':'failed','runtime_backend':bridge.info.backend,
                    'mesh':MeshReport(mesh_path=case,passed_checkmesh=False),
                    'notes':['checkMesh 命令执行失败（见 log.checkMesh），结果不可信，终止求解']}
        stats=parse_mesh_stats(case)
        report=MeshReport(mesh_path=case,cell_count=stats['cell_count'],
                          max_non_orthogonality=stats['max_non_orthogonality'],
                          max_skewness=stats['max_skewness'],
                          passed_checkmesh=stats['passed_checkmesh'])
        if not report.passed_checkmesh:
            return {'status':'failed','runtime_backend':bridge.info.backend,'mesh':report,
                    'notes':['checkMesh 未通过（见 log.checkMesh），结果不可信，终止求解']}
        if report.cell_count <= 0:
            return {'status':'failed','runtime_backend':bridge.info.backend,'mesh':report,
                    'notes':['checkMesh 日志缺少有效单元数，结果不可信，终止求解']}
        return {'status':'completed','runtime_backend':bridge.info.backend,'mesh':report,'notes':[]}
MeshSmith=MeshSmithAgent
