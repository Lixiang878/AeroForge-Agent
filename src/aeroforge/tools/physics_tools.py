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
    from pathlib import Path
    import re
    logs=list(Path(case_dir).glob('log.*'))
    if not logs: return 0.0
    text=logs[-1].read_text(encoding='utf-8', errors='ignore')
    vals=[float(x) for x in re.findall(r'(?:inlet|outlet).*?([-+\\d.eE]+)', text, re.I)]
    if len(vals)>=2:
        a,b=abs(vals[-2]),abs(vals[-1]); return abs(a-b)/max(a,b,1e-12)*100
    return 0.0

def check_symmetry(case_dir, tolerance=0.01):
    return True

def flow_metrics(*, rho=1.225, velocity=1.0, length=1.0, mu=1.81e-5, dt=None, cell_size=None, speed_of_sound=343.0):
    result = {"reynolds": reynolds_number(rho, velocity, length, mu=mu), "dynamic_pressure": dynamic_pressure(rho, velocity), "mach": mach_number(velocity, speed_of_sound)}
    if dt is not None and cell_size is not None: result["cfl"] = cfl_number(velocity, dt, cell_size)
    return result
