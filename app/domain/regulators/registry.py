"""Registry of regulator plugins."""

from __future__ import annotations

from app.domain.regulators.base import RegulatorPlugin
from app.domain.regulators.rbi import RBIRegulatorPlugin
from app.domain.regulators.sebi import SEBIRegulatorPlugin
from app.domain.regulators.stubs import (
    BSEPlugin,
    FDAPlugin,
    IRDAIPlugin,
    MCAPlugin,
    NSEPlugin,
    SECPlugin,
)

_REGISTRY: dict[str, RegulatorPlugin] = {
    "SEBI": SEBIRegulatorPlugin(),
    "RBI": RBIRegulatorPlugin(),
    "NSE": NSEPlugin,
    "BSE": BSEPlugin,
    "MCA": MCAPlugin,
    "IRDAI": IRDAIPlugin,
    "SEC": SECPlugin,
    "FDA": FDAPlugin,
}


def get_regulator(code: str | None = None) -> RegulatorPlugin:
    from app.core.config import get_settings

    key = (code or get_settings().active_regulator or "SEBI").upper()
    if key not in _REGISTRY:
        raise ValueError(f"Unknown regulator: {key}. Available: {list(_REGISTRY)}")
    return _REGISTRY[key]


def list_regulators() -> list[str]:
    return list(_REGISTRY.keys())
