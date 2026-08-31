from __future__ import annotations
import uuid
from enum import Enum
from pathlib import Path
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict, field_validator, model_validator

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


class ModelAssetManifest(BaseModel):
    """Traceable rights and geometry metadata for a user-supplied vehicle."""

    model_id: str = Field(min_length=1)
    manufacturer: str = Field(min_length=1)
    model: str = Field(min_length=1)
    model_year: Optional[str] = None
    source_url: str = Field(min_length=1)
    source_sha256: str = Field(pattern=r"^[0-9a-fA-F]{64}$")
    license_id: str = Field(min_length=1)
    license_url: Optional[str] = None
    source_format: str = "STL"
    units: str = "m"
    forward_axis: str = "-X"  # vehicle nose points upstream; freestream flows +X
    up_axis: str = "+Z"
    redistribution_allowed: bool = False
    derivatives_allowed: bool = False
    cfd_ready: bool = False
    notes: str = ""

    @field_validator("license_id")
    @classmethod
    def require_known_license(cls, value: str) -> str:
        if value.strip().lower() in {"unknown", "unspecified", "none"}:
            raise ValueError("model asset license must be traceable")
        return value.strip()
class FluidProperties(BaseModel):
    name: str = "air"
    density: float = Field(default=1.225, gt=0)
    kinematic_viscosity: float = Field(default=1.5e-5, gt=0)
class BoundingBox(BaseModel):
    x_min: float; x_max: float; y_min: float; y_max: float; z_min: float; z_max: float

    @model_validator(mode="after")
    def validate_extents(self):
        for axis in ("x", "y", "z"):
            if getattr(self, f"{axis}_max") <= getattr(self, f"{axis}_min"):
                raise ValueError(f"BoundingBox {axis}_max must be greater than {axis}_min")
        return self
class SimulationTask(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    task_id: str = Field(default_factory=lambda: f"task_{uuid.uuid4().hex[:8]}")
    user_prompt: str
    object_name: str = "generic object"
    flow_type: FlowType = FlowType.EXTERNAL_AERODYNAMICS
    velocity: float = Field(default=1.0, gt=0)
    yaw_angle_deg: float = 0.0  # 风向角（偏航）：入口速度矢量绕 z 轴旋转
    regime: Regime = Regime.STEADY
    fluid: FluidProperties = Field(default_factory=FluidProperties)
    geometry_source: GeometrySource = GeometrySource.SEARCH
    upload_stl_path: Optional[Path] = None
class GeometryInfo(BaseModel):
    stl_path: Path; bbox: BoundingBox; characteristic_length: float = Field(gt=0); source: str
    manifest_path: Optional[Path] = None
class MeshReport(BaseModel):
    mesh_path: Path; cell_count: int = 0; max_non_orthogonality: float = 0.0; max_skewness: float = 0.0; passed_checkmesh: bool = False
class ForceCoeffs(BaseModel):
    cd: float; cl: float; cm: Optional[float] = None
    # 压差/摩擦分解（来自求解日志 forceCoeffs 块的 Pressure/Viscous 列；
    # coefficient.dat 的 Cd(f)/Cd(r) 列并非摩擦/压差，见 openfoam_tools）
    cd_pressure: Optional[float] = None; cd_viscous: Optional[float] = None
class SimReport(BaseModel):
    case_dir: Path; converged: bool; final_residuals: dict[str, float] = Field(default_factory=dict); force_coeffs: Optional[ForceCoeffs] = None; flux_error_percent: float = 0.0; runtime_seconds: float = 0.0; notes: list[str] = Field(default_factory=list)
class FinalReport(BaseModel):
    task: SimulationTask; geometry: GeometryInfo; mesh: MeshReport; simulation: SimReport; visualization_paths: list[Path] = Field(default_factory=list); animation_paths: list[Path] = Field(default_factory=list); interactive_paths: list[Path] = Field(default_factory=list); markdown_report_path: Path
    visualization_note: str = ""  # 跳过/失败原因（诚实标注，不静默）
