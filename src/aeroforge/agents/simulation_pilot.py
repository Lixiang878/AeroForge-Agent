from ..core.models import SimReport,ForceCoeffs
class SimulationPilotAgent:
    async def run(self, config, **kwargs):
        return {'status':'dry-run','simulation':SimReport(case_dir=config['case_dir'],converged=False,final_residuals={},force_coeffs=ForceCoeffs(cd=.4,cl=0),flux_error_percent=0,runtime_seconds=0)}
SimulationPilot=SimulationPilotAgent
