import asyncio
import pytest
from aeroforge.agents import OrchestratorAgent
import aeroforge.core.runtime_bridge as rb
def test_dry_run(tmp_path, monkeypatch):
 monkeypatch.setattr(rb, 'detect_runtime', lambda *a, **k: rb.RuntimeInfo(backend='unavailable'))
 r=asyncio.run(OrchestratorAgent(tmp_path).run('做一辆 2026 款宝马 X3 的迎风 CFD 测试，风速 30 km/h，稳态不可压')); report=r['report']; assert report.task.velocity==pytest.approx(8.333333); assert report.markdown_report_path.exists(); assert len(report.visualization_paths)==3
