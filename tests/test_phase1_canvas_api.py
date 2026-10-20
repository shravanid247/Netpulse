"""Phase 1 Unit Tests: Canvas API Schema & Simulation Lifecycle Contracts.

Validates:
1. ExperimentRequest schema accepts canvas default parameters.
2. Unique protocol validation and multi-protocol lists from canvas links.
3. Metric snapshots and results formatting without hardcoded mocks.
4. Error handling on invalid parameters.
"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = PROJECT_ROOT / "backend"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import unittest
from pydantic import ValidationError

from app.models.schemas import (
    ExperimentRequest,
    ExperimentResponse,
    MetricSnapshot,
    ResultResponse,
)


class TestPhase1CanvasAPIContracts(unittest.TestCase):
    """Unit tests for Phase 1 canvas-to-backend API contract integrity."""

    def test_canvas_default_payload_valid(self):
        """Verify the payload sent by TopologyCanvas adheres to ExperimentRequest."""
        payload = {
            "protocols": ["quic", "tcp"],
            "bandwidth_mbps": 25.0,
            "latency_ms": 45.0,
            "packet_loss_pct": 1.0,
            "duration_sec": 5,
        }
        req = ExperimentRequest(**payload)
        self.assertEqual(req.protocols, ["quic", "tcp"])
        self.assertEqual(req.bandwidth_mbps, 25.0)
        self.assertEqual(req.latency_ms, 45.0)
        self.assertEqual(req.packet_loss_pct, 1.0)
        self.assertEqual(req.duration_sec, 5)

    def test_canvas_deduplicates_protocols(self):
        """Duplicate protocols extracted from multiple canvas edges are deduplicated."""
        req = ExperimentRequest(
            protocols=["quic", "tcp", "quic"],
            bandwidth_mbps=50.0,
            latency_ms=20.0,
            packet_loss_pct=0.0,
            duration_sec=10,
        )
        self.assertEqual(req.protocols, ["quic", "tcp"])

    def test_canvas_rejects_empty_protocols(self):
        """At least one protocol must be selected."""
        with self.assertRaises(ValidationError):
            ExperimentRequest(
                protocols=[],
                bandwidth_mbps=25.0,
                latency_ms=45.0,
                packet_loss_pct=1.0,
                duration_sec=5,
            )

    def test_result_response_structure_for_inspector(self):
        """Verify ResultResponse contains fields expected by NodeInspector."""
        result = ResultResponse(
            protocol="quic",
            throughput_mbps=24.32,
            latency_ms=45.1,
            jitter_ms=None,
            packet_loss_pct=0.85,
            cpu_usage_pct=16.4,
            transfer_time_sec=5.0,
            handshake_success=True,
        )
        self.assertEqual(result.protocol, "quic")
        self.assertEqual(result.throughput_mbps, 24.32)
        self.assertEqual(result.latency_ms, 45.1)
        self.assertEqual(result.packet_loss_pct, 0.85)

    def test_metric_snapshot_serialization(self):
        """Verify MetricSnapshot model dumps valid dictionary for progress streaming."""
        snapshot = MetricSnapshot(
            experiment_id="EXP-123456",
            protocol="quic",
            elapsed_sec=3.0,
            packets_sent=75000,
            packets_received=74250,
            throughput_mbps=24.1,
            latency_ms=45.0,
            packet_loss_pct=1.0,
        )
        data = snapshot.model_dump()
        self.assertEqual(data["experiment_id"], "EXP-123456")
        self.assertEqual(data["throughput_mbps"], 24.1)


if __name__ == "__main__":
    unittest.main()
