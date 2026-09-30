# -*- coding: utf-8 -*-
"""并行求解链路回归：run_solver 命令序列 + processor forceCoeffs 解析 + pilot 接线。"""
import asyncio
from pathlib import Path

import pytest

import aeroforge.agents.simulation_pilot as pilot
from aeroforge.core.models import MeshReport
from aeroforge.core.runtime_bridge import RuntimeInfo, RuntimeBridge
from aeroforge.tools.openfoam_tools import (
    _latest_force_coeff_file,
    parse_force_coeffs,
    run_solver,
)


class RecordingBridge(RuntimeBridge):
    """记录 argv 的假桥（native 后端身份），返回码按序弹出，默认 0。"""

    def __init__(self, returncodes=()):
        super().__init__(info=RuntimeInfo(backend="native", solver_path="simpleFoam"))
        self.calls: list[list[str]] = []
        self.log_paths: list[str | None] = []
        self.returncodes = list(returncodes)

    def run(self, argv, cwd, log_path=None, timeout=7200.0):  # noqa: D401
        self.calls.append([str(a) for a in argv])
        self.log_paths.append(str(log_path) if log_path else None)
        rc = self.returncodes.pop(0) if self.returncodes else 0
        return {"dry_run": False, "returncode": rc,
                "log_path": str(log_path or Path(cwd) / "log.x"),
                "backend": "native", "timed_out": False}


def _write_coeff_dat(path: Path, rows, cd_col=1):
    """写 13 列 ESI forceCoeffs dat（Time Cd Cd(f) Cd(r) Cl ... Cm ...）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# Time\tCd\tCd(f)\tCd(r)\tCl\tCl(f)\tCl(r)\tCmPitch"
             "\tCmRoll\tCmYaw\tCs\tCs(f)\tCs(r)"]
    for r in rows:
        lines.append("\t".join(str(x) for x in r))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _row(t, cd, cl=0.05, cm=0.01):
    return [t, cd, cd / 2, cd / 2, cl, cl / 2, cl / 2, cm, 0, 0, 0, 0, 0]


# ---------------------------------------------------------------- run_solver
def test_run_solver_serial_unchanged(tmp_path):
    bridge = RecordingBridge()
    res = run_solver(tmp_path, bridge, solver="simpleFoam")
    assert bridge.calls == [["simpleFoam"]]
    assert res["returncode"] == 0 and res["stage"] == "simpleFoam"


def test_run_solver_parallel_sequence_steady(tmp_path):
    bridge = RecordingBridge()
    res = run_solver(tmp_path, bridge, parallel=True, n_parallel=4)
    assert [c[0] for c in bridge.calls] == ["decomposePar", "env", "reconstructPar"]
    assert bridge.calls[0] == ["decomposePar", "-force"]
    assert bridge.calls[1][:5] == ["env", "OMPI_ALLOW_RUN_AS_ROOT=1",
                                   "OMPI_ALLOW_RUN_AS_ROOT_CONFIRM=1",
                                   "mpirun", "-np"]
    assert bridge.calls[1][5:] == ["4", "simpleFoam", "-parallel"]
    # 求解日志按求解器命名，而不是 argv[0] 的 log.env
    assert bridge.log_paths[1].endswith("log.simpleFoam")
    assert bridge.calls[2] == ["reconstructPar", "-latestTime"]
    assert res["stage"] == "done" and res["returncode"] == 0


def test_run_solver_parallel_transient_reconstructs_all_times(tmp_path):
    bridge = RecordingBridge()
    run_solver(tmp_path, bridge, solver="pimpleFoam", parallel=True, n_parallel=2)
    assert bridge.calls[2] == ["reconstructPar"]


def test_run_solver_parallel_decompose_failure_short_circuits(tmp_path):
    bridge = RecordingBridge(returncodes=[1])
    res = run_solver(tmp_path, bridge, parallel=True, n_parallel=4)
    assert len(bridge.calls) == 1  # mpirun 不应被调用
    assert res["stage"] == "decomposePar" and res["returncode"] == 1


def test_run_solver_parallel_solver_failure_skips_reconstruct(tmp_path):
    bridge = RecordingBridge(returncodes=[0, 2])
    res = run_solver(tmp_path, bridge, parallel=True, n_parallel=4)
    assert len(bridge.calls) == 2
    assert res["stage"] == "simpleFoam" and res["returncode"] == 2


def test_run_solver_parallel_reconstruct_failure_does_not_mask_result(tmp_path):
    bridge = RecordingBridge(returncodes=[0, 0, 1])
    res = run_solver(tmp_path, bridge, parallel=True, n_parallel=4)
    assert res["returncode"] == 0
    assert res["reconstruct_returncode"] == 1


# ------------------------------------------------------------ parse_force_coeffs
def test_parse_force_coeffs_serial_regression(tmp_path):
    _write_coeff_dat(tmp_path / "postProcessing" / "forceCoeffs1" / "0" / "coefficient.dat",
                     [_row(1, 0.40), _row(2, 0.42), _row(3, 0.44), _row(4, 0.46)])
    fc = parse_force_coeffs(tmp_path)
    assert fc is not None and fc.cd == pytest.approx(0.45)


def test_parse_force_coeffs_processor_global_values(tmp_path):
    # ESI v2412 行为：各 processor 写 reduce 后的全局值（相同）
    rows = [_row(1, 0.40), _row(2, 0.42), _row(3, 0.44), _row(4, 0.46)]
    for rank in range(4):
        _write_coeff_dat(tmp_path / f"processor{rank}" / "postProcessing"
                         / "forceCoeffs" / "0" / "coefficient.dat", rows)
    fc = parse_force_coeffs(tmp_path)
    assert fc is not None
    assert fc.cd == pytest.approx(0.45)  # 不应被乘以 rank 数


def test_parse_force_coeffs_processor_local_values_summed(tmp_path):
    # 兼容写局部积分的实现：各 rank 值互不相同，整机系数 = 各 rank 之和
    rows = [_row(1, 0.40), _row(2, 0.42), _row(3, 0.44), _row(4, 0.46)]
    shares = (0.1, 0.2, 0.3, 0.4)
    for rank, share in enumerate(shares):
        scaled = [[r[0]] + [v * share for v in r[1:]] for r in rows]
        _write_coeff_dat(tmp_path / f"processor{rank}" / "postProcessing"
                         / "forceCoeffs" / "0" / "coefficient.dat", scaled)
    fc = parse_force_coeffs(tmp_path)
    assert fc is not None
    assert fc.cd == pytest.approx(0.45)
    assert fc.cl == pytest.approx(0.05)


def test_parse_force_coeffs_rank_missing_time_step_dropped(tmp_path):
    rows = [_row(1, 0.40), _row(2, 0.42), _row(3, 0.44), _row(4, 0.46)]
    _write_coeff_dat(tmp_path / "processor0" / "postProcessing" / "forceCoeffs"
                     / "0" / "coefficient.dat", rows)
    _write_coeff_dat(tmp_path / "processor1" / "postProcessing" / "forceCoeffs"
                     / "0" / "coefficient.dat", rows[1:])  # rank1 缺首行
    fc = parse_force_coeffs(tmp_path)
    assert fc is not None
    assert fc.cd == pytest.approx(0.45)  # 尾段 2/3/4 步均值


def test_latest_force_coeff_file_prefers_newest_processor_series(tmp_path):
    # 串行残留旧 postProcessing + 并行新 processor 系列 → 按数据最大时间选后者
    _write_coeff_dat(tmp_path / "postProcessing" / "forceCoeffs" / "0" / "coefficient.dat",
                     [_row(1, 0.1), _row(2, 0.1)])
    _write_coeff_dat(tmp_path / "processor0" / "postProcessing" / "forceCoeffs"
                     / "0" / "coefficient.dat",
                     [_row(1, 0.3), _row(2, 0.3), _row(9, 0.3)])
    picked = _latest_force_coeff_file(tmp_path)
    assert picked is not None and "processor0" in str(picked)


# ---------------------------------------------------------------- pilot 接线
def _mesh_ok():
    return {"status": "completed",
            "mesh": MeshReport(mesh_path=Path("."), cell_count=1, passed_checkmesh=True)}


def test_pilot_passes_parallel_config_from_spec(tmp_path, monkeypatch):
    import types
    captured = {}

    def fake_run_solver(case, bridge, solver="simpleFoam", **kwargs):
        captured.update(kwargs, solver=solver)
        return {"returncode": 0, "log_path": str(case / "log.simpleFoam"),
                "stage": "done"}

    spec = types.SimpleNamespace(n_parallel=6)
    monkeypatch.setattr(pilot, "RuntimeBridge", lambda: RecordingBridge())
    monkeypatch.setattr(pilot, "run_solver", fake_run_solver)
    result = asyncio.run(pilot.SimulationPilotAgent().run(
        {"case_dir": tmp_path, "solver": "simpleFoam", "spec": spec}, _mesh_ok()))
    assert captured["parallel"] is True
    assert captured["n_parallel"] == 6
    assert result.get("parallel") == {"n_processes": 6}


def test_pilot_serial_when_spec_has_no_n_parallel(tmp_path, monkeypatch):
    captured = {}

    def fake_run_solver(case, bridge, solver="simpleFoam", **kwargs):
        captured.update(kwargs, solver=solver)
        return {"returncode": 0, "log_path": str(case / "log.simpleFoam"),
                "stage": "done"}

    monkeypatch.setattr(pilot, "RuntimeBridge", lambda: RecordingBridge())
    monkeypatch.setattr(pilot, "run_solver", fake_run_solver)
    asyncio.run(pilot.SimulationPilotAgent().run(
        {"case_dir": tmp_path, "solver": "simpleFoam"}, _mesh_ok()))
    assert captured["parallel"] is False and captured["n_parallel"] == 1


def test_pilot_notes_failed_stage(tmp_path, monkeypatch):
    log = tmp_path / "log.simpleFoam"
    log.write_text("End\n", encoding="utf-8")

    def fake_run_solver(case, bridge, solver="simpleFoam", **kwargs):
        return {"returncode": 1, "log_path": str(log), "stage": "decomposePar",
                "timed_out": False}

    monkeypatch.setattr(pilot, "RuntimeBridge", lambda: RecordingBridge())
    monkeypatch.setattr(pilot, "run_solver", fake_run_solver)
    result = asyncio.run(pilot.SimulationPilotAgent().run(
        {"case_dir": tmp_path, "solver": "simpleFoam"}, _mesh_ok()))
    assert result["status"] == "failed"
    assert any("decomposePar" in note for note in result["notes"])
