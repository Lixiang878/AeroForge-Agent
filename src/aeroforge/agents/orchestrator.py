from __future__ import annotations
from .requirement_parser import RequirementParserAgent
from .geometry_hunter import GeometryHunterAgent
from .mesh_smith import MeshSmithAgent
from .physics_config import PhysicsConfigAgent
from .simulation_pilot import SimulationPilotAgent
from .result_analyst import ResultAnalystAgent
class OrchestratorAgent:
    def __init__(self,workspace='workspace'):
        self.workspace=workspace; self.agents={'requirements':RequirementParserAgent(),'geometry':GeometryHunterAgent(),'mesh':MeshSmithAgent(),'physics':PhysicsConfigAgent(),'simulation':SimulationPilotAgent(),'analysis':ResultAnalystAgent()}
    async def run(self,prompt,**kwargs):
        state={'input':prompt,'outputs':{}}
        r=await self.agents['requirements'].run(prompt); state['outputs']['requirements']=r
        g=await self.agents['geometry'].run(r,workspace=self.workspace); state['outputs']['geometry']=g
        m=await self.agents['mesh'].run(g,r); state['outputs']['mesh']=m
        c=await self.agents['physics'].run(r,m,workspace=self.workspace); state['outputs']['physics']=c
        s=await self.agents['simulation'].run(c); state['outputs']['simulation']=s
        a=await self.agents['analysis'].run(s,r,g,m); state['outputs']['analysis']=a; state['status']='completed'; state['report']=a['report']; return state
