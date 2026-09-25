"""QUIC runner seam for an aioquic client/server pair."""
from typing import Any

def run_quic_test(server_ip: str, duration_sec: int) -> dict[str, Any]:
    return {"protocol": "quic", "server_ip": server_ip, "duration_sec": duration_sec, "runner": "aioquic"}
