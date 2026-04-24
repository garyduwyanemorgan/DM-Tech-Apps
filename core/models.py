"""Domain models — pure data containers, no UI, no IO."""
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Dict, Optional


@dataclass
class WaterReading:
    """Single point-in-time water quality measurement."""
    timestamp: datetime
    ph: float
    do: float           # mg/L
    tss: float          # mg/L
    turbidity: float    # NTU
    cod: float          # mg/L
    ammonia: float      # mg/L
    phosphate: float    # mg/L
    oil_grease: float   # mg/L
    ecoli: float        # CFU/100mL
    total_coliforms: float  # CFU/100mL
    chla: float         # µg/L  (chlorophyll-a)
    phycocyanin: float  # µg/L
    salinity: float     # PSU
    water_temp: float   # °C

    def as_dict(self) -> Dict[str, float]:
        return {
            "ph": self.ph, "do": self.do, "tss": self.tss,
            "turbidity": self.turbidity, "cod": self.cod,
            "ammonia": self.ammonia, "phosphate": self.phosphate,
            "oil_grease": self.oil_grease, "ecoli": self.ecoli,
            "total_coliforms": self.total_coliforms,
        }


@dataclass
class ComplianceResult:
    """Result of checking one parameter against its DECCA limit."""
    parameter_key: str
    parameter_name: str
    value: float
    unit: str
    limit_display: str
    compliant: bool
    margin_pct: float       # positive = headroom, negative = breach
    risk_level: str         # LOW / MODERATE / HIGH


@dataclass
class AlertState:
    """Current alert status for a lagoon."""
    level: int              # 1-4
    bloom_probability: float  # 0-100
    dominant_species: str
    top_drivers: list = field(default_factory=list)
    escalation_reason: Optional[str] = None


@dataclass
class SludgeZone:
    """Sludge measurement for one lagoon zone."""
    zone_name: str
    total_depth_ft: float
    sludge_depth_ft: float
    last_survey: date

    @property
    def effective_depth_ft(self) -> float:
        return self.total_depth_ft - self.sludge_depth_ft

    @property
    def capacity_loss_pct(self) -> float:
        if self.total_depth_ft == 0:
            return 0
        return (self.sludge_depth_ft / self.total_depth_ft) * 100

    @property
    def status(self) -> str:
        pct = self.capacity_loss_pct
        if pct > 30:
            return "CRITICAL"
        if pct > 20:
            return "WARNING"
        return "OK"


@dataclass
class Incident:
    """DECCA compliance incident record."""
    date: date
    parameter: str
    measured_value: float
    decca_limit: str
    duration_hours: float
    root_cause: str
    corrective_action: str
    resolution_date: Optional[date] = None

    @property
    def days_to_resolve(self) -> Optional[int]:
        if self.resolution_date:
            return (self.resolution_date - self.date).days
        return None
