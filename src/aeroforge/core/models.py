from __future__ import annotations
import uuid
from enum import Enum
from pathlib import Path
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict

class FlowType(str, Enum):
    EXTERNAL_AERODYNAMICS = "external_aerodynamics"
    INTERNAL_FLOW = "internal_flow"
class Regime(str, Enum):
    STEADY = "steady"
    TRANSIENT = "transient"
class GeometrySource(str, Enum):
    SEARCH = "search"
    PARAMETRIC = "parametric"
    UPLOAD = "upload"
class FluidProperties(BaseModel):
    name: str = "air"
    density: float = 1.225
    kinematic_viscosity: float = 1.5e-5
class BoundingBox(BaseModel):
    x_min: float; x_max: float; y_min: float; y_max: float; z_min: float; z_max: float
class SimulationTask(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    task_id: str = Field(default_factory=lambda: f"task_{uuid.uuid4().hex[:8]}")
    user_prompt: str
    object_name: str = "generic object"
    flow_type: FlowType = FlowType.EXTERNAL_AERODYNAMICS
    velocity: float = 1.0
    regime: Regime = Regime.STEADY
    fluid: FluidProperties = Field(default_factory=FluidProperties)
    geometry_source: GeometrySource = GeometrySource.SEARCH
    upload_stl_path: Optional[Path] = None
class GeometryInfo(BaseModel):
    stl_path: Path; bbox: BoundingBox; characteristic_length: float; source: str
class MeshReport(BaseModel):
    mesh_path: Path; cell_count: int = 0; max_non_orthogonality: float = 0.0; max_skewness: float = 0.0; passed_checkmesh: bool = False
class ForceCoeffs(BaseModel):
    cd: float; cl: float; cm: Optional[float] = None
class SimReport(BaseModel):
    case_dir: Path; converged: bool; final_residuals: dict[str, float] = Field(default_factory=dict); force_coeffs: Optional[ForceCoeffs] = None; flux_error_percent: float = 0.0; runtime_seconds: float = 0.0
class FinalReport(BaseModel):
    task: SimulationTask; geometry: GeometryInfo; mesh: MeshReport; simulation: SimReport; visualization_paths: list[Path] = Field(default_factory=list); markdown_report_path: Path
