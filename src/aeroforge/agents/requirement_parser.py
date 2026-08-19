from __future__ import annotations
import re
from ..core.models import SimulationTask, FlowType, Regime
class RequirementParserAgent:
    async def run(self, prompt, **kwargs):
        text=str(prompt); warnings=[]
        vm=re.search(r"([0-9]+(?:\.[0-9]+)?)\s*(km/h|m/s)", text, re.I)
        velocity=float(vm.group(1))/3.6 if vm and vm.group(2).lower()=="km/h" else (float(vm.group(1)) if vm else 1.0)
        if not vm: warnings.append("未识别速度，使用 1.0 m/s")
        om=re.search(r"[\"“”]([^\"“”]+)[\"“”]",text); object_name=om.group(1) if om else "generic object"
        flow=FlowType.INTERNAL_FLOW if re.search(r"内流|管道|internal",text,re.I) else FlowType.EXTERNAL_AERODYNAMICS
        regime=Regime.TRANSIENT if re.search(r"瞬态|非定常|transient",text,re.I) else Regime.STEADY
        return {"status":"completed","task":SimulationTask(user_prompt=text,object_name=object_name,velocity=velocity,flow_type=flow,regime=regime),"warnings":warnings}
RequirementParser=RequirementParserAgent
