"""Real UDP test runner using system iperf3 binary.

Executes iperf3 server on server host and client on client host with UDP mode (-u),
captures real JSON metrics, and parses throughput, jitter, packet loss, and CPU utilization.
"""
from __future__ import annotations

import json
import subprocess
import time
from typing import Any


def run_udp_test(
    server_host: Any,
    client_host: Any,
    server_ip: str = "10.0.0.2",
    duration_sec: int = 10,
    bandwidth_mbps: float = 10.0,
    port: int = 5201,
) -> dict[str, Any]:
    """Run real UDP experiment between two Mininet hosts using iperf3."""
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

    # Build client UDP command
    # -u specifies UDP mode, -b specifies target bandwidth
    target_bw = max(0.1, float(bandwidth_mbps))
    client_cmd = [
        "iperf3",
        "-c", server_ip,
        "-u",
        "-b", f"{target_bw}M",
        "-p", str(port),
        "-t", str(duration_sec),
        "--json",
    ]

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
        raise RuntimeError(f"iperf3 UDP client failed with no output: {client_stderr}")

    try:
        raw_data = json.loads(client_stdout)
    except json.JSONDecodeError as err:
        raise RuntimeError(f"Failed to parse iperf3 UDP JSON output: {err}\nOutput was: {client_stdout[:500]}")

    if "error" in raw_data:
        raise RuntimeError(f"iperf3 UDP reported error: {raw_data['error']}")

    end_data = raw_data.get("end", {})
    sum_data = end_data.get("sum", {})
    sum_received = end_data.get("sum_received", {})
    sum_sent = end_data.get("sum_sent", {})
    cpu_data = end_data.get("cpu_utilization_percent", {})

    # In UDP iperf3 JSON:
    # `sum` usually contains sender statistics: bits_per_second, lost_percent, jitter_ms (or in streams)
    # `sum_received` or `sum` may contain receiver statistics reported back from server.
    bps = sum_received.get("bits_per_second", sum_data.get("bits_per_second", sum_sent.get("bits_per_second", 0.0)))
    throughput_mbps = round(bps / 1_000_000, 2)
    transfer_time_sec = round(sum_data.get("seconds", sum_sent.get("seconds", float(duration_sec))), 2)
    cpu_usage_pct = round(cpu_data.get("host_total", 0.0), 2)

    # UDP Jitter and Loss
    jitter_ms = sum_data.get("jitter_ms", sum_received.get("jitter_ms"))
    packet_loss_pct = sum_data.get("lost_percent", sum_received.get("lost_percent", 0.0))

    # Check streams if not in sum
    streams = end_data.get("streams", [])
    if streams:
        udp_stream = streams[0].get("udp", {})
        if jitter_ms is None and "jitter_ms" in udp_stream:
            jitter_ms = udp_stream.get("jitter_ms")
        if (packet_loss_pct == 0.0 or packet_loss_pct is None) and "lost_percent" in udp_stream:
            packet_loss_pct = udp_stream.get("lost_percent", 0.0)

    jitter_val = round(float(jitter_ms), 3) if jitter_ms is not None else 0.0
    packet_loss_val = round(float(packet_loss_pct), 2) if packet_loss_pct is not None else 0.0

    return {
        "protocol": "udp",
        "throughput_mbps": throughput_mbps,
        "latency_ms": 0.0,
        "jitter_ms": jitter_val,
        "packet_loss_pct": packet_loss_val,
        "cpu_usage_pct": cpu_usage_pct,
        "transfer_time_sec": transfer_time_sec,
        "handshake_success": None,
        "raw_output": client_stdout,
    }
