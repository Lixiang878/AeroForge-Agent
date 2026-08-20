import sys

from aeroforge.core.runtime_bridge import RuntimeBridge, RuntimeInfo


def test_unavailable_backend_returns_dry_run(tmp_path):
    bridge = RuntimeBridge(RuntimeInfo(backend="unavailable"))
    res = bridge.run(["blockMesh"], cwd=tmp_path)
    assert res["dry_run"] is True
    assert res["returncode"] is None


def test_fallback_wsl_path_conversion():
    f = RuntimeBridge._fallback_wsl_path(r"E:\GitHub项目\aeroforge-agent\case dir")
    assert f == "/mnt/e/GitHub项目/aeroforge-agent/case dir"


def test_native_backend_executes_and_logs(tmp_path):
    bridge = RuntimeBridge(RuntimeInfo(backend="native"))
    res = bridge.run([sys.executable, "-c", "print('bridge-ok')"], cwd=tmp_path)
    assert res["dry_run"] is False and res["returncode"] == 0
    log_text = open(res["log_path"], encoding="utf-8").read()
    assert "bridge-ok" in log_text


def test_runtime_path_native_passthrough(tmp_path):
    bridge = RuntimeBridge(RuntimeInfo(backend="native"))
    assert bridge.runtime_path(tmp_path) == str(tmp_path)
