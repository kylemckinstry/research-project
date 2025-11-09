from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional, Literal, Any


def _maybe_load_yaml(path: Path) -> Optional[dict]:
    try:
        import yaml  # type: ignore

        with path.open("r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except ModuleNotFoundError:  # pragma: no cover - optional dependency
        raise RuntimeError(
            "YAML config requested but PyYAML is not installed. Install pyyaml or use JSON."
        )


def _load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


@dataclass
class Weights:
    manager_weight: float = 1.0
    coffee: float = 1.0
    sandwich: float = 1.0
    speed: float = 0.5
    customer_service: float = 0.5
    fairness_penalty_per_std_above_median: float = 0.25


@dataclass
class HoursCaps:
    max_hours_per_week_per_employee: int = 40


@dataclass
class DefaultShift:
    start: str = "07:00"
    end: str = "15:00"
    duration_hours: int = 8


Weekday = Literal["MON","TUE","WED","THU","FRI","SAT","SUN"]

@dataclass
class DayProfile:
    coffee: float = 1.0
    sandwich: float = 1.0
    speed: float = 1.0
    customer_service: float = 1.0
    threshold: float = 0.70
    traffic: str = "medium"
    primary: str = "Mixed"
    availability: float = 0.80

@dataclass
class DemandConfig:
    weekdays: Dict[Weekday, DayProfile] = field(default_factory=dict)
    overrides: Dict[str, DayProfile] = field(default_factory=dict)


@dataclass
class SchedulerConfig:
    timezone: str = "Australia/Sydney"
    default_shift: DefaultShift = field(default_factory=DefaultShift)
    default_requirements: Dict[str, int] = field(
        default_factory=lambda: {
            "MANAGER": 1,
            "BARISTA": 2,
            "WAITER": 1,
            "SANDWICH": 1,
        }
    )
    overrides: Dict[str, Dict[str, int]] = field(default_factory=dict)
    weekend_requirements: Dict[str, int] = field(default_factory=lambda: {
        "MANAGER": 2,
        "BARISTA": 1,
        "WAITER": 2,
        "SANDWICH": 1,
    })
    hours_caps: HoursCaps = field(default_factory=HoursCaps)
    weights: Weights = field(default_factory=Weights)
    busy_days: list[str] = field(default_factory=lambda: ["Saturday", "Sunday"])  # names
    role_time_windows: Dict[str, dict] = field(default_factory=dict)
    hours_policy: Dict[str, Dict[str, float]] = field(default_factory=dict)
    hours_penalties: Dict[str, float] = field(default_factory=lambda: {
        "per_hour_below_target": 0.5,
        "per_hour_above_target": 0.75,
    })
    global_hard_cap: Optional[float] = None
    schedule_busy_days_first: bool = False
    reserve_hours_for_weekend: Dict[str, float] = field(default_factory=dict)
    weekend_fallback: Dict[str, dict] = field(default_factory=dict)
    demand: DemandConfig = field(default_factory=DemandConfig)


_WD_FROM_IDX = {0:"MON",1:"TUE",2:"WED",3:"THU",4:"FRI",5:"SAT",6:"SUN"}


def _to_day_profile(d: dict | None) -> DayProfile:
    d = d or {}
    return DayProfile(
        coffee=float(d.get("coffee", 1.0)),
        sandwich=float(d.get("sandwich", 1.0)),
        speed=float(d.get("speed", 1.0)),
        customer_service=float(d.get("customer_service", 1.0)),
        threshold=float(d.get("threshold", 0.70)),
        traffic=str(d.get("traffic", "medium")),
        primary=str(d.get("primary", "Mixed")),
        availability=float(d.get("availability", 0.80)),
    )


def load_config(path: str | Path) -> SchedulerConfig:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    if path.suffix.lower() in {".yaml", ".yml"}:
        raw = _maybe_load_yaml(path)
    elif path.suffix.lower() == ".json":
        raw = _load_json(path)
    else:
        raise ValueError("Unsupported config extension. Use .yaml/.yml or .json")

    # Normalize and validate
    tz = str(raw.get("timezone", "Australia/Sydney"))
    ds = raw.get("default_shift", {})
    default_shift = DefaultShift(
        start=str(ds.get("start", "07:00")),
        end=str(ds.get("end", "15:00")),
        duration_hours=int(ds.get("duration_hours", 8)),
    )
    default_requirements = {
        k.upper(): int(v) for k, v in (raw.get("default_requirements") or {}).items()
    } or {
        "MANAGER": 1,
        "BARISTA": 2,
        "WAITER": 1,
        "SANDWICH": 1,
    }
    overrides_in = raw.get("overrides") or {}
    overrides: Dict[str, Dict[str, int]] = {}
    for date_str, role_map in overrides_in.items():
        overrides[date_str] = {k.upper(): int(v) for k, v in (role_map or {}).items()}
    
    weekend_requirements = {
        k.upper(): int(v) for k, v in (raw.get("weekend_requirements") or {}).items()
    } or {
        "MANAGER": 2,
        "BARISTA": 1,
        "WAITER": 2,
        "SANDWICH": 1,
    }

    hc = raw.get("hours_caps", {})
    hours_caps = HoursCaps(
        max_hours_per_week_per_employee=int(
            hc.get("max_hours_per_week_per_employee", 40)
        )
    )

    w = raw.get("weights", {})
    weights = Weights(
        manager_weight=float(w.get("manager_weight", 1.0)),
        coffee=float(w.get("coffee", 1.0)),
        sandwich=float(w.get("sandwich", 1.0)),
        speed=float(w.get("speed", 0.5)),
        customer_service=float(w.get("customer_service", 0.5)),
        fairness_penalty_per_std_above_median=float(
            w.get("fairness_penalty_per_std_above_median", 0.25)
        ),
    )

    busy_days = list(raw.get("busy_days", ["Saturday", "Sunday"]))
    role_time_windows = raw.get("role_time_windows", {})
    hours_policy = raw.get("hours_policy", {})
    hours_penalties = raw.get("hours_penalties", {
        "per_hour_below_target": 0.5,
        "per_hour_above_target": 0.75,
    })
    global_hard_cap = raw.get("global_hard_cap")
    schedule_busy_days_first = bool(raw.get("schedule_busy_days_first", False))
    reserve_hours_for_weekend = raw.get("reserve_hours_for_weekend", {})
    weekend_fallback = raw.get("weekend_fallback", {})

    dem_raw: dict = raw.get("demand") or {}
    wk_raw: dict = dem_raw.get("weekdays") or {}
    default_weekdays: Dict[Weekday, DayProfile] = {
        "MON": DayProfile(),
        "TUE": DayProfile(),
        "WED": DayProfile(),
        "THU": DayProfile(),
        "FRI": DayProfile(traffic="high", coffee=1.3, speed=1.1, threshold=0.75, availability=0.90, primary="Coffee"),
        "SAT": DayProfile(traffic="high", coffee=1.4, sandwich=1.1, speed=1.1, threshold=0.75, availability=0.95, primary="Coffee"),
        "SUN": DayProfile(traffic="medium", coffee=1.2, customer_service=1.1, threshold=0.70, availability=0.85, primary="Coffee"),
    }
    weekdays: Dict[Weekday, DayProfile] = {}
    for k, v in default_weekdays.items():
        supplied = wk_raw.get(k) or wk_raw.get(k.capitalize()) or wk_raw.get(k.title())
        weekdays[k] = _to_day_profile(supplied) if supplied is not None else v
    ov_raw: dict = dem_raw.get("overrides") or {}
    ov: Dict[str, DayProfile] = { str(d): _to_day_profile(p) for d, p in ov_raw.items() }
    demand = DemandConfig(weekdays=weekdays, overrides=ov)

    cfg = SchedulerConfig(
        timezone=tz,
        default_shift=default_shift,
        default_requirements=default_requirements,
        overrides=overrides,
        hours_caps=hours_caps,
        weights=weights,
        busy_days=busy_days,
        role_time_windows=role_time_windows,
        hours_policy=hours_policy,
        hours_penalties=hours_penalties,
        global_hard_cap=global_hard_cap,
        schedule_busy_days_first=schedule_busy_days_first,
        reserve_hours_for_weekend=reserve_hours_for_weekend,
        weekend_fallback=weekend_fallback,
        weekend_requirements=weekend_requirements,
        demand=demand,
    )
    _validate_config(cfg)
    return cfg


def _validate_config(cfg: SchedulerConfig) -> None:
    if cfg.default_shift.duration_hours <= 0:
        raise ValueError("default_shift.duration_hours must be positive")
    if cfg.default_shift.start >= cfg.default_shift.end:
        raise ValueError("default_shift.start must be before default_shift.end")
    for role, count in cfg.default_requirements.items():
        if count < 0:
            raise ValueError(f"default_requirements for role {role} must be >= 0")
    for date_str, role_map in cfg.overrides.items():
        for role, count in role_map.items():
            if count < 0:
                raise ValueError(
                    f"override {date_str} role {role} requirement must be >= 0"
                )
    if cfg.hours_caps.max_hours_per_week_per_employee <= 0:
        raise ValueError("hours_caps.max_hours_per_week_per_employee must be positive")
    if cfg.role_time_windows:
        for role, mapping in cfg.role_time_windows.items():
            if not isinstance(mapping, dict):
                raise ValueError("role_time_windows entries must be dicts per role")
    for role, pol in cfg.hours_policy.items():
        for key in ("target_min", "target_max", "hard_cap"):
            if key not in pol:
                raise ValueError(f"hours_policy for role {role} missing {key}")
        if pol["target_min"] > pol["target_max"]:
            raise ValueError(f"hours_policy target_min > target_max for role {role}")


from datetime import datetime

def resolve_day_profile(cfg: SchedulerConfig, dt: datetime, override: Optional[dict] = None) -> DayProfile:
    if override:
        return _to_day_profile(override)
    wd = _WD_FROM_IDX[dt.weekday()]
    return cfg.demand.weekdays[wd]
