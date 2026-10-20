"""Real TCP test runner using system iperf3 binary.

Executes iperf3 server on server host and client on client host,
captures real JSON metrics, and parses throughput, cpu, and timing.
"""
from __future__ import annotations

import json
import subprocess
import time
from typing import Any

def run_tcp_test(
    server_host: Any,
    client_host: Any,
    server_ip: str = "10.0.0.2",
    duration_sec: int = 10,
    bandwidth_mbps: float | None = None,
    port: int = 5201,
) -> dict[str, Any]:
    """Run real TCP experiment between two Mininet hosts using iperf3."""
    # Ensure any previous iperf3 processes on server and client are stopped
    server_host.cmd("killall -9 iperf3 2>/dev/null || true")
    client_host.cmd("killall -9 iperf3 2>/dev/null || true")
    time.sleep(0.5)

    # Start iperf3 server on server_host in one-off mode (-1)
    server_cmd = ["iperf3", "-s", "-p", str(port), "-1", "--json"]
    server_proc = server_host.popen(
        server_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    time.sleep(0.8)  # Allow server to bind and listen

    # Build client command
    client_cmd = [
        "iperf3",
        "-c", server_ip,
        "-p", str(port),
        "-t", str(duration_sec),
        "--json",
    ]
    if bandwidth_mbps is not None and bandwidth_mbps > 0:
        client_cmd.extend(["-b", f"{bandwidth_mbps}M"])

    client_stdout, client_stderr = "", ""
    try:
        client_proc = client_host.popen(
            client_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        client_stdout, client_stderr = client_proc.communicate(timeout=max(35, duration_sec + 30))
    finally:
        # Ensure server process terminates
        try:
            server_proc.wait(timeout=4)
        except subprocess.TimeoutExpired:
            server_proc.kill()

    if not client_stdout.strip():
        raise RuntimeError(f"iperf3 TCP client failed with no output: {client_stderr}")

    try:
        raw_data = json.loads(client_stdout)
    except json.JSONDecodeError as err:
        raise RuntimeError(f"Failed to parse iperf3 JSON output: {err}\nOutput was: {client_stdout[:500]}")

    if "error" in raw_data:
        raise RuntimeError(f"iperf3 reported error: {raw_data['error']}")

    end_data = raw_data.get("end", {})
    sum_received = end_data.get("sum_received", {})
    sum_sent = end_data.get("sum_sent", {})
    cpu_data = end_data.get("cpu_utilization_percent", {})

    bps = sum_received.get("bits_per_second", sum_sent.get("bits_per_second", 0.0))
    throughput_mbps = round(bps / 1_000_000, 2)
    transfer_time_sec = round(sum_received.get("seconds", sum_sent.get("seconds", float(duration_sec))), 2)
    cpu_usage_pct = round(cpu_data.get("host_total", 0.0), 2)
    retransmits = sum_sent.get("retransmits", 0)

    # Estimate RTT/latency from sender stream if available
    streams = end_data.get("streams", [])
    latency_ms = 0.0
    if streams and "sender" in streams[0]:
        latency_ms = round(streams[0]["sender"].get("mean_rtt", 0.0) / 1000, 2)

    return {
        "protocol": "tcp",
        "throughput_mbps": throughput_mbps,
        "latency_ms": latency_ms,
        "jitter_ms": None,
        "packet_loss_pct": 0.0,
        "retransmits": retransmits,
        "cpu_usage_pct": cpu_usage_pct,
        "transfer_time_sec": transfer_time_sec,
        "handshake_success": True,
        "raw_output": client_stdout,
    }

