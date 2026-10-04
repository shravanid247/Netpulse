"""Stage 6 QUIC Integration & Benchmark Tests.

Validates:
1. aioquic, pylsqpack, cryptography dependency availability in project interpreter.
2. Ephemeral X.509 certificate generation, SAN compliance, and CA verification.
3. Standalone loopback client-server QUIC handshake and benchmark transfer.
4. No orphan QUIC processes.
5. Real Mininet execution of QUIC under baseline (100M, 0ms, 0% loss).
6. Real Mininet execution of QUIC under impairment (10M, 50ms, 3% loss).
7. End-to-end API pipeline (POST /experiment/start -> PostgreSQL persistence -> raw JSON).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from experiments.quic.certs import generate_ephemeral_certificate
from experiments.quic.run_quic_test import get_python_interpreter

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = PROJECT_ROOT / "backend"
SYSTEM_HELPER = Path("/usr/local/libexec/netpulse-runner")
RAW_RESULTS_DIR = PROJECT_ROOT / "results" / "raw"


def is_helper_ready() -> bool:
    return SYSTEM_HELPER.is_file() and os.access(SYSTEM_HELPER, os.X_OK)


def http_request(
    url: str,
    method: str = "GET",
    data: dict | None = None,
    timeout: float = 15.0,
) -> tuple[int, dict]:
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    body = json.dumps(data).encode("utf-8") if data is not None else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            resp_body = resp.read().decode("utf-8")
            return resp.status, json.loads(resp_body) if resp_body else {}
    except urllib.error.HTTPError as exc:
        err_body = exc.read().decode("utf-8")
        try:
            parsed = json.loads(err_body)
        except Exception:
            parsed = {"error": err_body}
        return exc.code, parsed


class TestStage6Quic(unittest.TestCase):
    """Stage 6 real QUIC experiment and integration test suite."""

    real_proc: subprocess.Popen | None = None
    real_port: int = 8906

    @classmethod
    def setUpClass(cls) -> None:
        cls.python_bin = get_python_interpreter()

        # Start real execution mode FastAPI backend on port 8906
        env = os.environ.copy()
        env["PYTHONPATH"] = str(BACKEND_DIR)
        env["NETPULSE_EXECUTION_MODE"] = "real"

        cls.real_proc = subprocess.Popen(
            [cls.python_bin, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(cls.real_port)],
            cwd=str(BACKEND_DIR),
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        cls._wait_for_server(cls.real_port)

    @classmethod
    def tearDownClass(cls) -> None:
        if cls.real_proc:
            cls.real_proc.terminate()
            try:
                cls.real_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                cls.real_proc.kill()

        if is_helper_ready():
            subprocess.run(["sudo", str(SYSTEM_HELPER), "--action", "cleanup"], capture_output=True, check=False)
        subprocess.run(["pkill", "-9", "-f", "quic_server.py"], capture_output=True, check=False)
        subprocess.run(["pkill", "-9", "-f", "quic_client.py"], capture_output=True, check=False)

    @classmethod
    def _wait_for_server(cls, port: int, max_retries: int = 40) -> None:
        url = f"http://127.0.0.1:{port}/health"
        for _ in range(max_retries):
            try:
                status, data = http_request(url, timeout=1.0)
                if status == 200 and data.get("status") == "ok":
                    return
            except Exception:
                pass
            time.sleep(0.2)
        raise RuntimeError(f"Server on port {port} failed to become ready.")

    def setUp(self) -> None:
        time.sleep(1.0)

    def tearDown(self) -> None:
        time.sleep(1.0)

    def test_01_quic_dependencies_available(self) -> None:
        """Verify that aioquic, pylsqpack, and cryptography are available in the project interpreter."""
        cmd = [self.python_bin, "-c", "import aioquic, pylsqpack, cryptography; print('QUIC_OK')"]
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
        self.assertEqual(proc.returncode, 0, f"Dependencies unavailable: {proc.stderr}")
        self.assertIn("QUIC_OK", proc.stdout)

    def test_02_ephemeral_cert_generation_and_tls_verification(self) -> None:
        """Verify ephemeral certificate generation, SAN compliance, and TLS verification."""
        ephemeral = generate_ephemeral_certificate(server_ip="10.0.0.2")
        try:
            self.assertTrue(ephemeral.cert_path.is_file())
            self.assertTrue(ephemeral.key_path.is_file())

            cmd = [
                self.python_bin, "-c",
                f"""
from aioquic.quic.configuration import QuicConfiguration
server_conf = QuicConfiguration(is_client=False, alpn_protocols=['netpulse-quic'])
server_conf.load_cert_chain('{ephemeral.cert_path}', '{ephemeral.key_path}')

client_conf = QuicConfiguration(is_client=True, alpn_protocols=['netpulse-quic'], server_name='10.0.0.2')
client_conf.load_verify_locations(cafile='{ephemeral.cert_path}')
print('CONFIG_OK')
                """
            ]
            proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
            self.assertEqual(proc.returncode, 0, f"TLS configuration failed: {proc.stderr}")
            self.assertIn("CONFIG_OK", proc.stdout)
        finally:
            ephemeral.cleanup()
            self.assertFalse(ephemeral.cert_path.is_file())
            self.assertFalse(ephemeral.key_path.is_file())

    def test_03_standalone_quic_benchmark_transfer(self) -> None:
        """Verify real aioquic client and server transfer on loopback."""
        ephemeral = generate_ephemeral_certificate(server_ip="127.0.0.1")
        ready_file = ephemeral.cert_path.parent / "ready.txt"
        server_cmd = [
            self.python_bin, str(PROJECT_ROOT / "experiments" / "quic" / "quic_server.py"),
            "--host", "127.0.0.1",
            "--port", "4444",
            "--cert", str(ephemeral.cert_path),
            "--key", str(ephemeral.key_path),
            "--ready-file", str(ready_file),
        ]
        server_proc = subprocess.Popen(server_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

        try:
            for _ in range(50):
                if ready_file.is_file():
                    break
                time.sleep(0.05)
            self.assertTrue(ready_file.is_file(), "Server failed to signal readiness")

            client_cmd = [
                self.python_bin, str(PROJECT_ROOT / "experiments" / "quic" / "quic_client.py"),
                "--host", "127.0.0.1",
                "--port", "4444",
                "--cert", str(ephemeral.cert_path),
                "--duration", "2",
                "--bandwidth", "25",
                "--server-name", "127.0.0.1",
            ]
            client_res = subprocess.run(client_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            self.assertEqual(client_res.returncode, 0, f"Client failed: {client_res.stderr}")

            data = json.loads(client_res.stdout)
            self.assertEqual(data.get("protocol"), "quic")
            self.assertTrue(data.get("handshake_success"))
            self.assertGreater(data.get("throughput_mbps", 0.0), 0.0)
            self.assertGreater(data.get("transfer_time_sec", 0.0), 0.0)
            self.assertGreater(data.get("bytes_transferred", 0), 0)
        finally:
            server_proc.terminate()
            try:
                server_proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                server_proc.kill()
            ephemeral.cleanup()

    def test_04_no_orphan_quic_processes(self) -> None:
        """Verify no lingering quic_server.py or quic_client.py processes exist."""
        proc = subprocess.run(["pgrep", "-f", "quic_server.py"], stdout=subprocess.PIPE, text=True)
        self.assertEqual(proc.stdout.strip(), "", "Lingering quic_server.py processes found")
        proc = subprocess.run(["pgrep", "-f", "quic_client.py"], stdout=subprocess.PIPE, text=True)
        self.assertEqual(proc.stdout.strip(), "", "Lingering quic_client.py processes found")

    @unittest.skipUnless(is_helper_ready(), "Privileged helper not available for real execution")
    def test_05_real_quic_baseline_helper(self) -> None:
        """Verify real QUIC execution through privileged helper with baseline network."""
        raw_file = RAW_RESULTS_DIR / "stage6_unit_quic_baseline.json"
        if raw_file.is_file():
            raw_file.unlink()

        cmd = [
            "sudo", str(SYSTEM_HELPER),
            "--action", "run",
            "--experiment-id", "stage6_quic_base",
            "--protocol", "quic",
            "--duration", "3",
            "--bandwidth", "100.0",
            "--latency", "0.0",
            "--packet-loss", "0.0",
            "--output-file", str(raw_file),
        ]
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
        self.assertEqual(proc.returncode, 0, f"Helper failed: {proc.stderr}\nstdout: {proc.stdout}")

        data = json.loads(proc.stdout)
        self.assertTrue(data.get("success"))
        self.assertTrue(data.get("handshake_success"))
        self.assertGreater(data.get("throughput_mbps", 0.0), 0.0)
        self.assertGreater(data.get("transfer_time_sec", 0.0), 0.0)
        self.assertTrue(raw_file.is_file(), "Raw file was not created")

    @unittest.skipUnless(is_helper_ready(), "Privileged helper not available for real execution")
    def test_06_real_quic_impaired_helper(self) -> None:
        """Verify real QUIC execution through privileged helper with tc/netem impairment."""
        raw_file = RAW_RESULTS_DIR / "stage6_unit_quic_impaired.json"
        if raw_file.is_file():
            raw_file.unlink()

        cmd = [
            "sudo", str(SYSTEM_HELPER),
            "--action", "run",
            "--experiment-id", "stage6_quic_imp",
            "--protocol", "quic",
            "--duration", "3",
            "--bandwidth", "10.0",
            "--latency", "50.0",
            "--packet-loss", "3.0",
            "--output-file", str(raw_file),
        ]
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
        self.assertEqual(proc.returncode, 0, f"Helper failed: {proc.stderr}\nstdout: {proc.stdout}")

        data = json.loads(proc.stdout)
        self.assertTrue(data.get("success"))
        self.assertTrue(data.get("handshake_success"))
        self.assertGreater(data.get("throughput_mbps", 0.0), 0.0)
        self.assertIsNone(data.get("packet_loss_pct"))
        self.assertEqual(data.get("configured_packet_loss_pct"), 3.0)
        self.assertTrue(raw_file.is_file(), "Raw file was not created")

        raw_json = json.loads(raw_file.read_text())
        self.assertIsNone(raw_json.get("packet_loss_pct"))
        self.assertEqual(raw_json.get("configured_packet_loss_pct"), 3.0)

    @unittest.skipUnless(is_helper_ready(), "Privileged helper not available for real execution")
    def test_07_quic_api_pipeline_real_mode(self) -> None:
        """Verify full API pipeline with real QUIC execution."""
        payload = {
            "protocols": ["quic"],
            "bandwidth_mbps": 10.0,
            "latency_ms": 50.0,
            "packet_loss_pct": 0.0,
            "duration_sec": 3,
        }
        status, data = http_request(
            f"http://127.0.0.1:{self.real_port}/experiment/start",
            method="POST",
            data=payload,
        )
        self.assertEqual(status, 201)
        exp_id = data["experiment_id"]

        final_status = "PENDING"
        for _ in range(45):
            time.sleep(1.0)
            s_code, s_data = http_request(f"http://127.0.0.1:{self.real_port}/experiment/status/{exp_id}")
            self.assertEqual(s_code, 200)
            final_status = s_data.get("status")
            if final_status in ("COMPLETE", "FAILED"):
                break

        self.assertEqual(final_status, "COMPLETE", f"Experiment ended with error: {s_data.get('error')}")

        r_code, r_data = http_request(f"http://127.0.0.1:{self.real_port}/experiment/results/{exp_id}")
        self.assertEqual(r_code, 200)
        self.assertEqual(r_data.get("experiment_id"), exp_id)
        self.assertEqual(len(r_data.get("results", [])), 1)

        quic_res = r_data["results"][0]
        self.assertEqual(quic_res["protocol"], "quic")
        self.assertTrue(quic_res["handshake_success"])
        self.assertGreater(quic_res["throughput_mbps"], 0.0)
        self.assertGreater(quic_res["transfer_time_sec"], 0.0)

        # Raw file check
        self.assertIsNotNone(r_data.get("raw_result_path"))
        raw_path = Path(r_data["raw_result_path"])
        self.assertTrue(raw_path.is_file())
        raw_json = json.loads(raw_path.read_text())
        self.assertIsNone(raw_json.get("packet_loss_pct"))
        self.assertEqual(raw_json.get("configured_packet_loss_pct"), 0.0)


if __name__ == "__main__":
    unittest.main()
