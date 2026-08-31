"""STL 工具：包围盒解析（binary/ASCII）与 Ahmed body 参数化生成。

Ahmed body（Ahmed et al., 1984）是汽车外流场 CFD 验证的经典基准：
25° 后窗斜角的公开实验值 Cd ≈ 0.285（Re ≈ 2.78e6）。本模块用纯 Python
生成其简化参数化 STL（无支腿、无圆角），保证验证算例自包含、可复现。
"""
from __future__ import annotations

import math
import os
import struct
import tempfile
from pathlib import Path

from ..core.models import BoundingBox

__all__ = ["read_stl_bbox", "ahmed_body_stl", "stl_surface_area",
           "is_watertight", "signed_volume", "prepare_stl_for_cfd"]

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
    lower = [float("inf")] * 3
    upper = [float("-inf")] * 3
    for triangle in _iter_triangles(p):
        for x, y, z in triangle:
            for index, value in enumerate((x, y, z)):
                lower[index] = min(lower[index], value)
                upper[index] = max(upper[index], value)
    if lower[0] == float("inf"):
        raise ValueError(f"STL has no vertices: {p}")
    return BoundingBox(x_min=lower[0], x_max=upper[0], y_min=lower[1], y_max=upper[1],
                       z_min=lower[2], z_max=upper[2])


def _iter_triangles(path: str | Path):
    """流式读取 ASCII 或 binary STL，并在截断时明确失败。

    真实车辆 STL 常有数百 MB。这里不能先 ``read_bytes`` 再构造全部顶点
    列表，否则封闭性检查会同时保留原始文件、顶点和边表，内存峰值可达
    文件大小的数十倍。
    """
    p = Path(path)
    size = p.stat().st_size
    with p.open("rb") as fh:
        head = fh.read(84)
    if _is_ascii_stl(head, size):
        triangle = []
        with p.open("r", encoding="ascii", errors="ignore") as fh:
            lines = fh
            for line in lines:
                parts = line.split()
                if len(parts) != 4 or parts[0].lower() != "vertex":
                    continue
                try:
                    triangle.append((float(parts[1]), float(parts[2]), float(parts[3])))
                except ValueError as exc:
                    raise ValueError(f"Invalid ASCII STL vertex in {p}") from exc
                if len(triangle) == 3:
                    yield tuple(triangle)
                    triangle.clear()
        if triangle:
            raise ValueError(f"ASCII STL has incomplete triangle in {p}")
        return

    if len(head) < 84:
        raise ValueError(f"Binary STL is truncated: {p}")
    n = struct.unpack("<I", head[80:84])[0]
    expected = 84 + n * 50
    if size < expected:
        raise ValueError(f"Binary STL is truncated: {p}")
    with p.open("rb") as fh:
        fh.seek(84)
        for _ in range(n):
            record = fh.read(50)
            if len(record) != 50:
                raise ValueError(f"Binary STL is truncated: {p}")
            values = struct.unpack("<12fH", record)
            yield (
                tuple(values[3:6]),
                tuple(values[6:9]),
                tuple(values[9:12]),
            )


def prepare_stl_for_cfd(source: str | Path, destination: str | Path, *,
                        target_ground_z: float | None = None,
                        scale: float = 1.0,
                        rotation_z_deg: float = 0.0) -> BoundingBox:
    """把任意 ASCII/binary STL 流式转为单一区域 binary STL。

    转换会保留三角形绕序，重新计算法向，并可统一缩放及把最低点平移到
    ``target_ground_z``，并可绕全局 z 轴旋转以匹配求解器的正 x 来流约定。
    binary STL 不保存多个 ``solid`` 名，因此可避免多零件车辆导入后生成
    未配置的 OpenFOAM patch；当前流程仍把车身、车轮和附件作为一个固定
    壁面，独立旋转车轮需另行扩展 patch 映射。
    """
    src = Path(source)
    dst = Path(destination)
    if src.resolve() == dst.resolve():
        raise ValueError("source and destination STL paths must differ")
    if not math.isfinite(scale) or scale <= 0:
        raise ValueError("STL scale must be positive and finite")
    if not math.isfinite(rotation_z_deg):
        raise ValueError("rotation_z_deg must be finite")
    if target_ground_z is not None and not math.isfinite(target_ground_z):
        raise ValueError("target_ground_z must be finite when provided")

    original_bbox = read_stl_bbox(src)
    z_shift = 0.0 if target_ground_z is None else (
        target_ground_z - scale * original_bbox.z_min
    )
    angle = math.radians(rotation_z_deg)
    cos_a, sin_a = math.cos(angle), math.sin(angle)
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp_handle = tempfile.NamedTemporaryFile(
        mode="w+b", prefix=f".{dst.name}.", suffix=".tmp",
        dir=dst.parent, delete=False,
    )
    tmp_path = Path(tmp_handle.name)
    count = 0
    try:
        with tmp_handle as fh:
            fh.write(b"AeroForge normalized CFD surface".ljust(80, b" "))
            fh.write(struct.pack("<I", 0))
            for triangle in _iter_triangles(src):
                transformed = tuple(
                    (
                        scale * (cos_a * point[0] - sin_a * point[1]),
                        scale * (sin_a * point[0] + cos_a * point[1]),
                        scale * point[2] + z_shift,
                    )
                    for point in triangle
                )
                if not all(math.isfinite(value) for point in transformed for value in point):
                    raise ValueError(f"STL contains non-finite coordinates: {src}")
                a, b, c = transformed
                ux, uy, uz = (b[i] - a[i] for i in range(3))
                vx, vy, vz = (c[i] - a[i] for i in range(3))
                nx = uy * vz - uz * vy
                ny = uz * vx - ux * vz
                nz = ux * vy - uy * vx
                norm = math.sqrt(nx * nx + ny * ny + nz * nz)
                if norm == 0:
                    raise ValueError(f"STL contains a degenerate triangle: {src}")
                fh.write(struct.pack("<fff", nx / norm, ny / norm, nz / norm))
                for point in transformed:
                    fh.write(struct.pack("<fff", *point))
                fh.write(struct.pack("<H", 0))
                count += 1
            if count == 0:
                raise ValueError(f"STL has no triangles: {src}")
            if count > 0xFFFFFFFF:
                raise ValueError(f"STL has too many triangles for binary format: {src}")
            fh.seek(80)
            fh.write(struct.pack("<I", count))
        os.replace(tmp_path, dst)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise
    return read_stl_bbox(dst)


def stl_surface_area(path: str | Path) -> float:
    """计算 ASCII/binary STL 表面积（用于几何合理性检查）。"""
    area = 0.0
    for pts in _iter_triangles(path):
        ax = pts[1][0] - pts[0][0]; ay = pts[1][1] - pts[0][1]; az = pts[1][2] - pts[0][2]
        bx = pts[2][0] - pts[0][0]; by = pts[2][1] - pts[0][1]; bz = pts[2][2] - pts[0][2]
        cx = ay * bz - az * by; cy = az * bx - ax * bz; cz = ax * by - ay * bx
        area += 0.5 * math.sqrt(cx * cx + cy * cy + cz * cz)
    return area


def is_watertight(path: str | Path) -> bool:
    """封闭性检查：每条无向边必须恰好被两个三角形共享（流形表面）。"""
    bbox = read_stl_bbox(path)
    if bbox is None:
        return False
    scale = max(bbox.x_max - bbox.x_min, bbox.y_max - bbox.y_min,
                bbox.z_max - bbox.z_min, 1.0)
    # ASCII STL 常以有限有效数字写出同一顶点；量化避免 0 与
    # -2e-16 这类舍入差异被误判为断边，同时保持相对几何容差很小。
    tolerance = scale * 1e-7

    def vertex_key(point):
        return tuple(round(float(value) / tolerance) for value in point)

    edges: dict[tuple, int] = {}
    for pts in _iter_triangles(path):
        for a, b in ((pts[0], pts[1]), (pts[1], pts[2]), (pts[2], pts[0])):
            ka, kb = vertex_key(a), vertex_key(b)
            key = (ka, kb) if ka <= kb else (kb, ka)
            edges[key] = edges.get(key, 0) + 1
    return bool(edges) and all(c == 2 for c in edges.values())


def signed_volume(path: str | Path) -> float:
    """散度定理计算带符号体积：法向一致朝外时为正（方向一致性检查）。"""
    vol = 0.0
    for a, b, c in _iter_triangles(path):
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
        # 循环移位不会改变绕序；右侧面需要真正反转法向。
        return [(a, c, b) if flip else (a, b, c) for (a, b, c) in tris]

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
