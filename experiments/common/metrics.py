from typing import TypedDict

class Metrics(TypedDict):
    protocol: str
    throughput_mbps: float
    latency_ms: float
    jitter_ms: float
    packet_loss_pct: float
    cpu_usage_pct: float

def explain(metrics: Metrics) -> list[str]:
    notes: list[str] = []
    if metrics["packet_loss_pct"] > 3:
        notes.append("Packet loss increased retransmissions, reducing effective throughput.")
    if metrics["latency_ms"] > 100:
        notes.append("Higher latency increased round-trip time and connection overhead.")
    return notes
