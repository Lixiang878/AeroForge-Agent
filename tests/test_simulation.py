import asyncio
import pytest
from aeroforge.agents import OrchestratorAgent
import aeroforge.core.runtime_bridge as rb


def test_dry_run_honest(tmp_path, monkeypatch):
    """dry-run：产出报告，但可视化 0 张（不伪造图像）、Cd 为 None。"""
    monkeypatch.setattr(rb, 'detect_runtime', lambda *a, **k: rb.RuntimeInfo(backend='unavailable'))
    r = asyncio.run(OrchestratorAgent(tmp_path).run(
        '做一个 Ahmed body 的迎风 CFD 测试，风速 30 km/h，稳态不可压'))
    report = r['report']
    assert report.task.velocity == pytest.approx(8.333333)
    assert report.task.object_name == 'Ahmed body'
    assert report.markdown_report_path.exists()
    assert report.visualization_paths == []          # 不再产出假图
    assert '不伪造' in report.visualization_note
    assert report.simulation.force_coeffs is None
    md = report.markdown_report_path.read_text(encoding='utf-8')
    assert 'N/A' in md and 'dry-run' in md


def test_dry_run_render_disabled(tmp_path, monkeypatch):
    monkeypatch.setattr(rb, 'detect_runtime', lambda *a, **k: rb.RuntimeInfo(backend='unavailable'))
    r = asyncio.run(OrchestratorAgent(tmp_path).run(
        'Ahmed body 迎风 40 m/s', render=False))
    assert r['report'].visualization_note == '按参数跳过高清可视化'
