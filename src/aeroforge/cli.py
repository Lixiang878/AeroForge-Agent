import argparse,asyncio
from .agents import OrchestratorAgent
def main():
 p=argparse.ArgumentParser(); p.add_argument('prompt'); p.add_argument('--workspace',default='workspace'); a=p.parse_args(); r=asyncio.run(OrchestratorAgent(a.workspace).run(a.prompt)); print(f"报告已生成: {r['report'].markdown_report_path}"); print(f"Cd = {r['report'].simulation.force_coeffs.cd:.4f}")
if __name__=='__main__': main()
