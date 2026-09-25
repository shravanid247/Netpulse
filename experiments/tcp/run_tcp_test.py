"""TCP runner seam. Replace the simulated call with iperf3 on a Mininet host."""
from typing import Any

def run_tcp_test(server_ip: str, duration_sec: int, bandwidth_mbps: float | None = None) -> dict[str, Any]:
    return {"protocol": "tcp", "server_ip": server_ip, "duration_sec": duration_sec, "requested_bandwidth_mbps": bandwidth_mbps, "runner": "iperf3"}
