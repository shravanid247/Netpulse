"""Linux tc/netem hooks. These functions are called by the experiment engine."""
import subprocess

def set_conditions(interface: str, bandwidth_mbps: float, latency_ms: float, packet_loss_pct: float) -> None:
    command = ["tc", "qdisc", "replace", "dev", interface, "root", "netem", "delay", f"{latency_ms}ms", "loss", f"{packet_loss_pct}%", "rate", f"{bandwidth_mbps}mbit"]
    subprocess.run(command, check=True)

def reset_network(interface: str) -> None:
    subprocess.run(["tc", "qdisc", "del", "dev", interface, "root"], check=False)
