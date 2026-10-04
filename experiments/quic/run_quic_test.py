"""Real QUIC test runner using aioquic inside Mininet host namespaces.

Orchestrates ephemeral TLS certificate generation, launches the QUIC benchmark server
in the server host namespace (h2), launches the QUIC client in the client host namespace (h1),
collects metrics (throughput, latency, transfer time, CPU, handshake success),
and ensures complete process and certificate cleanup.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from experiments.quic.certs import generate_ephemeral_certificate

logger = logging.getLogger(__name__)


def get_python_interpreter() -> str:
    """Resolve Python interpreter possessing aioquic and project dependencies."""
    project_root = Path(__file__).resolve().parents[2]
    venv_python = project_root / "backend" / ".venv" / "bin" / "python"
    if venv_python.is_file() and os.access(venv_python, os.X_OK):
        return str(venv_python)
    return sys.executable


def _get_cli_arg(arg_name: str, default: float = 0.0) -> float:
    try:
        if arg_name in sys.argv:
            idx = sys.argv.index(arg_name)
            if idx + 1 < len(sys.argv):
                return float(sys.argv[idx + 1])
    except (ValueError, IndexError):
        pass
    return default


def run_quic_test(
    server_host: Any,
    client_host: Any,
    server_ip: str = "10.0.0.2",
    duration_sec: int = 5,
    bandwidth_mbps: float = 100.0,
    port: int = 4433,
) -> dict[str, Any]:
    """Run real QUIC benchmark between Mininet hosts h1 (client) and h2 (server)."""
    # Terminate any lingering QUIC processes
    server_host.cmd("pkill -9 -f quic_server.py 2>/dev/null || true")
    client_host.cmd("pkill -9 -f quic_client.py 2>/dev/null || true")
    time.sleep(0.5)

    python_bin = get_python_interpreter()
    script_dir = Path(__file__).resolve().parent
    server_script = script_dir / "quic_server.py"
    client_script = script_dir / "quic_client.py"

    cfg_loss = _get_cli_arg("--packet-loss", 0.0)
    cfg_lat = _get_cli_arg("--latency", 0.0)

    ephemeral = generate_ephemeral_certificate(server_ip=server_ip)
    ready_file = ephemeral.cert_path.parent / "server_ready.txt"

    server_cmd = [
        python_bin,
        str(server_script),
        "--host", server_ip,
        "--port", str(port),
        "--cert", str(ephemeral.cert_path),
        "--key", str(ephemeral.key_path),
        "--ready-file", str(ready_file),
    ]

    server_proc = server_host.popen(
        server_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    # Wait for server socket readiness
    ready = False
    for _ in range(50):
        if ready_file.is_file():
            ready = True
            break
        if server_proc.poll() is not None:
            _, server_err = server_proc.communicate()
            ephemeral.cleanup()
            raise RuntimeError(f"QUIC server terminated prematurely: {server_err}")
        time.sleep(0.1)

    if not ready:
        try:
            server_proc.kill()
        except Exception:
            pass
        ephemeral.cleanup()
        raise TimeoutError("QUIC server failed to signal readiness within 5 seconds")

    client_cmd = [
        python_bin,
        str(client_script),
        "--host", server_ip,
        "--port", str(port),
        "--cert", str(ephemeral.cert_path),
        "--duration", str(duration_sec),
        "--bandwidth", str(bandwidth_mbps),
        "--latency", str(cfg_lat),
        "--packet-loss", str(cfg_loss),
        "--server-name", server_ip,
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
        try:
            server_proc.terminate()
            server_proc.wait(timeout=4)
        except subprocess.TimeoutExpired:
            server_proc.kill()
        except Exception:
            pass
        ephemeral.cleanup()

    if not client_stdout.strip():
        raise RuntimeError(f"QUIC client produced no output (exit code {client_proc.returncode}): {client_stderr}")

    try:
        data = json.loads(client_stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Failed to parse QUIC client JSON output: {exc}\nRaw: {client_stdout[:500]}")

    if data.get("error") and not data.get("handshake_success"):
        raise RuntimeError(f"QUIC execution failed: {data['error']}")

    raw_payload = {
        "protocol": "quic",
        "handshake_success": data.get("handshake_success", False),
        "throughput_mbps": data.get("throughput_mbps", 0.0),
        "latency_ms": data.get("latency_ms", 0.0),
        "jitter_ms": data.get("jitter_ms"),
        "packet_loss_pct": None,  # Measured loss unavailable from client; kept null
        "configured_bandwidth_mbps": data.get("configured_bandwidth_mbps", bandwidth_mbps),
        "configured_latency_ms": data.get("configured_latency_ms", cfg_lat),
        "configured_packet_loss_pct": data.get("configured_packet_loss_pct", cfg_loss),
        "cpu_usage_pct": data.get("cpu_usage_pct", 0.0),
        "transfer_time_sec": data.get("transfer_time_sec", float(duration_sec)),
        "bytes_transferred": data.get("bytes_transferred", 0),
        "error": data.get("error"),
    }

    return {
        "protocol": "quic",
        "throughput_mbps": data.get("throughput_mbps", 0.0),
        "latency_ms": data.get("latency_ms", 0.0),
        "jitter_ms": data.get("jitter_ms"),
        "packet_loss_pct": None,
        "configured_bandwidth_mbps": data.get("configured_bandwidth_mbps", bandwidth_mbps),
        "configured_latency_ms": data.get("configured_latency_ms", cfg_lat),
        "configured_packet_loss_pct": data.get("configured_packet_loss_pct", cfg_loss),
        "cpu_usage_pct": data.get("cpu_usage_pct", 0.0),
        "transfer_time_sec": data.get("transfer_time_sec", float(duration_sec)),
        "handshake_success": data.get("handshake_success", False),
        "bytes_transferred": data.get("bytes_transferred", 0),
        "raw_output": json.dumps(raw_payload, indent=2),
    }
