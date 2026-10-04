#!/usr/bin/env python3
"""Root-owned, root-controlled Mininet experiment helper for NetPulse.

Installed at: /usr/local/libexec/netpulse-runner
Ownership: root:root
Permissions: 0755

This tool executes privileged Mininet network namespace, Open vSwitch, and Linux
tc/netem traffic control operations under strict validation, captures raw system
benchmarks (iperf3, ping), and writes the results to a controlled output location.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from mininet.net import Mininet
from mininet.node import OVSSwitch
from mininet.topo import Topo

DEFAULT_RESULTS_DIR = Path("/var/lib/netpulse/results/raw")
SAFE_ID_REGEX = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")
INTERFACE_REGEX = re.compile(r"^[a-zA-Z0-9_\-\.]{2,16}$")

# Inter-switch bottleneck interfaces controlling bidirectional traffic
INTERSWITCH_INTERFACES = ["s1-eth2", "s2-eth1"]


# ==============================================================================
# Validation & tc/netem Traffic Control Helpers
# ==============================================================================

def validate_interface(interface: str) -> None:
    if not isinstance(interface, str) or not INTERFACE_REGEX.match(interface):
        raise ValueError(f"Invalid network interface: '{interface}'")


def build_tc_command(
    interface: str,
    bandwidth_mbps: float | None = None,
    latency_ms: float | None = None,
    packet_loss_pct: float | None = None,
) -> list[str]:
    validate_interface(interface)
    cmd = ["tc", "qdisc", "replace", "dev", interface, "root", "netem"]

    if latency_ms is not None and latency_ms > 0:
        cmd.extend(["delay", f"{latency_ms:.2f}ms"])

    if packet_loss_pct is not None and packet_loss_pct > 0:
        cmd.extend(["loss", f"{packet_loss_pct:.2f}%"])

    if bandwidth_mbps is not None and bandwidth_mbps > 0:
        cmd.extend(["rate", f"{bandwidth_mbps:.2f}mbit"])

    return cmd


def apply_netem(
    interface: str,
    bandwidth_mbps: float | None = None,
    latency_ms: float | None = None,
    packet_loss_pct: float | None = None,
) -> None:
    """Apply tc/netem qdisc to an interface."""
    cmd = build_tc_command(interface, bandwidth_mbps, latency_ms, packet_loss_pct)
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
    if res.returncode != 0:
        raise RuntimeError(f"tc netem error on {interface}: {res.stderr.strip() or res.stdout.strip()}")


def reset_netem(interface: str) -> None:
    """Reset tc qdisc on an interface."""
    validate_interface(interface)
    subprocess.run(
        ["tc", "qdisc", "del", "dev", interface, "root"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )


def show_qdisc(interface: str) -> str:
    """Query current tc qdisc details on an interface."""
    validate_interface(interface)
    res = subprocess.run(
        ["tc", "qdisc", "show", "dev", interface],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    return res.stdout.strip()


def apply_topology_impairment(
    bandwidth_mbps: float | None = None,
    latency_ms: float | None = None,
    packet_loss_pct: float | None = None,
    interfaces: list[str] | None = None,
) -> list[str]:
    """Apply impairment symmetrically across inter-switch link interfaces."""
    target_intfs = interfaces or INTERSWITCH_INTERFACES
    configured = []
    for intf in target_intfs:
        apply_netem(
            interface=intf,
            bandwidth_mbps=bandwidth_mbps,
            latency_ms=latency_ms,
            packet_loss_pct=packet_loss_pct,
        )
        configured.append(intf)
    return configured


def reset_topology_impairment(interfaces: list[str] | None = None) -> None:
    """Remove qdisc impairment from inter-switch link interfaces."""
    target_intfs = interfaces or INTERSWITCH_INTERFACES
    for intf in target_intfs:
        reset_netem(intf)


# ==============================================================================
# Mininet Topology
# ==============================================================================

class NetPulseTopo(Topo):
    """Isolated 2-host, 2-switch virtual network topology."""

    def build(self) -> None:
        h1 = self.addHost("h1", ip="10.0.0.1/24")
        h2 = self.addHost("h2", ip="10.0.0.2/24")
        s1 = self.addSwitch("s1", cls=OVSSwitch, failMode="standalone")
        s2 = self.addSwitch("s2", cls=OVSSwitch, failMode="standalone")
        self.addLink(h1, s1)
        self.addLink(s1, s2)
        self.addLink(s2, h2)


def build_net() -> Mininet:
    return Mininet(
        topo=NetPulseTopo(),
        controller=None,
        switch=OVSSwitch,
        autoSetMacs=True,
        autoStaticArp=True,
    )


def cleanup(net: Mininet | None = None) -> None:
    """Clean up Mininet network and lingering processes."""
    if net is not None:
        try:
            reset_topology_impairment()
        except Exception:
            pass
        try:
            net.stop()
        except Exception:
            pass
    try:
        subprocess.run(["mn", "-c"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    except Exception:
        pass


def measure_ping(h1: Any, target_ip: str = "10.0.0.2", count: int = 5) -> dict[str, Any]:
    """Execute real ICMP ping between h1 and target_ip."""
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


def run_tcp(h1: Any, h2: Any, duration: int, bandwidth: float) -> dict[str, Any]:
    """Execute real TCP test using system iperf3."""
    h2.cmd("killall -9 iperf3 2>/dev/null || true")
    h1.cmd("killall -9 iperf3 2>/dev/null || true")
    time.sleep(0.5)

    server_proc = h2.popen(
        ["iperf3", "-s", "-p", "5201", "-1", "--json"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    time.sleep(0.8)

    client_cmd = ["iperf3", "-c", "10.0.0.2", "-p", "5201", "-t", str(duration), "--json"]
    if bandwidth > 0:
        client_cmd.extend(["-b", f"{bandwidth}M"])

    try:
        client_proc = h1.popen(client_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        stdout, stderr = client_proc.communicate(timeout=max(35, duration + 30))
    finally:
        try:
            server_proc.wait(timeout=4)
        except subprocess.TimeoutExpired:
            server_proc.kill()

    if not stdout.strip():
        raise RuntimeError(f"TCP iperf3 produced no output: {stderr}")

    data = json.loads(stdout)
    if "error" in data:
        raise RuntimeError(f"iperf3 error: {data['error']}")

    end = data.get("end", {})
    sum_rcv = end.get("sum_received", end.get("sum_sent", {}))
    cpu = end.get("cpu_utilization_percent", {})
    bps = sum_rcv.get("bits_per_second", 0.0)

    # Estimate TCP latency from stream RTT if available
    streams = end.get("streams", [])
    tcp_latency = 0.0
    if streams and "sender" in streams[0]:
        tcp_latency = round(streams[0]["sender"].get("mean_rtt", 0.0) / 1000, 2)

    return {
        "protocol": "tcp",
        "throughput_mbps": round(bps / 1_000_000, 2),
        "latency_ms": tcp_latency,
        "jitter_ms": None,
        "packet_loss_pct": 0.0,
        "retransmits": end.get("sum_sent", {}).get("retransmits", 0),
        "cpu_usage_pct": round(cpu.get("host_total", 0.0), 2),
        "transfer_time_sec": round(sum_rcv.get("seconds", float(duration)), 2),
        "handshake_success": True,
        "raw_output": stdout,
    }


def run_udp(h1: Any, h2: Any, duration: int, bandwidth: float) -> dict[str, Any]:
    """Execute real UDP test using system iperf3."""
    h2.cmd("killall -9 iperf3 2>/dev/null || true")
    h1.cmd("killall -9 iperf3 2>/dev/null || true")
    time.sleep(0.6)

    server_proc = h2.popen(
        ["iperf3", "-s", "-p", "5201", "-1", "--json"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    time.sleep(1.2)

    client_cmd = ["iperf3", "-c", "10.0.0.2", "-u", "-b", f"{bandwidth}M", "-p", "5201", "-t", str(duration), "--json"]

    try:
        client_proc = h1.popen(client_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        stdout, stderr = client_proc.communicate(timeout=max(35, duration + 30))
    finally:
        try:
            server_proc.wait(timeout=4)
        except subprocess.TimeoutExpired:
            server_proc.kill()

    if not stdout.strip():
        raise RuntimeError(f"UDP iperf3 produced no output: {stderr}")

    data = json.loads(stdout)
    if "error" in data:
        raise RuntimeError(f"iperf3 UDP error: {data['error']}")

    end = data.get("end", {})
    sum_data = end.get("sum", end.get("sum_received", end.get("sum_sent", {})))
    cpu = end.get("cpu_utilization_percent", {})
    bps = sum_data.get("bits_per_second", 0.0)

    jitter_ms = sum_data.get("jitter_ms", 0.0)
    loss_pct = sum_data.get("lost_percent", 0.0)

    return {
        "protocol": "udp",
        "throughput_mbps": round(bps / 1_000_000, 2),
        "latency_ms": 0.0,
        "jitter_ms": round(float(jitter_ms), 3) if jitter_ms is not None else 0.0,
        "packet_loss_pct": round(float(loss_pct), 2) if loss_pct is not None else 0.0,
        "cpu_usage_pct": round(cpu.get("host_total", 0.0), 2),
        "transfer_time_sec": round(sum_data.get("seconds", float(duration)), 2),
        "handshake_success": None,
        "raw_output": stdout,
    }


def resolve_safe_output_path(output_file: str | None, experiment_id: str, protocol: str) -> Path:
    """Resolve and validate destination output path to prevent directory traversal."""
    if output_file:
        target = Path(output_file).resolve()
        if target.suffix != ".json":
            raise ValueError(f"Output file must have .json extension: {target}")
        if target.parent == Path("/") or str(target).startswith(("/etc", "/bin", "/sbin", "/usr/bin")):
            raise ValueError(f"Output file location forbidden: {target}")
    else:
        target = DEFAULT_RESULTS_DIR / f"{experiment_id}_{protocol}.json"

    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description="NetPulse Privileged Mininet & Traffic Control Helper")
    parser.add_argument("--action", choices=["run", "verify", "cleanup", "ping", "impairment_test"], required=True)
    parser.add_argument("--experiment-id", type=str, default="test_exp")
    parser.add_argument("--protocol", choices=["tcp", "udp"], default="tcp")
    parser.add_argument("--duration", type=int, default=5)
    parser.add_argument("--bandwidth", type=float, default=100.0)
    parser.add_argument("--latency", type=float, default=0.0)
    parser.add_argument("--packet-loss", type=float, default=0.0)
    parser.add_argument("--output-file", type=str, default=None)

    args = parser.parse_args()

    if not SAFE_ID_REGEX.match(args.experiment_id):
        print(json.dumps({"success": False, "error": "Invalid experiment ID format"}), file=sys.stderr)
        sys.exit(1)

    if not (1 <= args.duration <= 3600):
        print(json.dumps({"success": False, "error": "Duration out of bounds (1-3600s)"}), file=sys.stderr)
        sys.exit(1)

    if not (0.01 <= args.bandwidth <= 10000.0):
        print(json.dumps({"success": False, "error": "Bandwidth out of bounds (0.01-10000 Mbps)"}), file=sys.stderr)
        sys.exit(1)

    if not (0.0 <= args.latency <= 10000.0):
        print(json.dumps({"success": False, "error": "Latency out of bounds (0-10000 ms)"}), file=sys.stderr)
        sys.exit(1)

    if not (0.0 <= args.packet_loss <= 100.0):
        print(json.dumps({"success": False, "error": "Packet loss out of bounds (0-100%)"}), file=sys.stderr)
        sys.exit(1)

    if args.action == "cleanup":
        cleanup(None)
        print(json.dumps({"success": True, "action": "cleanup"}))
        sys.exit(0)

    net = None
    try:
        net = build_net()
        net.start()
        h1, h2 = net.get("h1"), net.get("h2")
        s1, s2 = net.get("s1"), net.get("s2")

        if args.action == "verify":
            ping_loss = net.ping(hosts=[h1, h2], timeout="1")
            res = {
                "success": ping_loss == 0.0,
                "action": "verify",
                "ping_loss": ping_loss,
                "nodes": ["h1", "h2", "s1", "s2"],
            }
            print(json.dumps(res, indent=2))
            sys.exit(0 if ping_loss == 0.0 else 1)

        elif args.action == "ping":
            if args.latency > 0 or args.packet_loss > 0 or args.bandwidth < 10000.0:
                apply_topology_impairment(
                    bandwidth_mbps=args.bandwidth,
                    latency_ms=args.latency,
                    packet_loss_pct=args.packet_loss,
                )
            ping_res = measure_ping(h1, target_ip="10.0.0.2", count=5)
            ping_res["action"] = "ping"
            ping_res["target_latency_ms"] = args.latency
            ping_res["target_loss_pct"] = args.packet_loss
            print(json.dumps(ping_res, indent=2))
            sys.exit(0 if ping_res["success"] else 1)

        elif args.action == "impairment_test":
            # Establish baseline ping
            baseline_ping = measure_ping(h1, "10.0.0.2", count=3)
            qdisc_before = {intf: show_qdisc(intf) for intf in INTERSWITCH_INTERFACES}

            # Apply impairment
            apply_topology_impairment(
                bandwidth_mbps=args.bandwidth,
                latency_ms=args.latency,
                packet_loss_pct=args.packet_loss,
            )
            qdisc_impaired = {intf: show_qdisc(intf) for intf in INTERSWITCH_INTERFACES}

            # Measure under impairment
            impaired_ping = measure_ping(h1, "10.0.0.2", count=5)

            # Reset impairment
            reset_topology_impairment()
            qdisc_after = {intf: show_qdisc(intf) for intf in INTERSWITCH_INTERFACES}
            restored_ping = measure_ping(h1, "10.0.0.2", count=3)

            res = {
                "success": True,
                "action": "impairment_test",
                "config": {
                    "bandwidth_mbps": args.bandwidth,
                    "latency_ms": args.latency,
                    "packet_loss_pct": args.packet_loss,
                },
                "qdisc_before": qdisc_before,
                "qdisc_impaired": qdisc_impaired,
                "qdisc_after": qdisc_after,
                "baseline_ping": baseline_ping,
                "impaired_ping": impaired_ping,
                "restored_ping": restored_ping,
            }
            print(json.dumps(res, indent=2))
            sys.exit(0)

        elif args.action == "run":
            # Apply real tc/netem impairment if configured
            apply_topology_impairment(
                bandwidth_mbps=args.bandwidth,
                latency_ms=args.latency,
                packet_loss_pct=args.packet_loss,
            )

            # Measure ICMP RTT for ground-truth latency reporting
            ping_res = measure_ping(h1, "10.0.0.2", count=3)

            if args.protocol == "tcp":
                res = run_tcp(h1, h2, args.duration, args.bandwidth)
            elif args.protocol == "udp":
                res = run_udp(h1, h2, args.duration, args.bandwidth)
            else:
                raise ValueError(f"Unsupported protocol {args.protocol}")

            # If iperf3 did not return latency or returned 0, use measured ICMP RTT
            if res.get("latency_ms", 0.0) == 0.0 and ping_res.get("avg_rtt_ms", 0.0) > 0.0:
                res["latency_ms"] = round(ping_res["avg_rtt_ms"], 2)

            res["target_bandwidth_mbps"] = args.bandwidth
            res["target_latency_ms"] = args.latency
            res["target_packet_loss_pct"] = args.packet_loss
            res["ping_stats"] = ping_res

            raw_path = resolve_safe_output_path(args.output_file, args.experiment_id, args.protocol)
            raw_path.write_text(res.get("raw_output", ""), encoding="utf-8")
            os.chmod(raw_path, 0o644)

            res["raw_output_path"] = str(raw_path)
            res["experiment_id"] = args.experiment_id
            res["success"] = True
            print(json.dumps(res, indent=2))
            sys.exit(0)

    except Exception as exc:
        print(json.dumps({"success": False, "error": str(exc)}), file=sys.stderr)
        sys.exit(1)
    finally:
        cleanup(net)


if __name__ == "__main__":
    main()
