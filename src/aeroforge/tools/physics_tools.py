"""Small dependency-free fluid physics calculations."""
from __future__ import annotations


def reynolds_number(rho, velocity, length, mu=None, nu=None):
    if mu is None and nu is None: raise ValueError("provide dynamic viscosity mu or kinematic viscosity nu")
    if mu is not None: return float(rho) * float(velocity) * float(length) / float(mu)
    return float(velocity) * float(length) / float(nu)


def dynamic_pressure(rho, velocity):
    return 0.5 * float(rho) * float(velocity) ** 2


def mach_number(velocity, speed_of_sound=343.0):
    return float(velocity) / float(speed_of_sound)


def cfl_number(velocity, dt, cell_size):
    return abs(float(velocity)) * float(dt) / float(cell_size)


def pressure_coefficient(pressure, reference_pressure=0.0, rho=1.225, velocity=1.0):
    q = dynamic_pressure(rho, velocity)
    if q == 0: raise ValueError("reference velocity must be non-zero")
    return (float(pressure) - float(reference_pressure)) / q


def check_flux_conservation(case_dir):
    """返回求解日志最后一次全局连续性误差百分比；无证据返回 ``None``。"""
    from pathlib import Path
    from .openfoam_tools import parse_continuity_error

    candidates = []
    for log in Path(case_dir).glob('log.*'):
        value = parse_continuity_error(log)
        if value is not None:
            candidates.append((log.stat().st_mtime_ns, value))
    return max(candidates, key=lambda item: item[0])[1] if candidates else None

def check_symmetry(case_dir, tolerance=0.01):
    """对称性需要场数据/积分面证据；当前工具未实现时返回 ``None``。"""
    return None

def flow_metrics(*, rho=1.225, velocity=1.0, length=1.0, mu=1.81e-5, dt=None, cell_size=None, speed_of_sound=343.0):
    result = {"reynolds": reynolds_number(rho, velocity, length, mu=mu), "dynamic_pressure": dynamic_pressure(rho, velocity), "mach": mach_number(velocity, speed_of_sound)}
    if dt is not None and cell_size is not None: result["cfl"] = cfl_number(velocity, dt, cell_size)
    return result
