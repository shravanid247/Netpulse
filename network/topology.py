"""Mininet topology for h1 - s1 - s2 - h2.

Isolated virtual network topology for NetPulse experiments.
h1 (10.0.0.1) ---- s1 (OVS standalone) ---- s2 (OVS standalone) ---- h2 (10.0.0.2)
"""
from __future__ import annotations

import logging
import re
import subprocess
from typing import Any

logger = logging.getLogger(__name__)

# Safe identifier pattern for Linux interfaces (<16 chars total)
SAFE_MININET_ID = re.compile(r"^[a-zA-Z0-9_]{1,8}$")


def sanitize_node_id(node_id: str, node_type: str, index: int) -> str:
    """Generate a compact, valid Linux-interface-safe identifier (<= 8 chars).
    
    Ensures that derived interface names like '<id>-eth0' strictly adhere
    to Linux IFNAMSIZ <= 15 chars.
    """
    prefix = "c" if node_type == "client" else "srv" if node_type == "server" else "s"
    clean = re.sub(r"[^a-zA-Z0-9]", "", node_id).lower()
    if 1 <= len(clean) <= 6 and clean[0].isalpha() and SAFE_MININET_ID.match(clean):
        return clean
    return f"{prefix}{index}"


def analyze_topology_path(
    topology_spec: dict[str, Any],
    default_bandwidth: float = 25.0,
    default_latency: float = 45.0,
    default_loss: float = 1.0,
) -> dict[str, Any]:
    """Analyze dynamic topology graph: finds primary client, server, and active path metrics.

    Uses Breadth-First Search (BFS) to identify the shortest path from the first
    reachable client to the first reachable server, aggregating latency, loss, and bottleneck bandwidth.
    """
    nodes = topology_spec.get("nodes", [])
    edges = topology_spec.get("edges", [])

    node_map = {n["id"]: n for n in nodes}
    clients = [n for n in nodes if n.get("type") == "client"]
    servers = [n for n in nodes if n.get("type") == "server"]

    if not clients:
        raise ValueError("Topology must contain at least one client node.")
    if not servers:
        raise ValueError("Topology must contain at least one server node.")

    # Build adjacency list with edge metadata
    adj: dict[str, list[dict[str, Any]]] = {n["id"]: [] for n in nodes}
    for e in edges:
        s, t = e["source"], e["target"]
        if s in adj and t in adj:
            adj[s].append({"target": t, "edge": e})
            adj[t].append({"target": s, "edge": e})

    server_ids = {s["id"] for s in servers}
    shortest_path: list[str] | None = None
    traversed_edges: list[dict[str, Any]] = []

    # BFS from the first client to find shortest path to any server
    for client in clients:
        queue: list[tuple[str, list[str], list[dict[str, Any]]]] = [
            (client["id"], [client["id"]], [])
        ]
        visited = {client["id"]}
        found = False

        while queue:
            curr, path, edge_path = queue.pop(0)
            if curr in server_ids:
                shortest_path = path
                traversed_edges = edge_path
                found = True
                break
            for conn in adj.get(curr, []):
                nxt = conn["target"]
                if nxt not in visited:
                    visited.add(nxt)
                    queue.append((nxt, path + [nxt], edge_path + [conn["edge"]]))
        if found:
            break

    if not shortest_path:
        raise ValueError("No connected path found between any client and server.")

    primary_client = node_map[shortest_path[0]]
    primary_server = node_map[shortest_path[-1]]

    # Compute path-level metrics
    hop_count = max(1, len(shortest_path) - 1)
    switch_count = sum(1 for nid in shortest_path if node_map[nid].get("type") == "switch")

    # Bottleneck bandwidth along the path
    bandwidths = [
        float(e.get("bandwidth_mbps"))
        for e in traversed_edges
        if e.get("bandwidth_mbps") is not None and float(e.get("bandwidth_mbps", 0)) > 0
    ]
    effective_bandwidth = min(bandwidths) if bandwidths else default_bandwidth

    # Cumulative latency (sum of link delays + 1ms per switch transit)
    latencies = [
        float(e.get("latency_ms"))
        for e in traversed_edges
        if e.get("latency_ms") is not None
    ]
    link_latency_sum = sum(latencies) if latencies else default_latency
    switch_transit_delay = switch_count * 1.0
    cumulative_latency = round(link_latency_sum + switch_transit_delay, 2)

    # Compound packet loss: 1 - product(1 - p_i)
    losses = [
        float(e.get("packet_loss_pct"))
        for e in traversed_edges
        if e.get("packet_loss_pct") is not None
    ]
    if losses:
        survival_prob = 1.0
        for l in losses:
            survival_prob *= max(0.0, 1.0 - (l / 100.0))
        compound_loss = round((1.0 - survival_prob) * 100.0, 2)
    else:
        compound_loss = default_loss

    return {
        "client": primary_client,
        "server": primary_server,
        "path_node_ids": shortest_path,
        "path_edges": traversed_edges,
        "hop_count": hop_count,
        "switch_count": switch_count,
        "effective_bandwidth_mbps": effective_bandwidth,
        "cumulative_latency_ms": cumulative_latency,
        "aggregate_loss_pct": compound_loss,
    }


def build_dynamic_topology(topology_spec: dict[str, Any]) -> tuple[Any, dict[str, Any]]:
    """Build a Mininet network dynamically from a validated topology specification."""
    from mininet.net import Mininet
    from mininet.node import OVSSwitch
    from mininet.topo import Topo

    nodes = topology_spec.get("nodes", [])
    edges = topology_spec.get("edges", [])

    # Step 1: Assign sanitized IDs to avoid Linux IFNAMSIZ (>15 chars) overflow
    sanitized_map: dict[str, str] = {}
    reverse_map: dict[str, str] = {}
    counts: dict[str, int] = {"client": 1, "switch": 1, "server": 1}

    for node in nodes:
        ntype = node.get("type", "client")
        short_id = sanitize_node_id(node["id"], ntype, counts.get(ntype, 1))
        while short_id in reverse_map:
            counts[ntype] += 1
            short_id = f"{'c' if ntype == 'client' else 'srv' if ntype == 'server' else 's'}{counts[ntype]}"
        counts[ntype] += 1
        sanitized_map[node["id"]] = short_id
        reverse_map[short_id] = node["id"]

    # Step 2: Assign sequential IPs to hosts (10.0.0.1, 10.0.0.2, ...)
    host_ips: dict[str, str] = {}
    ip_counter = 1
    for node in nodes:
        if node.get("type") in ("client", "server"):
            short_id = sanitized_map[node["id"]]
            host_ips[short_id] = f"10.0.0.{ip_counter}/24"
            ip_counter += 1

    path_analysis = analyze_topology_path(topology_spec)
    primary_client_short = sanitized_map.get(path_analysis["client"]["id"], "c1")
    primary_server_short = sanitized_map.get(path_analysis["server"]["id"], "srv1")
    primary_server_ip = host_ips.get(primary_server_short, "10.0.0.2/24").split("/")[0]

    class DynamicTopo(Topo):
        def build(self) -> None:
            # Add switches (with STP to prevent loops in cycles)
            for node in nodes:
                short_id = sanitized_map[node["id"]]
                ntype = node.get("type")
                if ntype == "switch":
                    self.addSwitch(short_id, cls=OVSSwitch, failMode="standalone", stp=True)
                else:
                    self.addHost(short_id, ip=host_ips[short_id])

            # Add links
            for edge in edges:
                src_short = sanitized_map[edge["source"]]
                dst_short = sanitized_map[edge["target"]]
                self.addLink(src_short, dst_short)

    net = Mininet(
        topo=DynamicTopo(),
        controller=None,
        switch=OVSSwitch,
        autoSetMacs=True,
        autoStaticArp=True,
    )

    metadata = {
        "sanitized_map": sanitized_map,
        "reverse_map": reverse_map,
        "primary_client": primary_client_short,
        "primary_server": primary_server_short,
        "primary_server_ip": primary_server_ip,
        "path_analysis": path_analysis,
        "host_ips": host_ips,
    }
    return net, metadata


def get_dynamic_bottleneck_interfaces(net: Any, metadata: dict[str, Any]) -> list[str]:
    """Resolve the specific interface names for the bottleneck links along the active path."""
    path_nodes = metadata.get("path_analysis", {}).get("path_node_ids", [])
    sanitized_map = metadata.get("sanitized_map", {})
    if len(path_nodes) < 2:
        return []

    # Identify links connecting adjacent nodes on the path
    target_pairs: set[tuple[str, str]] = set()
    for i in range(len(path_nodes) - 1):
        s1 = sanitized_map.get(path_nodes[i], path_nodes[i])
        s2 = sanitized_map.get(path_nodes[i + 1], path_nodes[i + 1])
        target_pairs.add((s1, s2))
        target_pairs.add((s2, s1))

    intfs: list[str] = []
    for link in getattr(net, "links", []):
        try:
            n1 = link.intf1.node.name
            n2 = link.intf2.node.name
            if (n1, n2) in target_pairs:
                intfs.extend([link.intf1.name, link.intf2.name])
        except Exception:
            continue
    return sorted(list(set(intfs)))


def build_topology() -> Any:
    """Instantiate and configure the legacy 2-host, 2-switch Mininet topology."""
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
