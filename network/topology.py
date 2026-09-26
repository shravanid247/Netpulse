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


def get_topology_info(net: Any) -> dict[str, Any]:
    """Return structured host, switch, and link metadata."""
    h1 = net.get("h1")
    h2 = net.get("h2")
    return {
        "hosts": {
            "h1": {"ip": h1.IP(), "intf": h1.defaultIntf().name},
            "h2": {"ip": h2.IP(), "intf": h2.defaultIntf().name},
        },
        "switches": ["s1", "s2"],
        "links": [
            ("h1", "s1"),
            ("s1", "s2"),
            ("s2", "h2"),
        ],
    }
