"""高清风洞可视化：调用 pvpython 对真实收敛场离屏渲染烟线图。

诚实边界：没有收敛场或找不到 pvpython 时返回 skipped 并说明原因，
绝不用合成场伪造 CFD 图像（v0.2.0 的 viz_tools 曾用假场画图，v0.4.0 移除）。
"""
from __future__ import annotations

import glob
import math
import re
import shutil
import subprocess
from pathlib import Path

__all__ = ["find_pvpython", "render_case", "read_freestream"]

_TEMPLATE = Path(__file__).parent / "pv_templates" / "streamline_hd.py"
_VIEWS = ("front", "wake", "side")


def find_pvpython() -> Path | None:
    """定位 pvpython：PATH 优先，其次常见安装目录。"""
    exe = shutil.which("pvpython") or shutil.which("pvpython.exe")
    if exe:
        return Path(exe)
    pats = [
        r"C:/Program Files/ParaView*/bin/pvpython.exe",
        r"C:/Program Files (x86)/ParaView*/bin/pvpython.exe",
        r"D:/Program Files/ParaView*/bin/pvpython.exe",
        r"E:/Program Files/ParaView*/bin/pvpython.exe",
        r"D:/ParaView*/bin/pvpython.exe",
        r"E:/ParaView*/bin/pvpython.exe",
    ]
    for pat in pats:
        hits = sorted(glob.glob(pat))
        if hits:
            return Path(hits[-1])
    return None


def read_freestream(case_dir: str | Path) -> float | None:
    """从 0/U 的 uniform 向量读入口速度模长。"""
    f = Path(case_dir) / "0" / "U"
    if not f.exists():
        return None
    m = re.search(
        r"uniform\s*\(\s*([-+\d.eE]+)\s+([-+\d.eE]+)\s+([-+\d.eE]+)\s*\)",
        f.read_text(encoding="utf-8", errors="ignore"))
    if not m:
        return None
    return math.sqrt(sum(float(g) ** 2 for g in m.groups()))


def _has_result_field(case: Path) -> bool:
    """求解器是否写出过非零时刻的 U 场（0/ 是初始场，不算）。"""
    if not (case / "constant" / "polyMesh").exists():
        return False
    for t in case.iterdir():
        if (t.is_dir() and re.fullmatch(r"\d+(\.\d+)?", t.name)
                and t.name != "0" and (t / "U").exists()):
            return True
    return False


def render_case(case_dir: str | Path, u_free: float | None = None,
                timeout: float = 900.0) -> dict:
    """渲染三机位高清烟线图。

    返回 {"status": completed|skipped|failed, "images": [Path...], "note": str}。
    """
    case = Path(case_dir).resolve()
    if not case.exists():
        return {"status": "skipped", "images": [],
                "note": f"算例目录不存在: {case}"}
    if not _has_result_field(case):
        return {"status": "skipped", "images": [],
                "note": "无收敛场（缺少非零时刻 U），跳过可视化"}
    pv = find_pvpython()
    if pv is None:
        return {"status": "skipped", "images": [],
                "note": "未找到 pvpython，高清渲染跳过（安装 ParaView 后自动启用）"}
    if u_free is None or u_free <= 0:
        u_free = read_freestream(case) or 40.0
    try:
        proc = subprocess.run(
            [str(pv), str(_TEMPLATE), str(case), f"{u_free:g}"],
            capture_output=True, text=True, timeout=timeout, encoding="utf-8",
            errors="replace")
    except subprocess.TimeoutExpired:
        return {"status": "failed", "images": [],
                "note": f"渲染超时（>{timeout:g}s）"}
    imgs = []
    for v in _VIEWS:
        p = case / "results" / f"streamline_hd_{v}.png"
        if p.exists() and p.stat().st_size > 20_000:
            imgs.append(p)
    if len(imgs) == len(_VIEWS):
        return {"status": "completed", "images": imgs, "note": ""}
    tail = (proc.stderr or proc.stdout or "")[-400:]
    return {"status": "failed", "images": imgs, "note": tail.strip()}
