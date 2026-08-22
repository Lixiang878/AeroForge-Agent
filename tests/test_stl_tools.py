import struct

from aeroforge.tools.stl_tools import (ahmed_body_stl, is_watertight,
                                       read_stl_bbox, signed_volume,
                                       stl_surface_area)


def test_ahmed_stl_bbox_matches_reference_dimensions(tmp_path):
    out = tmp_path / "ahmed.stl"
    bbox = ahmed_body_stl(out, slant_angle_deg=25.0)
    # Ahmed (1984): L=1.044, W=0.389, H=0.288, G=0.050
    assert abs(bbox.x_max - bbox.x_min - 1.044) < 1e-6
    assert abs(bbox.y_max - bbox.y_min - 0.389) < 1e-6
    assert abs(bbox.z_min - 0.050) < 1e-6
    assert abs(bbox.z_max - (0.050 + 0.288)) < 1e-6
    assert bbox == read_stl_bbox(out)


def test_ahmed_stl_binary_layout_and_surface(tmp_path):
    out = tmp_path / "ahmed.stl"
    ahmed_body_stl(out)
    data = out.read_bytes()
    n_tri = struct.unpack("<I", data[80:84])[0]
    # 轮廓 4n+5 点（n=24 圆弧段）：侧扇 2(m-2) + 包面 2m = 4m-4 = 8n+16
    assert n_tri == 8 * 24 + 16
    assert len(data) == 84 + n_tri * 50
    assert is_watertight(out)                # 封闭表面，snappyHexMesh 前提
    assert signed_volume(out) > 0            # 法向一致朝外（体积为正）
    area = stl_surface_area(out)
    assert 1.0 < area < 2.5                  # 含圆角 Ahmed 表面积约 1.6 m2


def test_ascii_stl_bbox(tmp_path):
    out = tmp_path / "tri.stl"
    out.write_text(
        "solid t\nfacet normal 0 0 1\nouter loop\n"
        "vertex 0 0 0\nvertex 1 0 0\nvertex 0 2 3\n"
        "endloop\nendfacet\nendsolid t\n", encoding="ascii")
    bbox = read_stl_bbox(out)
    assert bbox.x_max == 1.0 and bbox.y_max == 2.0 and bbox.z_max == 3.0
