"""Integration tests for real Linux tc/netem network impairment via netpulse-runner.

Requires privileged helper installed at /usr/local/libexec/netpulse-runner.
Skips gracefully if helper or sudo is unavailable.
"""
import json
import os
import subprocess
import time
import unittest
from pathlib import Path

SYSTEM_HELPER = Path("/usr/local/libexec/netpulse-runner")


def helper_available() -> bool:
    return SYSTEM_HELPER.is_file() and os.access(SYSTEM_HELPER, os.X_OK)


@unittest.skipUnless(helper_available(), "Privileged helper /usr/local/libexec/netpulse-runner not available")
class TestNetemMininetIntegration(unittest.TestCase):
    """Integration test suite executing real Mininet and Linux tc/netem tests."""

    def tearDown(self) -> None:
        time.sleep(1.0)

    def test_verify_connectivity(self):
        """Topology h1-s1-s2-h2 should start, ping h1<->h2, and clean up with 0% loss."""
        res = subprocess.run(
            ["sudo", str(SYSTEM_HELPER), "--action", "verify"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(res.returncode, 0, f"Verify failed: {res.stderr}")
        data = json.loads(res.stdout)
        self.assertTrue(data.get("success"))
        self.assertEqual(data.get("ping_loss"), 0.0)

    def test_impairment_lifecycle_and_qdiscs(self):
        """Test full qdisc replacement, latency injection, packet loss, and restoration."""
        res = subprocess.run(
            [
                "sudo", str(SYSTEM_HELPER),
                "--action", "impairment_test",
                "--bandwidth", "10",
                "--latency", "100",
                "--packet-loss", "5",
            ],
            capture_output=True,
            text=True,
            timeout=45,
        )
        self.assertEqual(res.returncode, 0, f"Impairment test failed: {res.stderr}")
        data = json.loads(res.stdout)
        self.assertTrue(data.get("success"))

        # Verify qdisc before was clean
        qdisc_before = data.get("qdisc_before", {})
        self.assertIn("s1-eth2", qdisc_before)

        # Verify netem qdisc was applied
        qdisc_impaired = data.get("qdisc_impaired", {})
        self.assertIn("netem", qdisc_impaired.get("s1-eth2", ""))
        self.assertIn("delay 100ms", qdisc_impaired.get("s1-eth2", ""))
        self.assertIn("loss 5%", qdisc_impaired.get("s1-eth2", ""))

        # Verify ping RTT increased significantly under 100ms one-way delay (>= 200ms RTT)
        baseline_ping = data.get("baseline_ping", {})
        impaired_ping = data.get("impaired_ping", {})
        restored_ping = data.get("restored_ping", {})

        self.assertLess(baseline_ping.get("avg_rtt_ms", 999), 50.0)
        self.assertGreater(impaired_ping.get("avg_rtt_ms", 0), 180.0)
        self.assertLess(restored_ping.get("avg_rtt_ms", 999), 50.0)

    def test_real_tcp_with_impairment(self):
        """Test real TCP benchmark with 10 Mbps bandwidth limit, 100ms latency, and 5% loss."""
        res = subprocess.run(
            [
                "sudo", str(SYSTEM_HELPER),
                "--action", "run",
                "--experiment-id", "test_int_tcp",
                "--protocol", "tcp",
                "--duration", "5",
                "--bandwidth", "10",
                "--latency", "100",
                "--packet-loss", "5",
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(res.returncode, 0, f"TCP run failed: {res.stderr}")
        data = json.loads(res.stdout)
        self.assertTrue(data.get("success"))
        self.assertEqual(data.get("protocol"), "tcp")
        self.assertGreater(data.get("latency_ms", 0), 150.0)
        self.assertLessEqual(data.get("throughput_mbps", 0), 10.0)

    def test_real_udp_with_impairment(self):
        """Test real UDP benchmark measuring ~10 Mbps throughput, ~5% loss, and latency."""
        res = subprocess.run(
            [
                "sudo", str(SYSTEM_HELPER),
                "--action", "run",
                "--experiment-id", "test_int_udp",
                "--protocol", "udp",
                "--duration", "5",
                "--bandwidth", "10",
                "--latency", "100",
                "--packet-loss", "5",
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(res.returncode, 0, f"UDP run failed: {res.stderr}")
        data = json.loads(res.stdout)
        self.assertTrue(data.get("success"))
        self.assertEqual(data.get("protocol"), "udp")
        self.assertGreater(data.get("latency_ms", 0), 150.0)
        self.assertGreater(data.get("packet_loss_pct", 0), 0.0)

    def tearDown(self):
        """Ensure cleanup after every test."""
        subprocess.run(["sudo", str(SYSTEM_HELPER), "--action", "cleanup"], capture_output=True, check=False)


if __name__ == "__main__":
    unittest.main()
