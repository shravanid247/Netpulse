#!/usr/bin/env python3
"""Root-owned, root-controlled Mininet experiment helper for NetPulse.

Installed at: /usr/local/libexec/netpulse-runner
Ownership: root:root
Permissions: 0755

This tool executes privileged Mininet network namespace and Open vSwitch
operations under strict validation, captures raw system iperf3 output,
and writes the results to a controlled output location.
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
            net.stop()
        except Exception:
            pass
    try:
        subprocess.run(["mn", "-c"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    except Exception:
        pass


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
        stdout, stderr = client_proc.communicate(timeout=duration + 15)
    finally:
        try:
            server_proc.wait(timeout=3)
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

    return {
        "protocol": "tcp",
        "throughput_mbps": round(bps / 1_000_000, 2),
        "latency_ms": 0.0,
        "jitter_ms": None,
        "packet_loss_pct": 0.0,
        "retransmits": end.get("sum_sent", {}).get("retransmits", 0),
        "cpu_usage_pct": round(cpu.get("host_total", 0.0), 2),
        "transfer_time_sec": round(sum_rcv.get("seconds", float(duration)), 2),
        "raw_output": stdout,
    }


def run_udp(h1: Any, h2: Any, duration: int, bandwidth: float) -> dict[str, Any]:
    """Execute real UDP test using system iperf3."""
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

    client_cmd = ["iperf3", "-c", "10.0.0.2", "-u", "-b", f"{bandwidth}M", "-p", "5201", "-t", str(duration), "--json"]

    try:
        client_proc = h1.popen(client_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        stdout, stderr = client_proc.communicate(timeout=duration + 15)
    finally:
        try:
            server_proc.wait(timeout=3)
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
    parser = argparse.ArgumentParser(description="NetPulse Privileged Mininet Helper")
    parser.add_argument("--action", choices=["run", "verify", "cleanup"], required=True)
    parser.add_argument("--experiment-id", type=str, default="test_exp")
    parser.add_argument("--protocol", choices=["tcp", "udp"], default="tcp")
    parser.add_argument("--duration", type=int, default=5)
    parser.add_argument("--bandwidth", type=float, default=100.0)
    parser.add_argument("--output-file", type=str, default=None)

    args = parser.parse_args()

    if not SAFE_ID_REGEX.match(args.experiment_id):
        print(json.dumps({"success": False, "error": "Invalid experiment ID format"}), file=sys.stderr)
        sys.exit(1)

    if not (1 <= args.duration <= 3600):
        print(json.dumps({"success": False, "error": "Duration out of bounds (1-3600s)"}), file=sys.stderr)
        sys.exit(1)

    if not (0.1 <= args.bandwidth <= 10000.0):
        print(json.dumps({"success": False, "error": "Bandwidth out of bounds (0.1-10000 Mbps)"}), file=sys.stderr)
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

        elif args.action == "run":
            if args.protocol == "tcp":
                res = run_tcp(h1, h2, args.duration, args.bandwidth)
            elif args.protocol == "udp":
                res = run_udp(h1, h2, args.duration, args.bandwidth)
            else:
                raise ValueError(f"Unsupported protocol {args.protocol}")

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
