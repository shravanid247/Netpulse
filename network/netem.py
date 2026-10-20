"""Linux tc/netem traffic control module for NetPulse.

Constructs and manages real Linux tc/netem queuing disciplines (qdiscs)
for network impairment (bandwidth limit, latency injection, packet loss).
"""
from __future__ import annotations

import logging
import re
import subprocess
from typing import Any

logger = logging.getLogger(__name__)

INTERFACE_REGEX = re.compile(r"^[a-zA-Z0-9_\-\.]{2,16}$")

# Sensible safety limits
MIN_BANDWIDTH_MBPS = 0.01
MAX_BANDWIDTH_MBPS = 10000.0  # 10 Gbps
MIN_LATENCY_MS = 0.0
MAX_LATENCY_MS = 10000.0      # 10 seconds
MIN_LOSS_PCT = 0.0
MAX_LOSS_PCT = 100.0


def validate_interface_name(interface: str) -> None:
    """Validate interface name format to prevent shell injection."""
    if not isinstance(interface, str) or not INTERFACE_REGEX.match(interface):
        raise ValueError(f"Invalid network interface name: '{interface}'")


def validate_impairment_params(
    bandwidth_mbps: float | None = None,
    latency_ms: float | None = None,
    packet_loss_pct: float | None = None,
) -> None:
    """Validate impairment values against allowable ranges."""
    if bandwidth_mbps is not None:
        if not isinstance(bandwidth_mbps, (int, float)) or not (MIN_BANDWIDTH_MBPS <= bandwidth_mbps <= MAX_BANDWIDTH_MBPS):
            raise ValueError(
                f"bandwidth_mbps must be between {MIN_BANDWIDTH_MBPS} and {MAX_BANDWIDTH_MBPS} Mbps (got {bandwidth_mbps})"
            )

    if latency_ms is not None:
        if not isinstance(latency_ms, (int, float)) or not (MIN_LATENCY_MS <= latency_ms <= MAX_LATENCY_MS):
            raise ValueError(
                f"latency_ms must be between {MIN_LATENCY_MS} and {MAX_LATENCY_MS} ms (got {latency_ms})"
            )

    if packet_loss_pct is not None:
        if not isinstance(packet_loss_pct, (int, float)) or not (MIN_LOSS_PCT <= packet_loss_pct <= MAX_LOSS_PCT):
            raise ValueError(
                f"packet_loss_pct must be between {MIN_LOSS_PCT} and {MAX_LOSS_PCT}% (got {packet_loss_pct})"
            )


def build_tc_command(
    interface: str,
    bandwidth_mbps: float | None = None,
    latency_ms: float | None = None,
    packet_loss_pct: float | None = None,
) -> list[str]:
    """Build structured tc command arguments for netem qdisc."""
    validate_interface_name(interface)
    validate_impairment_params(bandwidth_mbps, latency_ms, packet_loss_pct)

    cmd = ["tc", "qdisc", "replace", "dev", interface, "root", "netem"]

    if latency_ms is not None and latency_ms > 0:
        # Round to 2 decimal places if float
        lat_str = f"{latency_ms:.2f}ms" if isinstance(latency_ms, float) else f"{latency_ms}ms"
        cmd.extend(["delay", lat_str])

    if packet_loss_pct is not None and packet_loss_pct > 0:
        loss_str = f"{packet_loss_pct:.2f}%" if isinstance(packet_loss_pct, float) else f"{packet_loss_pct}%"
        cmd.extend(["loss", loss_str])

    if bandwidth_mbps is not None and bandwidth_mbps > 0:
        bw_str = f"{bandwidth_mbps:.2f}mbit" if isinstance(bandwidth_mbps, float) else f"{bandwidth_mbps}mbit"
        cmd.extend(["rate", bw_str])

    return cmd


def set_conditions(
    interface: str,
    bandwidth_mbps: float | None = None,
    latency_ms: float | None = None,
    packet_loss_pct: float | None = None,
) -> None:
    """Apply real tc/netem qdisc impairment to a network interface."""
    cmd = build_tc_command(interface, bandwidth_mbps, latency_ms, packet_loss_pct)
    # If no impairment options were added beyond 'root netem', just return or apply plain netem
    logger.info("Applying tc impairment on %s: %s", interface, " ".join(cmd))
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
    if res.returncode != 0:
        raise RuntimeError(f"Failed to apply tc qdisc on {interface}: {res.stderr.strip() or res.stdout.strip()}")


def reset_network(interface: str) -> None:
    """Remove root qdisc from an interface, restoring normal network behavior."""
    validate_interface_name(interface)
    logger.info("Resetting tc qdisc on %s", interface)
    subprocess.run(
        ["tc", "qdisc", "del", "dev", interface, "root"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )


def get_qdisc_info(interface: str) -> str:
    """Inspect current qdisc configuration on an interface."""
    validate_interface_name(interface)
    res = subprocess.run(
        ["tc", "qdisc", "show", "dev", interface],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    return res.stdout.strip()


def apply_topology_impairment(
    net: Any,
    bandwidth_mbps: float | None = None,
    latency_ms: float | None = None,
    packet_loss_pct: float | None = None,
    interfaces: list[str] | None = None,
) -> list[str]:
    """Apply impairment symmetrically to the inter-switch bottleneck interfaces.

    By default, targets s1-eth2 (s1 -> s2 direction) and s2-eth1 (s2 -> s1 direction).
    """
    target_intfs = interfaces or ["s1-eth2", "s2-eth1"]
    configured: list[str] = []
    for intf in target_intfs:
        set_conditions(
            interface=intf,
            bandwidth_mbps=bandwidth_mbps,
            latency_ms=latency_ms,
            packet_loss_pct=packet_loss_pct,
        )
        configured.append(intf)
    return configured


def reset_topology_impairment(
    net: Any = None,
    interfaces: list[str] | None = None,
) -> None:
    """Reset qdiscs on specified or default inter-switch interfaces."""
    target_intfs = interfaces or ["s1-eth2", "s2-eth1", "h1-eth0", "h2-eth0"]
    for intf in target_intfs:
        try:
            reset_network(intf)
        except Exception as exc:
            logger.warning("Error resetting interface %s: %s", intf, exc)
