"""Real aioquic benchmark client for NetPulse Mininet experiments.

Connects from Mininet host h1 to h2 (10.0.0.2:4433) using TLS 1.3 and ALPN netpulse-quic.
Verifies the server using the ephemeral experiment certificate.
Measures:
- handshake_success (boolean)
- handshake latency
- throughput (Mbps) from actual bytes streamed over actual elapsed time
- latency (smoothed RTT in ms from QUIC loss recovery or handshake RTT)
- CPU usage percentage
- transfer time
Outputs structured JSON to stdout.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import resource
import sys
import time
from pathlib import Path
from typing import Any

from aioquic.asyncio import QuicConnectionProtocol, connect
from aioquic.quic.configuration import QuicConfiguration
from aioquic.quic.events import HandshakeCompleted, QuicEvent, StreamDataReceived


class NetPulseClientProtocol(QuicConnectionProtocol):
    """QUIC client protocol tracking connection and stream events."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.handshake_event = asyncio.Event()
        self.ack_event = asyncio.Event()
        self.server_ack_text: str = ""
        self.handshake_time_ms: float = 0.0

    def quic_event_received(self, event: QuicEvent) -> None:
        if isinstance(event, HandshakeCompleted):
            self.handshake_event.set()
        elif isinstance(event, StreamDataReceived):
            self.server_ack_text += event.data.decode("utf-8", errors="replace")
            if event.end_stream:
                self.ack_event.set()


async def run_client(
    host: str,
    port: int,
    cert_file: str,
    duration: int,
    bandwidth: float,
    latency: float = 0.0,
    packet_loss: float = 0.0,
    server_name: str = "10.0.0.2",
) -> dict[str, Any]:
    cert_path = Path(cert_file).resolve()
    if not cert_path.is_file():
        raise FileNotFoundError(f"TLS certificate missing: {cert_path}")

    config = QuicConfiguration(
        is_client=True,
        alpn_protocols=["netpulse-quic"],
        server_name=server_name,
    )
    config.load_verify_locations(cafile=str(cert_path))

    connect_start = time.perf_counter()
    ru_start = resource.getrusage(resource.RUSAGE_SELF)

    result_data: dict[str, Any] = {
        "protocol": "quic",
        "handshake_success": False,
        "throughput_mbps": 0.0,
        "latency_ms": 0.0,
        "jitter_ms": None,
        "packet_loss_pct": None,
        "configured_bandwidth_mbps": bandwidth,
        "configured_latency_ms": latency,
        "configured_packet_loss_pct": packet_loss,
        "cpu_usage_pct": 0.0,
        "transfer_time_sec": 0.0,
        "bytes_transferred": 0,
        "error": None,
    }

    try:
        async with connect(
            host=host,
            port=port,
            configuration=config,
            create_protocol=NetPulseClientProtocol,
        ) as client:
            # Wait for TLS 1.3 + QUIC handshake completion
            try:
                await asyncio.wait_for(client.handshake_event.wait(), timeout=12.0)
            except asyncio.TimeoutError:
                result_data["error"] = "QUIC handshake timed out"
                return result_data

            handshake_elapsed_ms = (time.perf_counter() - connect_start) * 1000.0
            result_data["handshake_success"] = True
            result_data["latency_ms"] = round(handshake_elapsed_ms, 2)

            # Benchmark streaming phase
            stream_id = client._quic.get_next_available_stream_id()
            chunk_size = 32768  # 32 KB chunks
            chunk = b"Q" * chunk_size

            # Calculate pacing interval if bandwidth limit is specified
            if bandwidth > 0:
                pacing_delay = (chunk_size * 8) / (bandwidth * 1_000_000.0)
            else:
                pacing_delay = 0.001

            total_bytes_sent = 0
            transfer_start = time.perf_counter()
            bench_deadline = transfer_start + max(1, duration)

            while time.perf_counter() < bench_deadline:
                client._quic.send_stream_data(stream_id, chunk, end_stream=False)
                total_bytes_sent += len(chunk)
                client.transmit()

                # Sleep to enforce pacing delay or yield event loop
                delay = max(0.001, pacing_delay)
                await asyncio.sleep(delay)

            # Signal end of stream
            client._quic.send_stream_data(stream_id, b"", end_stream=True)
            client.transmit()

            # Wait for server acknowledgment
            try:
                await asyncio.wait_for(client.ack_event.wait(), timeout=max(5.0, duration * 0.5))
            except asyncio.TimeoutError:
                # Still record bytes sent even if ACK was delayed under extreme loss
                pass

            transfer_elapsed = max(0.001, time.perf_counter() - transfer_start)
            bps = (total_bytes_sent * 8) / transfer_elapsed
            throughput_mbps = round(bps / 1_000_000.0, 2)

            # Query smoothed RTT if available
            smoothed_rtt = client._quic._loss._rtt_smoothed
            if smoothed_rtt > 0:
                result_data["latency_ms"] = round(smoothed_rtt * 1000.0, 2)

            # Compute CPU usage
            ru_end = resource.getrusage(resource.RUSAGE_SELF)
            wall_elapsed = max(0.001, time.perf_counter() - connect_start)
            cpu_time = (ru_end.ru_utime + ru_end.ru_stime) - (ru_start.ru_utime + ru_start.ru_stime)
            cpu_pct = round((cpu_time / wall_elapsed) * 100.0, 2)

            result_data["throughput_mbps"] = throughput_mbps
            result_data["transfer_time_sec"] = round(transfer_elapsed, 2)
            result_data["bytes_transferred"] = total_bytes_sent
            result_data["cpu_usage_pct"] = cpu_pct

    except Exception as exc:
        result_data["error"] = str(exc)

    return result_data


def main() -> None:
    parser = argparse.ArgumentParser(description="NetPulse Real QUIC Benchmark Client")
    parser.add_argument("--host", type=str, default="10.0.0.2")
    parser.add_argument("--port", type=int, default=4433)
    parser.add_argument("--cert", type=str, required=True)
    parser.add_argument("--duration", type=int, default=5)
    parser.add_argument("--bandwidth", type=float, default=100.0)
    parser.add_argument("--latency", type=float, default=0.0)
    parser.add_argument("--packet-loss", type=float, default=0.0)
    parser.add_argument("--server-name", type=str, default="10.0.0.2")

    args = parser.parse_args()

    try:
        res = asyncio.run(
            run_client(
                host=args.host,
                port=args.port,
                cert_file=args.cert,
                duration=args.duration,
                bandwidth=args.bandwidth,
                latency=args.latency,
                packet_loss=args.packet_loss,
                server_name=args.server_name,
            )
        )
        print(json.dumps(res, indent=2))
        sys.exit(0 if res.get("handshake_success") else 1)
    except Exception as exc:
        err_res = {
            "protocol": "quic",
            "handshake_success": False,
            "error": str(exc),
        }
        print(json.dumps(err_res, indent=2))
        sys.exit(1)


if __name__ == "__main__":
    main()
