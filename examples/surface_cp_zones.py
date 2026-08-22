"""车身表面分区压力系数诊断（零求解成本，读收敛场）。

用途：Cd 偏差归因——把 body patch 面元按外法向分区（前表面/顶面/斜面/
基座/侧面/底面），输出各分区面积与面积加权 Cp、对压差阻力的贡献，
并给出 forceCoeffs 日志中 Cd 的压差/摩擦分解对照。

注意：VTK OpenFOAM reader 读出的 patch 面点序经 Newell 法给出的是
**内法向**（实测前表面 n.x>0 且 Cp 为正压可证），本脚本按内法向约定分类，
外法向 = -n；压差贡献公式已相应取号。

用法：
    python examples/surface_cp_zones.py <case_dir> [--q 980]
    # case_dir 含收敛时间步与 postProcessing/forceCoeffs*；q=0.5*rho*U^2
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import numpy as np
import vtk
from vtk.util.numpy_support import vtk_to_numpy as v2n

AREF = 0.112032  # Ahmed body 迎风面积 m2（W*H）


def find_block(mb, name):
    it = mb.NewIterator()
    it.GoToFirstItem()
    while not it.IsDoneWithTraversal():
        d = it.GetCurrentDataObject()
        meta = it.GetCurrentMetaData()
        if meta is not None and name in meta.Get(vtk.vtkCompositeDataSet.NAME()):
            return d
        if isinstance(d, vtk.vtkCompositeDataSet):
            f = find_block(d, name)
            if f is not None:
                return f
        it.GoToNextItem()
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description="Surface Cp zone diagnostics")
    ap.add_argument("case_dir")
    ap.add_argument("--q", type=float, default=980.0,
                    help="动压 0.5*rho*U^2（默认 1.225*40^2/2）")
    args = ap.parse_args()
    case = Path(args.case_dir)

    foam = case / "diag.foam"
    if not foam.exists():
        foam.write_text("", encoding="utf-8")

    r = vtk.vtkOpenFOAMReader()
    r.SetFileName(str(foam))
    r.SetPatchArrayStatus("internalMesh", 0)
    r.SetPatchArrayStatus("patch/body", 1)
    r.Update()
    tv = r.GetTimeValues()
    r.UpdateTimeStep(max(tv.GetValue(i) for i in range(tv.GetNumberOfTuples())))
    r.Update()
    body = find_block(r.GetOutput(), "body")
    if body is None:
        print("body patch 未找到", file=sys.stderr)
        return 1

    if not isinstance(body, vtk.vtkPolyData):
        gf = vtk.vtkGeometryFilter()
        gf.SetInputData(body)
        gf.Update()
        body = gf.GetOutput()

    # 面元：Newell 内法向 n、面积 A、质心 x（见模块 docstring）
    areas, nxs, nys, nzs, cxs = [], [], [], [], []
    for i in range(body.GetNumberOfCells()):
        c = body.GetCell(i)
        pts = [np.array(body.GetPoint(c.GetPointId(j))) for j in range(c.GetNumberOfPoints())]
        if len(pts) < 3:
            continue
        nv = np.zeros(3)
        for j in range(len(pts)):
            nv += np.cross(pts[j], pts[(j + 1) % len(pts)])
        a = 0.5 * np.linalg.norm(nv)
        nx, ny, nz = nv / (np.linalg.norm(nv) + 1e-30)
        areas.append(a); nxs.append(nx); nys.append(ny); nzs.append(nz)
        cxs.append(np.mean(pts, axis=0)[0])

    p_arr = body.GetCellData().GetArray("p")
    if p_arr is None:
        print("p 场缺失", file=sys.stderr)
        return 1

    areas, nxs, nys, nzs, cxs, p = map(
        np.array, (areas, nxs, nys, nzs, cxs, v2n(p_arr)))
    cp = p / args.q
    x_min, x_max = cxs.min(), cxs.max()
    span = x_max - x_min

    # 内法向约定下的分区（外法向 = -n）：
    #   front: n.x>0.95 | base: n.x<-0.95 且靠后 | slant: 斜置且 n.z<-0.3 靠后
    #   top: n.z<-0.95 | bottom: n.z>0.95 | side: |n.y|>0.95
    groups = {
        "front(前表面)":  nxs > 0.95,
        "base(基座)":    (nxs < -0.95) & (cxs > x_min + 0.85 * span),
        "slant(斜面)":   (np.abs(nxs) >= 0.15) & (np.abs(nxs) < 0.95)
                         & (nzs < -0.3) & (cxs > x_min + 0.6 * span),
        "top(顶面)":     (nzs < -0.95) & ~(np.abs(nxs) >= 0.15),
        "bottom(底面)":  nzs > 0.95,
        "side(侧面)":    np.abs(nys) > 0.95,
    }
    used = np.zeros(len(areas), bool)
    print(f"{'分区':<14}{'面积m2':>9}{'Cp均值':>9}{'Cd_r贡献':>10}")
    tot = 0.0
    for name, m in groups.items():
        m = m & ~used
        used |= m
        if m.sum() == 0:
            print(f"{name:<14}{0:>9.4f}{float('nan'):>9.4f}{0.0:>+10.4f}")
            continue
        a = areas[m]
        cpw = np.average(cp[m], weights=a)
        # 压差阻力贡献：F_x = -∮p·n_outer dA，n_outer=-n（内法向），
        # 故 Cd_r = sum(Cp*A*n.x)/Aref（正号：前表面正压给正阻力贡献）
        contrib = np.sum(cp[m] * a * nxs[m]) / AREF
        tot += contrib
        print(f"{name:<14}{a.sum():>9.4f}{cpw:>9.4f}{contrib:>+10.4f}")
    print(f"\n压差阻力合计 Cd_r ≈ {tot:+.4f}")
    print(f"车身湿面积 {areas.sum():.4f} m2")

    # 求解日志的 Cd 压差/摩擦分解对照
    logs = sorted(case.glob("log.simpleFoam")) + sorted(case.glob("log.pimpleFoam"))
    if logs:
        text = logs[-1].read_text(encoding="utf-8", errors="ignore")
        blocks = re.findall(
            r"Cd:\s*([\d.eE+-]+)\s+([\d.eE+-]+)\s+([\d.eE+-]+)", text)
        if blocks:
            t = blocks[-5:]
            print(f"forceCoeffs 日志: Cd 压差 {sum(float(b[1]) for b in t)/len(t):.4f}"
                  f" + 摩擦 {sum(float(b[2]) for b in t)/len(t):.4f}"
                  f"（尾 {len(t)} 块均值）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
