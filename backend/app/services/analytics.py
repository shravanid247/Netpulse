"""Comparative analytics and export service for NetPulse network experiments.

Evaluates performance across TCP, UDP, and QUIC protocols under identical network conditions,
derives research-grade comparison metrics, and generates CSV and JSON export datasets.

Formulas for Derived Metrics:
1. Throughput Efficiency (%):
   throughput_efficiency_pct = (throughput_mbps / bandwidth_mbps) * 100.0
   Measures the fraction of available bottleneck bandwidth utilized by the transport protocol.

2. Throughput Ratio vs TCP:
   throughput_ratio_vs_tcp = throughput_mbps / tcp_throughput_mbps
   Measures relative throughput compared to standard TCP baseline under identical conditions.
   Yields 1.0 for TCP itself; > 1.0 indicates outperforming TCP; < 1.0 indicates lower throughput.

3. Latency Inflation (%):
   latency_inflation_pct = ((latency_ms - target_latency_ms) / target_latency_ms) * 100.0
   Measures the percentage increase in observed latency relative to the configured link latency.

4. CPU Cost per Mbps:
   cpu_cost_per_mbps = cpu_usage_pct / throughput_mbps
   Measures CPU processing overhead per unit of data transferred (lower indicates higher computational efficiency).
"""
from __future__ import annotations

import csv
import io
import json
from typing import Any

from app.db.models import Experiment, Result
from app.models.schemas import (
    ComparisonResponse,
    ComparisonSummary,
    ExperimentRequest,
    ProtocolMetrics,
)


def build_comparison(experiment: Experiment) -> ComparisonResponse:
    """Compute structured protocol comparison metrics from experiment results."""
    try:
        configured_protocols = json.loads(experiment.protocols)
    except Exception:
        configured_protocols = [experiment.protocols]

    config_req = ExperimentRequest(
        protocols=configured_protocols,
        bandwidth_mbps=experiment.bandwidth_mbps,
        latency_ms=experiment.latency_ms,
        packet_loss_pct=experiment.packet_loss_pct,
        duration_sec=experiment.duration_sec,
    )

    results_by_proto: dict[str, Result] = {r.protocol: r for r in experiment.results}
    tcp_result = results_by_proto.get("tcp")
    tcp_throughput = tcp_result.throughput_mbps if (tcp_result and tcp_result.throughput_mbps > 0) else None

    protocol_metrics: dict[str, ProtocolMetrics] = {}

    for proto, result in results_by_proto.items():
        # 1. Throughput Efficiency (%)
        efficiency: float | None = None
        if experiment.bandwidth_mbps > 0:
            efficiency = round((result.throughput_mbps / experiment.bandwidth_mbps) * 100.0, 2)

        # 2. Throughput Ratio vs TCP
        ratio_vs_tcp: float | None = None
        if tcp_throughput is not None and tcp_throughput > 0:
            ratio_vs_tcp = round(result.throughput_mbps / tcp_throughput, 3)

        # 3. Latency Inflation (%)
        latency_inflation: float | None = None
        if experiment.latency_ms > 0:
            latency_inflation = round(
                ((result.latency_ms - experiment.latency_ms) / experiment.latency_ms) * 100.0, 2
            )

        # 4. CPU Cost per Mbps
        cpu_cost: float | None = None
        if result.throughput_mbps > 0:
            cpu_cost = round(result.cpu_usage_pct / result.throughput_mbps, 3)

        protocol_metrics[proto] = ProtocolMetrics(
            protocol=proto,
            throughput_mbps=result.throughput_mbps,
            latency_ms=result.latency_ms,
            jitter_ms=result.jitter_ms,
            packet_loss_pct=result.packet_loss_pct,
            cpu_usage_pct=result.cpu_usage_pct,
            transfer_time_sec=result.transfer_time_sec,
            handshake_success=result.handshake_success,
            throughput_efficiency_pct=efficiency,
            throughput_ratio_vs_tcp=ratio_vs_tcp,
            latency_inflation_pct=latency_inflation,
            cpu_cost_per_mbps=cpu_cost,
        )

    # Calculate summary insights
    fastest_proto: str | None = None
    lowest_lat_proto: str | None = None
    most_cpu_eff_proto: str | None = None

    if protocol_metrics:
        # Fastest protocol
        sorted_by_tput = sorted(protocol_metrics.values(), key=lambda p: p.throughput_mbps, reverse=True)
        if sorted_by_tput and sorted_by_tput[0].throughput_mbps > 0:
            fastest_proto = sorted_by_tput[0].protocol

        # Lowest latency (considering latency > 0)
        with_latency = [p for p in protocol_metrics.values() if p.latency_ms > 0]
        if with_latency:
            lowest_lat_proto = min(with_latency, key=lambda p: p.latency_ms).protocol

        # Most CPU efficient (lowest cpu_cost_per_mbps > 0)
        with_cpu_cost = [p for p in protocol_metrics.values() if p.cpu_cost_per_mbps is not None and p.cpu_cost_per_mbps > 0]
        if with_cpu_cost:
            most_cpu_eff_proto = min(with_cpu_cost, key=lambda p: p.cpu_cost_per_mbps or 999999.0).protocol

    notes: list[str] = []
    if fastest_proto:
        tput = protocol_metrics[fastest_proto].throughput_mbps
        notes.append(f"{fastest_proto.upper()} achieved highest throughput at {tput} Mbps.")

    if "quic" in protocol_metrics and "tcp" in protocol_metrics:
        q_tput = protocol_metrics["quic"].throughput_mbps
        t_tput = protocol_metrics["tcp"].throughput_mbps
        if experiment.packet_loss_pct > 0:
            if q_tput >= t_tput:
                notes.append(
                    f"Under {experiment.packet_loss_pct}% packet loss, QUIC maintained {q_tput} Mbps vs TCP's {t_tput} Mbps."
                )
            else:
                notes.append(
                    f"Under {experiment.packet_loss_pct}% packet loss, TCP achieved {t_tput} Mbps vs QUIC's {q_tput} Mbps."
                )

    if "udp" in protocol_metrics and fastest_proto == "udp":
        notes.append("UDP led raw transmission speed without connection establishment or packet recovery overhead.")

    summary = ComparisonSummary(
        fastest_protocol=fastest_proto,
        lowest_latency_protocol=lowest_lat_proto,
        most_cpu_efficient=most_cpu_eff_proto,
        protocol_count=len(protocol_metrics),
        notes=notes,
    )

    return ComparisonResponse(
        experiment_id=experiment.id,
        status=experiment.status,
        config=config_req,
        protocols=protocol_metrics,
        summary=summary,
    )


def export_experiment_csv(experiment: Experiment, comparison: ComparisonResponse) -> str:
    """Format experiment parameters and comparative protocol metrics as downloadable CSV."""
    output = io.StringIO()
    writer = csv.writer(output)

    # Section 1: Experiment Metadata & Network Configuration
    writer.writerow(["# NetPulse Experiment Research Export"])
    writer.writerow(["Experiment ID", experiment.id])
    writer.writerow(["Status", experiment.status])
    writer.writerow(["Created At", experiment.created_at.isoformat() if experiment.created_at else ""])
    writer.writerow(["Completed At", experiment.completed_at.isoformat() if experiment.completed_at else ""])
    writer.writerow(["Configured Bandwidth (Mbps)", experiment.bandwidth_mbps])
    writer.writerow(["Configured Latency (ms)", experiment.latency_ms])
    writer.writerow(["Configured Packet Loss (%)", experiment.packet_loss_pct])
    writer.writerow(["Configured Duration (s)", experiment.duration_sec])
    writer.writerow([])

    # Section 2: Protocol Benchmark Results & Comparison
    headers = [
        "Protocol",
        "Throughput (Mbps)",
        "Latency (ms)",
        "Jitter (ms)",
        "Packet Loss (%)",
        "CPU Usage (%)",
        "Transfer Time (s)",
        "Handshake Success",
        "Throughput Efficiency (%)",
        "Ratio vs TCP",
        "Latency Inflation (%)",
        "CPU Cost per Mbps",
    ]
    writer.writerow(headers)

    for proto_name, m in comparison.protocols.items():
        writer.writerow([
            m.protocol.upper(),
            m.throughput_mbps,
            m.latency_ms,
            m.jitter_ms if m.jitter_ms is not None else "N/A",
            m.packet_loss_pct,
            m.cpu_usage_pct,
            m.transfer_time_sec,
            m.handshake_success if m.handshake_success is not None else "N/A",
            m.throughput_efficiency_pct if m.throughput_efficiency_pct is not None else "N/A",
            m.throughput_ratio_vs_tcp if m.throughput_ratio_vs_tcp is not None else "N/A",
            m.latency_inflation_pct if m.latency_inflation_pct is not None else "N/A",
            m.cpu_cost_per_mbps if m.cpu_cost_per_mbps is not None else "N/A",
        ])

    writer.writerow([])
    writer.writerow(["# Research Summary"])
    writer.writerow(["Fastest Protocol", comparison.summary.fastest_protocol or "N/A"])
    writer.writerow(["Lowest Latency Protocol", comparison.summary.lowest_latency_protocol or "N/A"])
    writer.writerow(["Most CPU Efficient Protocol", comparison.summary.most_cpu_efficient or "N/A"])
    for note in comparison.summary.notes:
        writer.writerow(["Note", note])

    return output.getvalue()


def export_experiment_json(experiment: Experiment, comparison: ComparisonResponse) -> dict[str, Any]:
    """Format complete research dataset as a structured JSON object."""
    return {
        "experiment_id": experiment.id,
        "status": experiment.status,
        "created_at": experiment.created_at.isoformat() if experiment.created_at else None,
        "completed_at": experiment.completed_at.isoformat() if experiment.completed_at else None,
        "config": comparison.config.model_dump(),
        "protocols": {p: m.model_dump() for p, m in comparison.protocols.items()},
        "summary": comparison.summary.model_dump(),
        "raw_result_path": experiment.raw_result_path,
        "error": experiment.error,
    }
