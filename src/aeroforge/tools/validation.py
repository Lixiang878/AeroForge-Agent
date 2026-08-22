"""基准验证：把计算得到的 Cd 与公开实验值对比。

Ahmed body（Ahmed et al. 1984, SAE 840300, Re ≈ 2.78e6）两个验证角：
- 20° 后窗：附体流动，Cd ≈ 0.197。稳态 RANS 的适用区，作为定量
  通过判据（±10%）。
- 25° 后窗：Cd ≈ 0.285，但处于分离/再附双稳态过渡区；粗网格壁面
  函数稳态 RANS 已知会高估分离、Cd 散布 0.30–0.55+（文献广泛记录），
  作为工程边界如实报告而非通过判据。
超出容差即明确标记“验证未通过”，不做模糊处理。
"""
from __future__ import annotations

from dataclasses import dataclass

__all__ = ["AHMED_CD_REF_25", "AHMED_CD_REF_20", "ahmed_reference",
           "ValidationResult", "compare_cd", "render_validation_markdown"]

AHMED_CD_REF_25 = 0.285
AHMED_CD_REF_20 = 0.197
DEFAULT_TOLERANCE = 0.10


def ahmed_reference(slant_angle_deg: float) -> float:
    """按后窗斜角返回实验参考 Cd（仅支持 20°/25° 两个验证角）。"""
    if abs(slant_angle_deg - 25.0) < 1e-6:
        return AHMED_CD_REF_25
    if abs(slant_angle_deg - 20.0) < 1e-6:
        return AHMED_CD_REF_20
    raise ValueError(f"unsupported slant angle {slant_angle_deg}; use 20 or 25")


@dataclass
class ValidationResult:
    reference: float
    computed: float
    tolerance: float
    deviation_percent: float
    passed: bool
    slant_angle_deg: float = 25.0


def compare_cd(computed: float, reference: float = AHMED_CD_REF_25,
               tolerance: float = DEFAULT_TOLERANCE,
               slant_angle_deg: float = 25.0) -> ValidationResult:
    """计算偏差并判定验证是否通过（相对偏差 ≤ tolerance）。"""
    dev = (computed - reference) / reference
    return ValidationResult(reference=reference, computed=computed,
                            tolerance=tolerance,
                            deviation_percent=round(dev * 100.0, 2),
                            passed=abs(dev) <= tolerance,
                            slant_angle_deg=slant_angle_deg)


def render_validation_markdown(res: ValidationResult, extra: dict | None = None) -> str:
    """生成验证报告 Markdown 文本。"""
    extra = extra or {}
    status = "**通过 ✅**" if res.passed else "**未通过 ❌**"
    angle_note = "" if abs(res.slant_angle_deg - 25.0) < 1e-6 else (
        "（附体流动角，稳态 RANS 适用区）")
    lines = [
        "# AeroForge-Agent 基准验证报告",
        "",
        f"- 基准: Ahmed body {res.slant_angle_deg:g}°（Ahmed et al., 1984, SAE 840300）",
        f"- 参考值 Cd = {res.reference:.4f}（Re ≈ 2.78e6）{angle_note}",
        f"- 计算值 Cd = {res.computed:.4f}",
        f"- 相对偏差: {res.deviation_percent:+.2f}%（容差 ±{res.tolerance * 100:.0f}%）",
        f"- 判定: {status}",
        "",
        "## 算例信息",
    ]
    for k, v in extra.items():
        lines.append(f"- {k}: {v}")
    lines += [
        "",
        "> 诚实边界：本验证为 RANS（k-ω SST）工程流程验证，不等同于 LES/DNS 精度。",
        "> v0.3.0 复核确认：前缘圆角曲率的网格解析度主导压差阻力精度（对照实验链",
        "> 见 docs/VALIDATION.md #9–#12）；25° 工况处于分离双稳态过渡区，稳态 RANS",
        "> 已知高估分离（文献散布 0.30–0.55+），故定量通过判据取 20° 附体角；",
        "> 简化几何（无支腿）为剩余系统偏差来源之一。",
        "",
    ]
    return "\n".join(lines)
