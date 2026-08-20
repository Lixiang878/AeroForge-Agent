from aeroforge.tools.case_builder import CaseSpec, build_case, domain_from_bbox
from aeroforge.tools.stl_tools import ahmed_body_stl


def _spec(tmp_path, **kw):
    stl = tmp_path / "ahmed.stl"
    bbox = ahmed_body_stl(stl)
    return CaseSpec(stl_path=stl, surface="body", bbox=bbox, velocity=40.0, **kw)


def test_build_case_creates_full_tree(tmp_path):
    case = build_case(tmp_path / "case", _spec(tmp_path))
    for rel in ("0/U", "0/p", "0/k", "0/omega", "0/nut",
                "constant/transportProperties", "constant/turbulenceProperties",
                "constant/triSurface/body.stl",
                "system/controlDict", "system/fvSchemes", "system/fvSolution",
                "system/blockMeshDict", "system/snappyHexMeshDict",
                "system/surfaceFeatureExtractDict"):
        assert (case / rel).exists(), rel


def test_boundary_conditions_and_force_coeffs(tmp_path):
    case = build_case(tmp_path / "case", _spec(tmp_path))
    u = (case / "0" / "U").read_text(encoding="utf-8")
    assert "fixedValue" in u and "noSlip" in u and "movingWallVelocity" in u
    assert "groundUpstream" in u and "symmetryPlane" in u   # 上游滑移地面
    ctrl = (case / "system" / "controlDict").read_text(encoding="utf-8")
    assert "forceCoeffs" in ctrl and "Aref" in ctrl and "rhoInf" in ctrl
    k = (case / "0" / "k").read_text(encoding="utf-8")
    assert "kqRWallFunction" in k
    assert "[0 2 -2 0 0 0 0]" in k          # 湍动能 m2/s2
    omega = (case / "0" / "omega").read_text(encoding="utf-8")
    assert "omegaWallFunction" in omega
    assert "[0 0 -1 0 0 0 0]" in omega      # 比耗散率 1/s


def test_blockmesh_patches_and_snappy_surface(tmp_path):
    case = build_case(tmp_path / "case", _spec(tmp_path))
    bm = (case / "system" / "blockMeshDict").read_text(encoding="utf-8")
    for patch in ("inlet", "outlet", "ground", "groundUpstream", "top",
                  "sideLow", "sideHigh"):
        assert patch in bm
    assert "symmetryPlane" in bm
    assert "hex (0 1 4 3 6 7 10 9)" in bm    # 双块结构（上游滑移地面）
    sh = (case / "system" / "snappyHexMeshDict").read_text(encoding="utf-8")
    assert "body.stl" in sh and "locationInMesh" in sh and "addLayers" in sh


def test_domain_margins_scale_with_body(tmp_path):
    spec = _spec(tmp_path)
    dom = domain_from_bbox(spec.bbox, spec.margins)
    L = spec.bbox.x_max - spec.bbox.x_min
    # 上游 3L + 下游 6L + 物体
    assert (dom["x_max"] - dom["x_min"]) > 8.9 * L
    assert dom["z_min"] == 0.0
