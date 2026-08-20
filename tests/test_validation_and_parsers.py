from aeroforge.tools.validation import (AHMED_CD_REF_25, compare_cd,
                                        render_validation_markdown)
from aeroforge.tools.openfoam_tools import (parse_force_coeffs,
                                            parse_mesh_stats, parse_residuals)


def test_compare_cd_pass_and_fail():
    res_ok = compare_cd(0.29)
    assert res_ok.passed and abs(res_ok.deviation_percent - 1.75) < 0.01
    res_bad = compare_cd(0.35)
    assert not res_bad.passed
    assert res_ok.reference == AHMED_CD_REF_25


def test_validation_markdown_contains_verdict():
    md = render_validation_markdown(compare_cd(0.29), {"网格单元数": 12345})
    assert "通过" in md and "0.2900" in md and "网格单元数: 12345" in md


def test_parse_residuals(tmp_path):
    log = tmp_path / "log.simpleFoam"
    log.write_text(
        "smoothSolver: Solving for Ux, Initial residual = 0.5, Final residual = 1e-3\n"
        "smoothSolver: Solving for p, Initial residual = 0.9, Final residual = 2e-5\n"
        "smoothSolver: Solving for Ux, Initial residual = 0.2, Final residual = 3e-6\n",
        encoding="utf-8")
    r = parse_residuals(log)
    assert r["Ux"] == 3e-6 and r["p"] == 2e-5


def test_parse_force_coeffs_esi_format(tmp_path):
    # ESI OpenFOAM v2412 实际格式：13 列
    # Time Cd Cd_f Cd_r Cl Cl_f Cl_r Cm f_x f_y f_z m_x m_y
    d = tmp_path / "postProcessing" / "forceCoeffs1" / "0"
    d.mkdir(parents=True)
    (d / "coefficient.dat").write_text(
        "# Force and moment coefficients\n"
        "# dragDir     : (1 0 0)\n"
        "10 0.30 0.15 0.15 -0.02 -0.01 -0.01 0.004 1 0 0 0 0\n"
        "20 0.28 0.14 0.14 0.00 -0.01 0.01 -0.002 1 0 0 0 0\n",
        encoding="utf-8")
    fc = parse_force_coeffs(tmp_path)
    assert fc is not None
    assert abs(fc.cd - 0.29) < 1e-9
    assert abs(fc.cl - (-0.01)) < 1e-9
    assert abs(fc.cm - 0.001) < 1e-9


def test_parse_mesh_stats(tmp_path):
    (tmp_path / "log.checkMesh").write_text(
        "Cells: 456789\nMesh non-orthogonality Max: 51.2\n"
        "Max skewness = 2.3\nMesh OK.\n", encoding="utf-8")
    s = parse_mesh_stats(tmp_path)
    assert s["cell_count"] == 456789
    assert s["max_non_orthogonality"] == 51.2
    assert s["passed_checkmesh"] is True
