"""STL 工具：包围盒解析（binary/ASCII）与 Ahmed body 参数化生成。

Ahmed body（Ahmed et al., 1984）是汽车外流场 CFD 验证的经典基准：
25° 后窗斜角的公开实验值 Cd ≈ 0.285（Re ≈ 2.78e6）。本模块用纯 Python
生成其简化参数化 STL（无支腿、无圆角），保证验证算例自包含、可复现。
"""
from __future__ import annotations

import math
import struct
from pathlib import Path

from ..core.models import BoundingBox

__all__ = ["read_stl_bbox", "ahmed_body_stl", "stl_surface_area",
           "is_watertight", "signed_volume"]

_ASCII_TOKEN = b"solid"


# ---------------------------------------------------------------- 读取
def _is_ascii_stl(head: bytes, size: int) -> bool:
    if not head.startswith(_ASCII_TOKEN):
        return False
    # binary STL 也可能以 'solid' 开头：用声明三角形数校验
    if size >= 84 and len(head) >= 84:
        n = struct.unpack("<I", head[80:84])[0]
        if size == 84 + n * 50:
            return False
    return True


def read_stl_bbox(path: str | Path) -> BoundingBox:
    """解析 STL 顶点范围（自动识别 ASCII / binary 格式）。"""
    p = Path(path)
    data = p.read_bytes()
    xs: list[float] = []
    ys: list[float] = []
    zs: list[float] = []
    if _is_ascii_stl(data[:84], len(data)):
        for line in data.decode("ascii", errors="ignore").splitlines():
            parts = line.split()
            if len(parts) == 4 and parts[0] == "vertex":
                xs.append(float(parts[1])); ys.append(float(parts[2])); zs.append(float(parts[3]))
    else:
        n = struct.unpack("<I", data[80:84])[0]
        for i in range(n):
            base = 84 + i * 50 + 12  # 跳过法向量，逐顶点 3 float x 3
            for k in range(3):
                x, y, z = struct.unpack("<fff", data[base + k * 12: base + k * 12 + 12])
                xs.append(x); ys.append(y); zs.append(z)
    if not xs:
        raise ValueError(f"STL has no vertices: {p}")
    return BoundingBox(x_min=min(xs), x_max=max(xs), y_min=min(ys), y_max=max(ys),
                       z_min=min(zs), z_max=max(zs))


def stl_surface_area(path: str | Path) -> float:
    """binary STL 表面积（用于几何合理性检查）。"""
    data = Path(path).read_bytes()
    n = struct.unpack("<I", data[80:84])[0]
    area = 0.0
    for i in range(n):
        base = 84 + i * 50 + 12
        pts = [struct.unpack("<fff", data[base + k * 12: base + k * 12 + 12]) for k in range(3)]
        ax = pts[1][0] - pts[0][0]; ay = pts[1][1] - pts[0][1]; az = pts[1][2] - pts[0][2]
        bx = pts[2][0] - pts[0][0]; by = pts[2][1] - pts[0][1]; bz = pts[2][2] - pts[0][2]
        cx = ay * bz - az * by; cy = az * bx - ax * bz; cz = ax * by - ay * bx
        area += 0.5 * math.sqrt(cx * cx + cy * cy + cz * cz)
    return area


def is_watertight(path: str | Path) -> bool:
    """封闭性检查：每条无向边必须恰好被两个三角形共享（流形表面）。"""
    data = Path(path).read_bytes()
    n = struct.unpack("<I", data[80:84])[0]
    edges: dict[tuple, int] = {}
    for i in range(n):
        base = 84 + i * 50 + 12
        pts = [struct.unpack("<fff", data[base + k * 12: base + k * 12 + 12]) for k in range(3)]
        for a, b in ((pts[0], pts[1]), (pts[1], pts[2]), (pts[2], pts[0])):
            key = (a, b) if a <= b else (b, a)
            edges[key] = edges.get(key, 0) + 1
    return all(c == 2 for c in edges.values())


def signed_volume(path: str | Path) -> float:
    """散度定理计算带符号体积：法向一致朝外时为正（方向一致性检查）。"""
    data = Path(path).read_bytes()
    n = struct.unpack("<I", data[80:84])[0]
    vol = 0.0
    for i in range(n):
        base = 84 + i * 50 + 12
        a, b, c = (struct.unpack("<fff", data[base + k * 12: base + k * 12 + 12])
                   for k in range(3))
        vol += (a[0] * (b[1] * c[2] - b[2] * c[1])
                + a[1] * (b[2] * c[0] - b[0] * c[2])
                + a[2] * (b[0] * c[1] - b[1] * c[0])) / 6.0
    return vol


# ---------------------------------------------------------------- Ahmed body
# 原始尺寸（Ahmed et al. 1984, SAE 840300），单位 m
AHMED_DEFAULTS = dict(length=1.044, width=0.389, height=0.288,
                      ground_clearance=0.050, slant_length=0.222)


def ahmed_body_stl(path: str | Path, slant_angle_deg: float = 25.0,
                   length: float | None = None, width: float | None = None,
                   height: float | None = None,
                   ground_clearance: float | None = None,
                   slant_length: float | None = None,
                   nose_top_radius: float = 0.100,
                   nose_bottom_radius: float = 0.050,
                   arc_segments: int = 24) -> BoundingBox:
    """生成 Ahmed body 参数化 STL（binary），返回其包围盒。

    坐标系：x 为来流方向，y 为展向，z 为垂向；底面位于 z=ground_clearance。
    含原始实验几何的关键特征：前鼻圆角（顶部 R100mm / 底部 R50mm）与
    后窗斜面；简化声明：省略支腿。圆角对降低前缘分离、复现实验 Cd
    至关重要（尖角前缘会把 Cd 推到 ~1.0 量级）。
    arc_segments：圆角离散段数。8 段时 R100 圆角每片面片 ~20mm，
    表面网格无法解析曲率，前缘滞止区虚大（Cd 虚高 ~0.2）；
    24 段（默认）配合前缘加密盒可将前缘吸力峰解析出来。
    """
    d = dict(AHMED_DEFAULTS)
    L = length or d["length"]
    W = width or d["width"]
    H = height or d["height"]
    G = ground_clearance or d["ground_clearance"]
    S = slant_length or d["slant_length"]
    ang = math.radians(slant_angle_deg)
    sdx = S * math.cos(ang)   # 斜面水平投影
    sdz = S * math.sin(ang)   # 斜面垂向落差

    rt = min(nose_top_radius, 0.45 * H, 0.25 * L)     # 前鼻上圆角
    rb = min(nose_bottom_radius, 0.45 * H, 0.25 * L)   # 前鼻下圆角
    z_top = G + H
    z_tail = z_top - sdz
    x_slant = L - sdx

    # ---- 侧面轮廓多边形（x,z 平面，CCW），含前鼻圆弧离散
    profile: list[tuple[float, float]] = [
        (rb, G), (L, G), (L, z_tail), (x_slant, z_top), (rt, z_top),
    ]
    # 上圆角：圆心 (rt, z_top-rt)，从 theta=π/2 到 π
    for i in range(1, arc_segments + 1):
        th = math.pi / 2 + i * (math.pi / 2) / arc_segments
        profile.append((rt + rt * math.cos(th), z_top - rt + rt * math.sin(th)))
    profile.append((0.0, G + rb))
    # 下圆角：圆心 (rb, G+rb)，从 theta=π 到 3π/2（终点即首点，不重复）
    for i in range(1, arc_segments):
        th = math.pi + i * (math.pi / 2) / arc_segments
        profile.append((rb + rb * math.cos(th), G + rb + rb * math.sin(th)))

    y0, y1 = -W / 2.0, W / 2.0
    left = [(x, y0, z) for (x, z) in profile]
    right = [(x, y1, z) for (x, z) in profile]

    def fan(pts: list[tuple], flip: bool) -> list[tuple]:
        tris = [(pts[0], pts[i], pts[i + 1]) for i in range(1, len(pts) - 1)]
        return [(b, c, a) if flip else (a, b, c) for (a, b, c) in tris]

    def rect(p1, p2, p3, p4) -> list[tuple]:
        return [(p1, p2, p3), (p1, p3, p4)]

    tris: list[tuple] = []
    tris += fan(left, flip=False)    # 左侧面，外法向 -y
    tris += fan(right, flip=True)    # 右侧面，外法向 +y
    # 环向包面：每条轮廓边 (i -> j) 生成外向四边形（CCW 轮廓 + 此顺序 = 外法向）
    n = len(profile)
    for i in range(n):
        (xi, zi), (xj, zj) = profile[i], profile[(i + 1) % n]
        Li, Lj = (xi, y0, zi), (xj, y0, zj)
        Ri, Rj = (xi, y1, zi), (xj, y1, zj)
        tris += rect(Li, Ri, Rj, Lj)

    _write_binary_stl(path, tris)
    return read_stl_bbox(path)


def _write_binary_stl(path: str | Path, tris: list[tuple]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("wb") as fh:
        fh.write(b"Ahmed body (parametric, AeroForge-Agent)".ljust(80))  # 80B header
        fh.write(struct.pack("<I", len(tris)))
        for (a, b, c) in tris:
            # 法向量由叉积给出
            ax = b[0] - a[0]; ay = b[1] - a[1]; az = b[2] - a[2]
            bx = c[0] - a[0]; by = c[1] - a[1]; bz = c[2] - a[2]
            nx = ay * bz - az * by; ny = az * bx - ax * bz; nz = ax * by - ay * bx
            norm = math.sqrt(nx * nx + ny * ny + nz * nz) or 1.0
            fh.write(struct.pack("<fff", nx / norm, ny / norm, nz / norm))
            for pt in (a, b, c):
                fh.write(struct.pack("<fff", *pt))
            fh.write(struct.pack("<H", 0))
