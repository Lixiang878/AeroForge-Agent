from pathlib import Path
from ..core.models import Regime
class PhysicsConfigAgent:
    async def run(self, parsed, mesh, **kwargs):
        task=parsed['task']; solver='pimpleFoam' if task.regime==Regime.TRANSIENT else 'simpleFoam'; case=Path(kwargs.get('workspace','workspace'))/task.task_id/'case'; case.mkdir(parents=True,exist_ok=True)
        return {'status':'dry-run','solver':solver,'case_dir':case,'task':task}
