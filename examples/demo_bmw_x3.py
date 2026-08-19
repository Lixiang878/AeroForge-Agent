import asyncio
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from aeroforge.agents import OrchestratorAgent
async def main():
    report=await OrchestratorAgent('workspace').run('做一辆 2026 款宝马 X3 的迎风 CFD 测试，风速 30 km/h，稳态不可压')
    print(f'报告已生成: {report["report"].markdown_report_path}')
    print(f'Cd = {report["report"].simulation.force_coeffs.cd:.4f}')
if __name__=='__main__': asyncio.run(main())
