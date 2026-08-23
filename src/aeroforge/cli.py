import argparse,asyncio
from .agents import OrchestratorAgent
def main():
 p=argparse.ArgumentParser(); p.add_argument('prompt'); p.add_argument('--workspace',default='workspace'); a=p.parse_args(); r=asyncio.run(OrchestratorAgent(a.workspace).run(a.prompt)); print(f"报告已生成: {r['report'].markdown_report_path}"); fc=r['report'].simulation.force_coeffs; print(f"Cd = {fc.cd:.4f}" if fc else "Cd = N/A（dry-run：无 OpenFOAM 运行时或未收敛，不虚构数值）")
if __name__=='__main__': main()
