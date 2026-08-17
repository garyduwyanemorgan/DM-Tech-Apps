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
    """Result of checking one parameter against its compliance limit."""
    parameter_key: str
    parameter_name: str
    value: float | None     # None when the parameter was never measured
    unit: str
    limit_display: str
    compliant: bool
    margin_pct: float       # positive = headroom, negative = breach
    risk_level: str         # LOW / MODERATE / HIGH / UNKNOWN
    # False when the lab never reported this parameter. Such a result carries
    # no verdict at all: `compliant` is False only because a bool must hold
    # something, and it must never be read as a breach. Defaulted so existing
    # constructors keep working unchanged.
    measured: bool = True


@dataclass
class AlertState:
    """Current alert status for a lagoon."""
    level: int              # 1-4
    # None when Chl-a was never measured. Deliberately not 0.0: a zero states
    # there is no bloom risk, which is a claim about the water rather than an
    # admission that nobody looked.
    bloom_probability: Optional[float]  # 0-100, or None if unmeasured
    dominant_species: str
    top_drivers: list = field(default_factory=list)
    escalation_reason: Optional[str] = None


@dataclass
class SludgeZone:
    """Sludge measurement for one lagoon zone."""
    zone_name: str
    total_depth_m: float
    sludge_depth_m: float
    last_survey: date

    @property
    def effective_depth_m(self) -> float:
        return self.total_depth_m - self.sludge_depth_m

    @property
    def capacity_loss_pct(self) -> float:
        if self.total_depth_m == 0:
            return 0
        return (self.sludge_depth_m / self.total_depth_m) * 100

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
    """compliance incident record."""
    date: date
    parameter: str
    measured_value: float
    compliance_limit: str
    duration_hours: float
    root_cause: str
    corrective_action: str
    resolution_date: Optional[date] = None

    @property
    def days_to_resolve(self) -> Optional[int]:
        if self.resolution_date:
            return (self.resolution_date - self.date).days
        return None
