"""Stage 7 Backend Research API & Comparative Analytics Tests.

Verifies:
1. GET /presets returns all verified network condition profiles from network/presets.py.
2. Comparison calculations: throughput efficiency, throughput ratio vs TCP, latency inflation, CPU cost.
3. Handling of missing/null metrics (e.g., when TCP is absent or packet_loss is null).
4. Error handling: 404 for unknown experiment, 400 for invalid experiment ID format.
5. Export endpoints:
   - GET /experiment/export/{id}?format=csv generates valid downloadable CSV.
   - GET /experiment/export/{id}?format=json generates structured research dataset.
6. Raw artifact security:
   - GET /experiment/raw/{id}/{protocol} securely serves raw JSON artifact.
   - Path traversal attempts, invalid protocols, and non-existent artifacts are rejected.
7. Enhanced GET /experiments returns summary metrics while preserving backward compatibility.
8. Multi-protocol experiment execution (TCP + UDP + QUIC) and full comparative analytics flow.
"""
from __future__ import annotations

import csv
import io
import json
import os
import subprocess
import sys
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = PROJECT_ROOT / "backend"
VENV_PYTHON = BACKEND_DIR / ".venv" / "bin" / "python"
RAW_RESULTS_DIR = PROJECT_ROOT / "results" / "raw"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Ensure backend venv dependencies are discoverable when running via system python
for site_pkg in (BACKEND_DIR / ".venv" / "lib").glob("python*/site-packages"):
    if str(site_pkg) not in sys.path:
        sys.path.insert(0, str(site_pkg))

from app.db.models import Experiment, Result
from app.services.analytics import (
    build_comparison,
    export_experiment_csv,
    export_experiment_json,
)
from network.presets import list_presets



def get_python_exe() -> str:
    if VENV_PYTHON.is_file() and os.access(VENV_PYTHON, os.X_OK):
        return str(VENV_PYTHON)
    return sys.executable


def http_request(
    url: str,
    method: str = "GET",
    data: dict | None = None,
    timeout: float = 15.0,
) -> tuple[int, dict | str, dict]:
    headers = {"Content-Type": "application/json", "Accept": "*/*"}
    body = json.dumps(data).encode("utf-8") if data is not None else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            content_type = resp.headers.get("Content-Type", "")
            raw = resp.read().decode("utf-8")
            resp_headers = dict(resp.headers)
            if "application/json" in content_type:
                return resp.status, json.loads(raw) if raw else {}, resp_headers
            return resp.status, raw, resp_headers
    except urllib.error.HTTPError as exc:
        err_body = exc.read().decode("utf-8")
        try:
            parsed = json.loads(err_body)
        except Exception:
            parsed = {"error": err_body}
        return exc.code, parsed, dict(exc.headers)


class TestAnalyticsUnit(unittest.TestCase):
    """Unit tests for comparative analytics formulas and export formatters."""

    def test_analytics_formulas_with_complete_protocols(self) -> None:
        """Verify derived metrics when TCP, UDP, and QUIC are all present."""
        exp = Experiment(
            id="EXP-UNIT01",
            status="COMPLETE",
            protocols=json.dumps(["tcp", "udp", "quic"]),
            bandwidth_mbps=100.0,
            latency_ms=20.0,
            packet_loss_pct=2.0,
            duration_sec=5,
            created_at=datetime.now(timezone.utc),
        )
        r_tcp = Result(
            experiment_id="EXP-UNIT01",
            protocol="tcp",
            throughput_mbps=80.0,
            latency_ms=24.0,
            jitter_ms=None,
            packet_loss_pct=0.0,
            cpu_usage_pct=16.0,
            transfer_time_sec=5.0,
            handshake_success=True,
        )
        r_udp = Result(
            experiment_id="EXP-UNIT01",
            protocol="udp",
            throughput_mbps=95.0,
            latency_ms=20.0,
            jitter_ms=0.5,
            packet_loss_pct=2.1,
            cpu_usage_pct=10.0,
            transfer_time_sec=5.0,
            handshake_success=None,
        )
        r_quic = Result(
            experiment_id="EXP-UNIT01",
            protocol="quic",
            throughput_mbps=88.0,
            latency_ms=22.0,
            jitter_ms=None,
            packet_loss_pct=0.0,
            cpu_usage_pct=22.0,
            transfer_time_sec=5.0,
            handshake_success=True,
        )
        exp.results = [r_tcp, r_udp, r_quic]

        comp = build_comparison(exp)
        self.assertEqual(comp.experiment_id, "EXP-UNIT01")
        self.assertEqual(len(comp.protocols), 3)

        # 1. Throughput Efficiency (%): throughput / bandwidth * 100
        # TCP: 80 / 100 * 100 = 80.0%
        # UDP: 95 / 100 * 100 = 95.0%
        # QUIC: 88 / 100 * 100 = 88.0%
        self.assertEqual(comp.protocols["tcp"].throughput_efficiency_pct, 80.0)
        self.assertEqual(comp.protocols["udp"].throughput_efficiency_pct, 95.0)
        self.assertEqual(comp.protocols["quic"].throughput_efficiency_pct, 88.0)

        # 2. Throughput Ratio vs TCP: throughput / tcp_throughput
        # TCP: 80 / 80 = 1.0
        # UDP: 95 / 80 = 1.188
        # QUIC: 88 / 80 = 1.100
        self.assertEqual(comp.protocols["tcp"].throughput_ratio_vs_tcp, 1.0)
        self.assertEqual(comp.protocols["udp"].throughput_ratio_vs_tcp, 1.188)
        self.assertEqual(comp.protocols["quic"].throughput_ratio_vs_tcp, 1.1)

        # 3. Latency Inflation (%): (latency - target_latency) / target_latency * 100
        # TCP: (24 - 20) / 20 * 100 = 20.0%
        # UDP: (20 - 20) / 20 * 100 = 0.0%
        # QUIC: (22 - 20) / 20 * 100 = 10.0%
        self.assertEqual(comp.protocols["tcp"].latency_inflation_pct, 20.0)
        self.assertEqual(comp.protocols["udp"].latency_inflation_pct, 0.0)
        self.assertEqual(comp.protocols["quic"].latency_inflation_pct, 10.0)

        # 4. CPU Cost per Mbps: cpu_usage / throughput
        # TCP: 16.0 / 80.0 = 0.2
        # UDP: 10.0 / 95.0 = 0.105
        # QUIC: 22.0 / 88.0 = 0.25
        self.assertEqual(comp.protocols["tcp"].cpu_cost_per_mbps, 0.2)
        self.assertEqual(comp.protocols["udp"].cpu_cost_per_mbps, 0.105)
        self.assertEqual(comp.protocols["quic"].cpu_cost_per_mbps, 0.25)

        # Summary
        self.assertEqual(comp.summary.fastest_protocol, "udp")
        self.assertEqual(comp.summary.lowest_latency_protocol, "udp")
        self.assertEqual(comp.summary.most_cpu_efficient, "udp")
        self.assertGreater(len(comp.summary.notes), 0)

    def test_analytics_formulas_with_missing_tcp_and_zero_latency(self) -> None:
        """Verify graceful null handling when TCP is absent and target latency is 0."""
        exp = Experiment(
            id="EXP-UNIT02",
            status="COMPLETE",
            protocols=json.dumps(["quic"]),
            bandwidth_mbps=50.0,
            latency_ms=0.0,
            packet_loss_pct=0.0,
            duration_sec=3,
        )
        r_quic = Result(
            experiment_id="EXP-UNIT02",
            protocol="quic",
            throughput_mbps=45.0,
            latency_ms=4.0,
            jitter_ms=None,
            packet_loss_pct=0.0,
            cpu_usage_pct=15.0,
            transfer_time_sec=3.0,
            handshake_success=True,
        )
        exp.results = [r_quic]

        comp = build_comparison(exp)
        # Ratio vs TCP should be None because TCP was not evaluated
        self.assertIsNone(comp.protocols["quic"].throughput_ratio_vs_tcp)
        # Latency inflation should be None because baseline latency was 0
        self.assertIsNone(comp.protocols["quic"].latency_inflation_pct)
        # Throughput efficiency should be 45 / 50 * 100 = 90.0%
        self.assertEqual(comp.protocols["quic"].throughput_efficiency_pct, 90.0)

    def test_csv_and_json_export_structure(self) -> None:
        """Verify CSV and JSON export generators."""
        exp = Experiment(
            id="EXP-EXPORT01",
            status="COMPLETE",
            protocols=json.dumps(["tcp", "quic"]),
            bandwidth_mbps=20.0,
            latency_ms=50.0,
            packet_loss_pct=1.0,
            duration_sec=5,
            created_at=datetime.now(timezone.utc),
        )
        r_tcp = Result(
            experiment_id="EXP-EXPORT01",
            protocol="tcp",
            throughput_mbps=15.0,
            latency_ms=55.0,
            jitter_ms=None,
            packet_loss_pct=0.0,
            cpu_usage_pct=12.0,
            transfer_time_sec=5.0,
            handshake_success=True,
        )
        r_quic = Result(
            experiment_id="EXP-EXPORT01",
            protocol="quic",
            throughput_mbps=18.0,
            latency_ms=52.0,
            jitter_ms=None,
            packet_loss_pct=0.0,
            cpu_usage_pct=14.0,
            transfer_time_sec=5.0,
            handshake_success=True,
        )
        exp.results = [r_tcp, r_quic]

        comp = build_comparison(exp)

        # Test CSV export
        csv_str = export_experiment_csv(exp, comp)
        self.assertIn("EXP-EXPORT01", csv_str)
        self.assertIn("TCP", csv_str)
        self.assertIn("QUIC", csv_str)
        reader = list(csv.reader(io.StringIO(csv_str)))
        self.assertGreater(len(reader), 5)

        # Test JSON export
        json_data = export_experiment_json(exp, comp)
        self.assertEqual(json_data["experiment_id"], "EXP-EXPORT01")
        self.assertIn("tcp", json_data["protocols"])
        self.assertIn("quic", json_data["protocols"])
        self.assertEqual(json_data["config"]["bandwidth_mbps"], 20.0)


class TestStage7ApiIntegration(unittest.TestCase):
    """Integration test suite for Stage 7 research API endpoints."""

    proc: subprocess.Popen | None = None
    port: int = 8907

    @classmethod
    def setUpClass(cls) -> None:
        env = os.environ.copy()
        env["PYTHONPATH"] = f"{BACKEND_DIR}:{PROJECT_ROOT}"
        env["NETPULSE_EXECUTION_MODE"] = "simulation"

        python_bin = get_python_exe()
        cls.proc = subprocess.Popen(
            [python_bin, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(cls.port)],
            cwd=str(BACKEND_DIR),
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        cls._wait_for_server(cls.port)

    @classmethod
    def tearDownClass(cls) -> None:
        if cls.proc:
            cls.proc.terminate()
            try:
                cls.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                cls.proc.kill()

    @classmethod
    def _wait_for_server(cls, port: int, max_retries: int = 40) -> None:
        url = f"http://127.0.0.1:{port}/health"
        for _ in range(max_retries):
            try:
                code, data, _ = http_request(url, timeout=1.0)
                if code == 200 and isinstance(data, dict) and data.get("status") == "ok":
                    return
            except Exception:
                pass
            time.sleep(0.2)
        raise RuntimeError(f"Server on port {port} failed to become ready.")

    def test_01_get_presets_matches_source_of_truth(self) -> None:
        """GET /presets must return all verified presets from network/presets.py."""
        code, data, _ = http_request(f"http://127.0.0.1:{self.port}/presets")
        self.assertEqual(code, 200)
        self.assertIsInstance(data, dict)

        expected_presets = list_presets()
        self.assertEqual(set(data.keys()), set(expected_presets.keys()))
        for key, expected_vals in expected_presets.items():
            self.assertEqual(data[key]["bandwidth_mbps"], expected_vals["bandwidth_mbps"])
            self.assertEqual(data[key]["latency_ms"], expected_vals["latency_ms"])
            self.assertEqual(data[key]["packet_loss_pct"], expected_vals["packet_loss_pct"])

    def test_02_unknown_experiment_returns_404(self) -> None:
        """Non-existent experiments should return 404 for compare, export, and status."""
        for endpoint in ["compare", "export", "status", "results"]:
            code, data, _ = http_request(f"http://127.0.0.1:{self.port}/experiment/{endpoint}/EXP-NONEXIST")
            self.assertEqual(code, 404, f"Endpoint /experiment/{endpoint} did not return 404 for missing experiment")

    def test_03_invalid_experiment_id_format_returns_400(self) -> None:
        """Malformed or traversal-attempting experiment IDs should return 400 or 404.

        400 is expected for IDs that fail SAFE_ID_REGEX.
        404 is acceptable for IDs that pass regex but don't exist in the database.
        """
        # Characters / patterns that violate SAFE_ID_REGEX = r'^[A-Za-z0-9_-]{1,32}$'
        malicious_ids = ["../etc/passwd", "EXP;rm -rf", "EXP'OR'1'='1", "EXP/test/123", "!@#$%^&*"]
        for bad_id in malicious_ids:
            safe_encoded = urllib.parse.quote(bad_id, safe="")
            code, _, _ = http_request(f"http://127.0.0.1:{self.port}/experiment/compare/{safe_encoded}")
            self.assertIn(code, (400, 404), f"Malformed ID '{bad_id}' was not rejected with 400 or 404")

        # SAFE_ID_REGEX length boundary: 33+ chars must be rejected (max is 32)
        id_33_chars = "A" * 33
        code, _, _ = http_request(f"http://127.0.0.1:{self.port}/experiment/compare/{id_33_chars}")
        self.assertEqual(code, 400, "33-char experiment ID (exceeds 32-char limit) should return 400")

        # Edge: exactly 32 chars is valid by regex and should return 404 (not 400)
        id_32_chars = "A" * 32
        code, _, _ = http_request(f"http://127.0.0.1:{self.port}/experiment/compare/{id_32_chars}")
        self.assertEqual(code, 404, "32-char experiment ID should pass regex validation and return 404 (not found)")

    def test_04_raw_artifact_retrieval_and_security(self) -> None:
        """Verify secure raw JSON artifact retrieval and path traversal prevention."""
        # 1. Invalid protocol
        code, data, _ = http_request(f"http://127.0.0.1:{self.port}/experiment/raw/EXP-VALID/badprotocol")
        self.assertEqual(code, 400)
        self.assertIn("Invalid protocol", str(data))

        # 2. Path traversal in protocol or id
        code, _, _ = http_request(f"http://127.0.0.1:{self.port}/experiment/raw/EXP-VALID/%2e%2e%2f%2e%2e%2fetc")
        self.assertIn(code, (400, 404))

        # 3. Create a valid mock raw file for testing secure retrieval
        test_exp_id = "EXP-TESTRAW01"
        test_file = RAW_RESULTS_DIR / f"{test_exp_id}_tcp.json"
        try:
            # First create the experiment record in DB via start
            payload = {
                "protocols": ["tcp"],
                "bandwidth_mbps": 10.0,
                "latency_ms": 0.0,
                "packet_loss_pct": 0.0,
                "duration_sec": 1,
            }
            code, start_res, _ = http_request(
                f"http://127.0.0.1:{self.port}/experiment/start", method="POST", data=payload
            )
            self.assertEqual(code, 201)
            real_exp_id = start_res["experiment_id"]

            # Wait for completion
            for _ in range(30):
                time.sleep(0.5)
                c, s, _ = http_request(f"http://127.0.0.1:{self.port}/experiment/status/{real_exp_id}")
                if s.get("status") in ("COMPLETE", "FAILED"):
                    break

            # Now retrieve raw file
            r_code, r_content, _ = http_request(f"http://127.0.0.1:{self.port}/experiment/raw/{real_exp_id}/tcp")
            self.assertEqual(r_code, 200)
            self.assertIsInstance(r_content, dict)
            self.assertEqual(r_content.get("protocol"), "tcp")
        finally:
            if test_file.is_file():
                test_file.unlink()

    def test_05_multi_protocol_simulation_and_comparative_analytics(self) -> None:
        """Run a simulation with TCP + UDP + QUIC and verify /compare and /export."""
        payload = {
            "protocols": ["tcp", "udp", "quic"],
            "bandwidth_mbps": 50.0,
            "latency_ms": 30.0,
            "packet_loss_pct": 2.0,
            "duration_sec": 2,
        }
        code, data, _ = http_request(
            f"http://127.0.0.1:{self.port}/experiment/start", method="POST", data=payload
        )
        self.assertEqual(code, 201)
        exp_id = data["experiment_id"]

        # Wait for simulation completion
        final_status = "PENDING"
        for _ in range(40):
            time.sleep(0.5)
            s_code, s_data, _ = http_request(f"http://127.0.0.1:{self.port}/experiment/status/{exp_id}")
            self.assertEqual(s_code, 200)
            final_status = s_data.get("status")
            if final_status in ("COMPLETE", "FAILED"):
                break

        self.assertEqual(final_status, "COMPLETE")

        # 1. Test GET /experiment/compare/{id}
        comp_code, comp_data, _ = http_request(f"http://127.0.0.1:{self.port}/experiment/compare/{exp_id}")
        self.assertEqual(comp_code, 200)
        self.assertEqual(comp_data["experiment_id"], exp_id)
        self.assertEqual(len(comp_data["protocols"]), 3)
        self.assertIn("tcp", comp_data["protocols"])
        self.assertIn("udp", comp_data["protocols"])
        self.assertIn("quic", comp_data["protocols"])

        # Check derived metrics presence
        for p in ["tcp", "udp", "quic"]:
            m = comp_data["protocols"][p]
            self.assertGreater(m["throughput_mbps"], 0.0)
            self.assertIsNotNone(m["throughput_efficiency_pct"])
            self.assertIsNotNone(m["cpu_cost_per_mbps"])

        # Ratio vs TCP
        self.assertEqual(comp_data["protocols"]["tcp"]["throughput_ratio_vs_tcp"], 1.0)
        self.assertIsNotNone(comp_data["protocols"]["udp"]["throughput_ratio_vs_tcp"])
        self.assertIsNotNone(comp_data["protocols"]["quic"]["throughput_ratio_vs_tcp"])

        # Summary insights
        self.assertIsNotNone(comp_data["summary"]["fastest_protocol"])
        self.assertGreater(len(comp_data["summary"]["notes"]), 0)

        # 2. Test GET /experiment/export/{id}?format=csv
        csv_code, csv_text, csv_headers = http_request(
            f"http://127.0.0.1:{self.port}/experiment/export/{exp_id}?format=csv"
        )
        self.assertEqual(csv_code, 200)
        self.assertIn("text/csv", csv_headers.get("content-type", ""))
        self.assertIn(f"netpulse_{exp_id}.csv", csv_headers.get("content-disposition", ""))
        self.assertIn("Experiment ID", csv_text)
        self.assertIn("Throughput Efficiency (%)", csv_text)

        # Validate CSV parser readability
        reader = list(csv.reader(io.StringIO(csv_text)))
        self.assertGreater(len(reader), 10)

        # 3. Test GET /experiment/export/{id}?format=json
        json_code, json_data, json_headers = http_request(
            f"http://127.0.0.1:{self.port}/experiment/export/{exp_id}?format=json"
        )
        self.assertEqual(json_code, 200)
        self.assertIn("application/json", json_headers.get("content-type", ""))
        self.assertEqual(json_data["experiment_id"], exp_id)
        self.assertEqual(len(json_data["protocols"]), 3)

    def test_06_enhanced_experiments_list_backward_compatible(self) -> None:
        """GET /experiments returns summary metrics while preserving backward compatibility."""
        code, data, _ = http_request(f"http://127.0.0.1:{self.port}/experiments")
        self.assertEqual(code, 200)
        self.assertIsInstance(data, list)
        self.assertGreater(len(data), 0)

        first = data[0]
        # Backward-compatible fields
        self.assertIn("experiment_id", first)
        self.assertIn("status", first)
        self.assertIn("protocols", first)
        self.assertIn("created_at", first)

        # Stage 7 summary enhancements
        self.assertIn("results_summary", first)
        self.assertIn("bandwidth_mbps", first)
        self.assertIn("latency_ms", first)
        self.assertIn("packet_loss_pct", first)


if __name__ == "__main__":
    unittest.main()
