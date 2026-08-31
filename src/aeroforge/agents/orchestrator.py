from __future__ import annotations
from .requirement_parser import RequirementParserAgent
from .geometry_hunter import GeometryHunterAgent
from .physics_config import PhysicsConfigAgent
from .mesh_smith import MeshSmithAgent
from .simulation_pilot import SimulationPilotAgent
from .result_analyst import ResultAnalystAgent


def _pipeline_status(stage_status: dict[str, str]) -> str:
    """聚合阶段状态，避免 dry-run/失败被分析阶段的完成状态覆盖。"""
    statuses = set(stage_status.values())
    if statuses & {"failed", "unknown"}:
        return "failed"
    if statuses & {"dry-run", "skipped"}:
        return "dry-run"
    return "completed"


class OrchestratorAgent:
    """六阶段编排：需求解析 → 几何 → 物理配置(建 case) → 网格 → 求解 → 分析。"""
    def __init__(self,workspace='workspace'):
        self.workspace=workspace; self.agents={'requirements':RequirementParserAgent(),'geometry':GeometryHunterAgent(),'physics':PhysicsConfigAgent(),'mesh':MeshSmithAgent(),'simulation':SimulationPilotAgent(),'analysis':ResultAnalystAgent()}
    async def run(self,prompt,**kwargs):
        state={'input':prompt,'outputs':{}}
        r=await self.agents['requirements'].run(prompt,**kwargs); state['outputs']['requirements']=r
        g=await self.agents['geometry'].run(r,workspace=self.workspace,**kwargs); state['outputs']['geometry']=g
        c=await self.agents['physics'].run(r,g,workspace=self.workspace,**kwargs); state['outputs']['physics']=c
        m=await self.agents['mesh'].run(c,r,**kwargs); state['outputs']['mesh']=m
        s=await self.agents['simulation'].run(c,m,**kwargs); state['outputs']['simulation']=s
        a=await self.agents['analysis'].run(s,r,g,m,**kwargs); state['outputs']['analysis']=a
        stage_status = {
            name: state['outputs'][name].get('status', 'unknown')
            for name in ('requirements', 'geometry', 'physics', 'mesh', 'simulation', 'analysis')
        }
        state['stage_status'] = stage_status
        state['status'] = _pipeline_status(stage_status)
        state['report']=a['report']
        return state
