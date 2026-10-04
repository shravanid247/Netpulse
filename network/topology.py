"""Mininet topology for h1 - s1 - s2 - h2.

Isolated virtual network topology for NetPulse experiments.
h1 (10.0.0.1) ---- s1 (OVS standalone) ---- s2 (OVS standalone) ---- h2 (10.0.0.2)
"""
from __future__ import annotations

import logging
import subprocess
from typing import Any

logger = logging.getLogger(__name__)


def build_topology() -> Any:
    """Instantiate and configure the 2-host, 2-switch Mininet topology."""
    from mininet.net import Mininet
    from mininet.node import OVSSwitch
    from mininet.topo import Topo

    class NetPulseTopo(Topo):
        def build(self) -> None:
            h1 = self.addHost("h1", ip="10.0.0.1/24")
            h2 = self.addHost("h2", ip="10.0.0.2/24")
            s1 = self.addSwitch("s1", cls=OVSSwitch, failMode="standalone")
            s2 = self.addSwitch("s2", cls=OVSSwitch, failMode="standalone")
            self.addLink(h1, s1)
            self.addLink(s1, s2)
            self.addLink(s2, h2)

    net = Mininet(
        topo=NetPulseTopo(),
        controller=None,
        switch=OVSSwitch,
        autoSetMacs=True,
        autoStaticArp=True,
    )
    return net


def cleanup_topology(net: Any | None = None) -> None:
    """Clean up Mininet network and residual system resources."""
    if net is not None:
        try:
            net.stop()
        except Exception as exc:
            logger.warning("Error during net.stop(): %s", exc)

    # Invoke system mininet cleanup tool (mn -c) to ensure clean interfaces and OVS state
    try:
        subprocess.run(
            ["mn", "-c"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=10,
        )
    except Exception as exc:
        logger.warning("Error running mn -c: %s", exc)


def verify_connectivity(net: Any) -> dict[str, Any]:
    """Test ping connectivity between h1 and h2."""
    h1 = net.get("h1")
    h2 = net.get("h2")
    loss = net.ping(hosts=[h1, h2], timeout="1")
    return {
        "success": loss == 0.0,
        "loss_percent": loss,
        "h1_ip": h1.IP(),
        "h2_ip": h2.IP(),
    }


def get_interswitch_interfaces() -> list[str]:
    """Return standard interface names for the s1 <-> s2 bottleneck link."""
    return ["s1-eth2", "s2-eth1"]


def measure_ping_latency(h1: Any, target_ip: str = "10.0.0.2", count: int = 5) -> dict[str, Any]:
    """Measure real ICMP round-trip latency and packet loss between h1 and target."""
    import re
    cmd = f"ping -c {count} -W 2 {target_ip}"
    raw_output = h1.cmd(cmd)

    loss_match = re.search(r"(\d+(?:\.\d+)?)%\s+packet\s+loss", raw_output)
    rtt_match = re.search(r"rtt\s+min/avg/max/mdev\s*=\s*([\d\.]+)/([\d\.]+)/([\d\.]+)/([\d\.]+)", raw_output)

    loss_pct = float(loss_match.group(1)) if loss_match else 100.0
    avg_rtt_ms = float(rtt_match.group(2)) if rtt_match else 0.0
    min_rtt_ms = float(rtt_match.group(1)) if rtt_match else 0.0
    max_rtt_ms = float(rtt_match.group(3)) if rtt_match else 0.0

    return {
        "success": loss_pct < 100.0,
        "loss_pct": loss_pct,
        "avg_rtt_ms": avg_rtt_ms,
        "min_rtt_ms": min_rtt_ms,
        "max_rtt_ms": max_rtt_ms,
        "raw_output": raw_output.strip(),
    }
