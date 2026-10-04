"""Real aioquic benchmark server for NetPulse Mininet experiments.

Listens on the Mininet host interface (10.0.0.2:4433) using TLS 1.3 and ALPN netpulse-quic.
Receives benchmark streams, measures transferred byte volumes, sends reception ACKs,
and provides explicit readiness notification.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import signal
import sys
from pathlib import Path

from aioquic.asyncio import QuicConnectionProtocol, serve
from aioquic.quic.configuration import QuicConfiguration
from aioquic.quic.events import QuicEvent, StreamDataReceived


class NetPulseServerProtocol(QuicConnectionProtocol):
    """QUIC server protocol tracking received streams and bytes."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.bytes_received: int = 0

    def quic_event_received(self, event: QuicEvent) -> None:
        if isinstance(event, StreamDataReceived):
            self.bytes_received += len(event.data)
            if event.end_stream:
                ack_payload = f"ACK:{self.bytes_received}".encode("utf-8")
                self._quic.send_stream_data(event.stream_id, ack_payload, end_stream=True)
                self.transmit()


async def run_server(host: str, port: int, cert_file: str, key_file: str, ready_file: str | None = None) -> None:
    cert_path = Path(cert_file).resolve()
    key_path = Path(key_file).resolve()

    if not cert_path.is_file() or not key_path.is_file():
        raise FileNotFoundError(f"TLS credentials missing: cert={cert_path}, key={key_path}")

    config = QuicConfiguration(
        is_client=False,
        alpn_protocols=["netpulse-quic"],
    )
    config.load_cert_chain(certfile=str(cert_path), keyfile=str(key_path))

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except (NotImplementedError, RuntimeError):
            # Non-main thread or unsupported platform
            pass

    server = await serve(
        host=host,
        port=port,
        configuration=config,
        create_protocol=NetPulseServerProtocol,
    )

    # Signal readiness to supervisor
    if ready_file:
        ready_path = Path(ready_file).resolve()
        ready_path.write_text("READY\n", encoding="utf-8")
    print(f"READY {host}:{port}", flush=True)

    try:
        await stop_event.wait()
    finally:
        server.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="NetPulse Real QUIC Benchmark Server")
    parser.add_argument("--host", type=str, default="10.0.0.2")
    parser.add_argument("--port", type=int, default=4433)
    parser.add_argument("--cert", type=str, required=True)
    parser.add_argument("--key", type=str, required=True)
    parser.add_argument("--ready-file", type=str, default=None)

    args = parser.parse_args()

    try:
        asyncio.run(run_server(args.host, args.port, args.cert, args.key, args.ready_file))
    except KeyboardInterrupt:
        pass
    except Exception as exc:
        print(f"Server error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
