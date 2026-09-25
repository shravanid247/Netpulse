"""UDP runner seam. Replace the simulated call with iperf3 -u on a Mininet host."""
from typing import Any

def run_udp_test(server_ip: str, duration_sec: int, bandwidth_mbps: float) -> dict[str, Any]:
    return {"protocol": "udp", "server_ip": server_ip, "duration_sec": duration_sec, "requested_bandwidth_mbps": bandwidth_mbps, "runner": "iperf3 -u"}
