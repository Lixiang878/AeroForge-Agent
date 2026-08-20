from __future__ import annotations
from .requirement_parser import RequirementParserAgent
from .geometry_hunter import GeometryHunterAgent
from .physics_config import PhysicsConfigAgent
from .mesh_smith import MeshSmithAgent
from .simulation_pilot import SimulationPilotAgent
from .result_analyst import ResultAnalystAgent
class OrchestratorAgent:
    """六阶段编排：需求解析 → 几何 → 物理配置(建 case) → 网格 → 求解 → 分析。"""
    def __init__(self,workspace='workspace'):
        self.workspace=workspace; self.agents={'requirements':RequirementParserAgent(),'geometry':GeometryHunterAgent(),'physics':PhysicsConfigAgent(),'mesh':MeshSmithAgent(),'simulation':SimulationPilotAgent(),'analysis':ResultAnalystAgent()}
    async def run(self,prompt,**kwargs):
        state={'input':prompt,'outputs':{}}
        r=await self.agents['requirements'].run(prompt); state['outputs']['requirements']=r
        g=await self.agents['geometry'].run(r,workspace=self.workspace); state['outputs']['geometry']=g
        c=await self.agents['physics'].run(r,g,workspace=self.workspace,**kwargs); state['outputs']['physics']=c
        m=await self.agents['mesh'].run(c,r,**kwargs); state['outputs']['mesh']=m
        s=await self.agents['simulation'].run(c,m,**kwargs); state['outputs']['simulation']=s
        a=await self.agents['analysis'].run(s,r,g,m); state['outputs']['analysis']=a; state['status']='completed'; state['report']=a['report']; return state
