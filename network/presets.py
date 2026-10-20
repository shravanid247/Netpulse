"""Predefined network condition presets for NetPulse benchmarks.

Provides standardized impairment profiles representing real-world networks:
- Fiber Broadband (high speed, near-zero loss, low latency)
- Home Broadband / DSL (moderate speed, slight latency)
- Mobile 4G / LTE (moderate speed, variable latency)
- Satellite (high latency, occasional loss)
- Poor / Congested WAN (low bandwidth, elevated latency & loss)
"""
from __future__ import annotations

from typing import Any

PRESETS: dict[str, dict[str, float]] = {
    # Core standard presets
    "excellent": {
        "bandwidth_mbps": 100.0,
        "latency_ms": 8.0,
        "packet_loss_pct": 0.0,
    },
    "average": {
        "bandwidth_mbps": 25.0,
        "latency_ms": 45.0,
        "packet_loss_pct": 1.0,
    },
    "poor": {
        "bandwidth_mbps": 10.0,
        "latency_ms": 100.0,
        "packet_loss_pct": 5.0,
    },
    "very_poor": {
        "bandwidth_mbps": 2.0,
        "latency_ms": 220.0,
        "packet_loss_pct": 12.0,
    },
    # Real-world profile aliases
    "fiber": {
        "bandwidth_mbps": 500.0,
        "latency_ms": 2.0,
        "packet_loss_pct": 0.0,
    },
    "4g_lte": {
        "bandwidth_mbps": 30.0,
        "latency_ms": 50.0,
        "packet_loss_pct": 1.5,
    },
    "satellite": {
        "bandwidth_mbps": 20.0,
        "latency_ms": 600.0,
        "packet_loss_pct": 3.0,
    },
    "lossy_iot": {
        "bandwidth_mbps": 1.0,
        "latency_ms": 150.0,
        "packet_loss_pct": 8.0,
    },
}


def get_preset(name: str) -> dict[str, float]:
    """Retrieve impairment parameters for a given preset name.

    Raises KeyError if the preset name is not recognized.
    """
    key = name.lower().strip()
    if key not in PRESETS:
        available = ", ".join(sorted(PRESETS.keys()))
        raise KeyError(f"Unknown preset '{name}'. Available presets: {available}")
    return dict(PRESETS[key])


def list_presets() -> dict[str, dict[str, float]]:
    """Return all available presets."""
    return {k: dict(v) for k, v in PRESETS.items()}
