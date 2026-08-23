# -*- coding: utf-8 -*-
"""高清烟线渲染入口（产品化后保留的薄封装）。

渲染逻辑已移入 src/aeroforge/tools/windtunnel_viz.py，
本脚本用普通 python 即可运行（自动定位并调用 pvpython）：

    python examples/paraview/streamline_hd.py <case_dir> [u_free_mps]
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from aeroforge.tools.windtunnel_viz import render_case  # noqa: E402


def main():
    p = argparse.ArgumentParser()
    p.add_argument("case", help="OpenFOAM 算例目录")
    p.add_argument("u_free", nargs="?", type=float, help="自由流速度 m/s（缺省从 0/U 读取）")
    a = p.parse_args()
    r = render_case(a.case, u_free=a.u_free)
    print(f"status: {r['status']}")
    if r["note"]:
        print(f"note: {r['note']}")
    for x in r["images"]:
        print(f"  {x}")


if __name__ == "__main__":
    main()
