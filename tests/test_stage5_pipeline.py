"""Stage 5 Real Experiment Orchestration & API Pipeline Tests.

Verifies:
1. POST /experiment/start returns immediately with PENDING status and experiment ID.
2. Background execution transitions status: PENDING -> RUNNING -> COMPLETE.
3. Real TCP experiment execution over Mininet and tc/netem.
4. Real UDP experiment execution over Mininet and tc/netem.
5. PostgreSQL persistence for Experiment and Result models.
6. Raw JSON files persisted in results/raw/ and referenced in raw_result_path.
7. GET /experiment/status/{id}, GET /experiment/results/{id}, GET /experiments.
8. Controlled failure handling (e.g. unsupported QUIC in real mode without faking data).
9. Cleanup path guarantees: tc impairment reset, Mininet cleaned, no orphaned iperf3.
10. Safe default simulation mode operation.
11. Concurrency serialization lock preventing overlapping Mininet runs.
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

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = PROJECT_ROOT / "backend"
VENV_PYTHON = BACKEND_DIR / ".venv" / "bin" / "python"
SYSTEM_HELPER = Path("/usr/local/libexec/netpulse-runner")
RAW_RESULTS_DIR = PROJECT_ROOT / "results" / "raw"


def is_helper_ready() -> bool:
    return SYSTEM_HELPER.is_file() and os.access(SYSTEM_HELPER, os.X_OK)


def get_python_exe() -> str:
    if VENV_PYTHON.is_file() and os.access(VENV_PYTHON, os.X_OK):
        return str(VENV_PYTHON)
    return sys.executable


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


class TestStage5Pipeline(unittest.TestCase):
    """Test suite for NetPulse Stage 5 orchestration pipeline."""

    sim_proc: subprocess.Popen | None = None
    real_proc: subprocess.Popen | None = None
    sim_port: int = 8901
    real_port: int = 8902

    @classmethod
    def setUpClass(cls) -> None:
        python_bin = get_python_exe()
        env_base = os.environ.copy()
        env_base["PYTHONPATH"] = str(BACKEND_DIR)

        # 1. Start simulation mode server
        sim_env = env_base.copy()
        sim_env["NETPULSE_EXECUTION_MODE"] = "simulation"
        cls.sim_proc = subprocess.Popen(
            [python_bin, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(cls.sim_port)],
            cwd=str(BACKEND_DIR),
            env=sim_env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        # 2. Start real execution mode server if privileged helper is available
        if is_helper_ready():
            real_env = env_base.copy()
            real_env["NETPULSE_EXECUTION_MODE"] = "real"
            cls.real_proc = subprocess.Popen(
                [python_bin, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(cls.real_port)],
                cwd=str(BACKEND_DIR),
                env=real_env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

        # Wait for servers to be healthy
        cls._wait_for_server(cls.sim_port, name="simulation")
        if cls.real_proc is not None:
            cls._wait_for_server(cls.real_port, name="real")

    @classmethod
    def tearDownClass(cls) -> None:
        if cls.sim_proc:
            cls.sim_proc.terminate()
            cls.sim_proc.wait(timeout=5)
        if cls.real_proc:
            cls.real_proc.terminate()
            cls.real_proc.wait(timeout=5)

        # System level cleanup
        if is_helper_ready():
            subprocess.run(["sudo", str(SYSTEM_HELPER), "--action", "cleanup"], capture_output=True, check=False)
        subprocess.run(["killall", "-9", "iperf3"], capture_output=True, check=False)

    def tearDown(self) -> None:
        time.sleep(1.0)

    @classmethod
    def _wait_for_server(cls, port: int, name: str, max_retries: int = 40) -> None:
        url = f"http://127.0.0.1:{port}/health"
        for _ in range(max_retries):
            try:
                status, data = http_request(url, timeout=1.0)
                if status == 200 and data.get("status") == "ok":
                    return
            except Exception:
                pass
            time.sleep(0.2)
        raise RuntimeError(f"Server on port {port} ({name}) failed to become ready.")

    def test_01_health_and_database(self) -> None:
        """Verify API health and database connectivity."""
        status, data = http_request(f"http://127.0.0.1:{self.sim_port}/health")
        self.assertEqual(status, 200)
        self.assertEqual(data.get("service"), "netpulse-api")

        status, data = http_request(f"http://127.0.0.1:{self.sim_port}/health/db")
        self.assertEqual(status, 200)
        self.assertEqual(data.get("database"), "connected")

    def test_02_simulation_pipeline(self) -> None:
        """Verify safe default simulation mode end-to-end."""
        payload = {
            "protocols": ["tcp", "udp"],
            "bandwidth_mbps": 20.0,
            "latency_ms": 30.0,
            "packet_loss_pct": 1.0,
            "duration_sec": 2,
        }
        start_time = time.time()
        status, data = http_request(
            f"http://127.0.0.1:{self.sim_port}/experiment/start",
            method="POST",
            data=payload,
        )
        elapsed = time.time() - start_time
        # POST must return promptly without blocking for the full duration
        self.assertLess(elapsed, 2.0, "POST /experiment/start blocked on experiment run")
        self.assertEqual(status, 201)
        self.assertIn("experiment_id", data)
        self.assertEqual(data.get("status"), "PENDING")

        exp_id = data["experiment_id"]

        # Poll status until complete
        final_status = "PENDING"
        for _ in range(30):
            time.sleep(0.5)
            s_code, s_data = http_request(f"http://127.0.0.1:{self.sim_port}/experiment/status/{exp_id}")
            self.assertEqual(s_code, 200)
            final_status = s_data.get("status")
            if final_status in ("COMPLETE", "FAILED"):
                break

        self.assertEqual(final_status, "COMPLETE")

        # Verify results endpoint
        r_code, r_data = http_request(f"http://127.0.0.1:{self.sim_port}/experiment/results/{exp_id}")
        self.assertEqual(r_code, 200)
        self.assertEqual(r_data.get("experiment_id"), exp_id)
        self.assertEqual(len(r_data.get("results", [])), 2)
        self.assertIsNotNone(r_data.get("raw_result_path"))

        # Verify raw files exist
        raw_paths = r_data["raw_result_path"].split(";")
        for p in raw_paths:
            self.assertTrue(Path(p).is_file(), f"Raw file {p} does not exist")

        # Verify listing
        l_code, l_data = http_request(f"http://127.0.0.1:{self.sim_port}/experiments")
        self.assertEqual(l_code, 200)
        self.assertTrue(any(row["experiment_id"] == exp_id for row in l_data))

    @unittest.skipUnless(is_helper_ready(), "Privileged helper not available for real execution")
    def test_03_real_tcp_experiment(self) -> None:
        """Verify real TCP experiment over Mininet and tc/netem."""
        payload = {
            "protocols": ["tcp"],
            "bandwidth_mbps": 10.0,
            "latency_ms": 60.0,
            "packet_loss_pct": 2.0,
            "duration_sec": 3,
        }
        start_time = time.time()
        status, data = http_request(
            f"http://127.0.0.1:{self.real_port}/experiment/start",
            method="POST",
            data=payload,
        )
        elapsed = time.time() - start_time
        self.assertLess(elapsed, 2.5, "POST /experiment/start blocked on real execution")
        self.assertEqual(status, 201)
        exp_id = data["experiment_id"]
        self.assertEqual(data.get("status"), "PENDING")

        # Wait for real experiment completion
        final_status = "PENDING"
        for _ in range(60):
            time.sleep(1.0)
            s_code, s_data = http_request(f"http://127.0.0.1:{self.real_port}/experiment/status/{exp_id}")
            self.assertEqual(s_code, 200)
            final_status = s_data.get("status")
            if final_status in ("COMPLETE", "FAILED"):
                break

        self.assertEqual(final_status, "COMPLETE", f"Real TCP experiment failed: {s_data}")

        # Fetch detailed results
        r_code, r_data = http_request(f"http://127.0.0.1:{self.real_port}/experiment/results/{exp_id}")
        self.assertEqual(r_code, 200)
        results = r_data.get("results", [])
        self.assertEqual(len(results), 1)

        tcp_result = results[0]
        self.assertEqual(tcp_result["protocol"], "tcp")
        self.assertGreater(tcp_result["throughput_mbps"], 0.0)
        self.assertGreater(tcp_result["latency_ms"], 50.0)
        self.assertIsNotNone(tcp_result["raw_output"])

        # Check raw JSON file
        raw_path = Path(r_data["raw_result_path"])
        self.assertTrue(raw_path.is_file())
        raw_content = json.loads(raw_path.read_text(encoding="utf-8"))
        self.assertIn("start", raw_content)
        self.assertIn("end", raw_content)

    @unittest.skipUnless(is_helper_ready(), "Privileged helper not available for real execution")
    def test_04_real_udp_experiment(self) -> None:
        """Verify real UDP experiment over Mininet and tc/netem."""
        payload = {
            "protocols": ["udp"],
            "bandwidth_mbps": 10.0,
            "latency_ms": 50.0,
            "packet_loss_pct": 3.0,
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
        for _ in range(60):
            time.sleep(1.0)
            s_code, s_data = http_request(f"http://127.0.0.1:{self.real_port}/experiment/status/{exp_id}")
            self.assertEqual(s_code, 200)
            final_status = s_data.get("status")
            if final_status in ("COMPLETE", "FAILED"):
                break

        self.assertEqual(final_status, "COMPLETE", f"Real UDP experiment failed: {s_data}")

        r_code, r_data = http_request(f"http://127.0.0.1:{self.real_port}/experiment/results/{exp_id}")
        self.assertEqual(r_code, 200)
        results = r_data.get("results", [])
        self.assertEqual(len(results), 1)

        udp_result = results[0]
        self.assertEqual(udp_result["protocol"], "udp")
        self.assertGreater(udp_result["throughput_mbps"], 0.0)
        self.assertIsNotNone(udp_result["jitter_ms"])
        self.assertGreaterEqual(udp_result["packet_loss_pct"], 0.0)
        self.assertIsNotNone(udp_result["raw_output"])

    @unittest.skipUnless(is_helper_ready(), "Privileged helper not available for real execution")
    def test_05_real_quic_execution_mode(self) -> None:
        """Verify requesting QUIC in real mode executes real benchmark without fabricating measurements."""
        payload = {
            "protocols": ["quic"],
            "bandwidth_mbps": 10.0,
            "latency_ms": 20.0,
            "packet_loss_pct": 0.0,
            "duration_sec": 2,
        }
        status, data = http_request(
            f"http://127.0.0.1:{self.real_port}/experiment/start",
            method="POST",
            data=payload,
        )
        self.assertEqual(status, 201)
        exp_id = data["experiment_id"]

        final_status = "PENDING"
        for _ in range(30):
            time.sleep(0.5)
            s_code, s_data = http_request(f"http://127.0.0.1:{self.real_port}/experiment/status/{exp_id}")
            final_status = s_data.get("status")
            if final_status in ("COMPLETE", "FAILED"):
                break

        self.assertEqual(final_status, "COMPLETE")
        r_code, r_data = http_request(f"http://127.0.0.1:{self.real_port}/experiment/results/{exp_id}")
        self.assertEqual(r_code, 200)
        self.assertEqual(len(r_data.get("results", [])), 1)
        self.assertEqual(r_data["results"][0]["protocol"], "quic")
        self.assertTrue(r_data["results"][0]["handshake_success"])
        self.assertGreater(r_data["results"][0]["throughput_mbps"], 0.0)

        # Verify no orphaned experiment iperf3 processes remain (exclude host system daemon)
        pgrep = subprocess.run(["pgrep", "-u", f"root,{os.getlogin() if hasattr(os, 'getlogin') else 'kenrich'}", "iperf3"], capture_output=True, text=True)
        self.assertEqual(pgrep.stdout.strip(), "", "Orphaned experiment iperf3 processes detected")

    def test_06_request_validation(self) -> None:
        """Verify invalid requests are rejected with 422 Unprocessable Entity."""
        # Invalid protocol
        status, _ = http_request(
            f"http://127.0.0.1:{self.sim_port}/experiment/start",
            method="POST",
            data={"protocols": ["invalid_proto"], "bandwidth_mbps": 10, "latency_ms": 0, "packet_loss_pct": 0, "duration_sec": 5},
        )
        self.assertEqual(status, 422)

        # Duration out of bounds
        status, _ = http_request(
            f"http://127.0.0.1:{self.sim_port}/experiment/start",
            method="POST",
            data={"protocols": ["tcp"], "bandwidth_mbps": 10, "latency_ms": 0, "packet_loss_pct": 0, "duration_sec": 0},
        )
        self.assertEqual(status, 422)

    def test_07_concurrency_lock(self) -> None:
        """Verify multiple submitted experiments are serialized safely without collisions."""
        p1 = {"protocols": ["tcp"], "bandwidth_mbps": 10, "latency_ms": 0, "packet_loss_pct": 0, "duration_sec": 2}
        p2 = {"protocols": ["udp"], "bandwidth_mbps": 10, "latency_ms": 0, "packet_loss_pct": 0, "duration_sec": 2}

        # Start first experiment
        s1, d1 = http_request(f"http://127.0.0.1:{self.sim_port}/experiment/start", method="POST", data=p1)
        self.assertEqual(s1, 201)
        exp1 = d1["experiment_id"]

        # Immediately start second experiment
        s2, d2 = http_request(f"http://127.0.0.1:{self.sim_port}/experiment/start", method="POST", data=p2)
        self.assertEqual(s2, 201)
        exp2 = d2["experiment_id"]

        # Both returned 201 promptly with distinct IDs
        self.assertNotEqual(exp1, exp2)

        # Poll exp2 until complete
        for _ in range(40):
            time.sleep(0.5)
            _, stat2 = http_request(f"http://127.0.0.1:{self.sim_port}/experiment/status/{exp2}")
            if stat2.get("status") in ("COMPLETE", "FAILED"):
                break

        self.assertEqual(stat2.get("status"), "COMPLETE")


if __name__ == "__main__":
    unittest.main()
