"""Unit tests for network.netem traffic control module.

Tests validation, command construction, safety bounds, and reset behavior.
These tests run without root privileges.
"""
import unittest
from unittest.mock import MagicMock, patch

from network.netem import (
    MAX_BANDWIDTH_MBPS,
    MAX_LATENCY_MS,
    MAX_LOSS_PCT,
    MIN_BANDWIDTH_MBPS,
    MIN_LATENCY_MS,
    MIN_LOSS_PCT,
    build_tc_command,
    get_qdisc_info,
    reset_network,
    reset_topology_impairment,
    set_conditions,
    validate_impairment_params,
    validate_interface_name,
)


class TestNetemValidation(unittest.TestCase):
    """Test parameter validation rules and boundary conditions."""

    def test_valid_parameters(self):
        """Valid parameters should not raise any exceptions."""
        validate_impairment_params(bandwidth_mbps=100.0, latency_ms=20.0, packet_loss_pct=1.0)
        validate_impairment_params(bandwidth_mbps=MIN_BANDWIDTH_MBPS, latency_ms=MIN_LATENCY_MS, packet_loss_pct=MIN_LOSS_PCT)
        validate_impairment_params(bandwidth_mbps=MAX_BANDWIDTH_MBPS, latency_ms=MAX_LATENCY_MS, packet_loss_pct=MAX_LOSS_PCT)
        validate_impairment_params(bandwidth_mbps=None, latency_ms=None, packet_loss_pct=None)

    def test_invalid_bandwidth(self):
        """Invalid bandwidth values must raise ValueError."""
        # Zero bandwidth
        with self.assertRaises(ValueError):
            validate_impairment_params(bandwidth_mbps=0.0)
        # Negative bandwidth
        with self.assertRaises(ValueError):
            validate_impairment_params(bandwidth_mbps=-10.0)
        # Exceeding maximum limit (10 Gbps)
        with self.assertRaises(ValueError):
            validate_impairment_params(bandwidth_mbps=10001.0)
        # Non-numeric
        with self.assertRaises(ValueError):
            validate_impairment_params(bandwidth_mbps="fast")  # type: ignore

    def test_invalid_latency(self):
        """Invalid latency values must raise ValueError."""
        # Negative latency
        with self.assertRaises(ValueError):
            validate_impairment_params(latency_ms=-1.0)
        # Exceeding max limit (10,000 ms)
        with self.assertRaises(ValueError):
            validate_impairment_params(latency_ms=10001.0)
        # Non-numeric
        with self.assertRaises(ValueError):
            validate_impairment_params(latency_ms="slow")  # type: ignore

    def test_invalid_packet_loss(self):
        """Invalid packet loss percentages must raise ValueError."""
        # Negative loss
        with self.assertRaises(ValueError):
            validate_impairment_params(packet_loss_pct=-0.1)
        # Loss > 100%
        with self.assertRaises(ValueError):
            validate_impairment_params(packet_loss_pct=100.1)
        # Non-numeric
        with self.assertRaises(ValueError):
            validate_impairment_params(packet_loss_pct="bad")  # type: ignore

    def test_interface_name_validation(self):
        """Interface names must match safe alphanumeric pattern."""
        valid_intfs = ["s1-eth1", "s1-eth2", "s2-eth1", "s2-eth2", "h1-eth0", "eth0", "lo"]
        for intf in valid_intfs:
            validate_interface_name(intf)

        invalid_intfs = [
            "s1-eth1; rm -rf /",
            "intf|cat",
            "s1`whoami`",
            "$HOME",
            "",
            "a",  # too short (< 2)
            "a" * 25,  # too long (> 16)
        ]
        for intf in invalid_intfs:
            with self.assertRaises(ValueError, msg=f"Failed to reject: {intf}"):
                validate_interface_name(intf)


class TestCommandConstruction(unittest.TestCase):
    """Test tc command argument formatting."""

    def test_full_impairment_command(self):
        cmd = build_tc_command(
            interface="s1-eth2",
            bandwidth_mbps=10.0,
            latency_ms=100.0,
            packet_loss_pct=5.0,
        )
        self.assertEqual(
            cmd,
            ["tc", "qdisc", "replace", "dev", "s1-eth2", "root", "netem", "delay", "100.00ms", "loss", "5.00%", "rate", "10.00mbit"],
        )

    def test_partial_impairment_command(self):
        # Latency only
        cmd_lat = build_tc_command("s1-eth2", latency_ms=50.0)
        self.assertEqual(
            cmd_lat,
            ["tc", "qdisc", "replace", "dev", "s1-eth2", "root", "netem", "delay", "50.00ms"],
        )

        # Loss only
        cmd_loss = build_tc_command("s1-eth2", packet_loss_pct=2.5)
        self.assertEqual(
            cmd_loss,
            ["tc", "qdisc", "replace", "dev", "s1-eth2", "root", "netem", "loss", "2.50%"],
        )

        # Rate only
        cmd_rate = build_tc_command("s1-eth2", bandwidth_mbps=25.0)
        self.assertEqual(
            cmd_rate,
            ["tc", "qdisc", "replace", "dev", "s1-eth2", "root", "netem", "rate", "25.00mbit"],
        )

    def test_zero_parameters_omitted(self):
        """Zero latency or loss should not add unnecessary netem flags."""
        cmd = build_tc_command("s1-eth2", bandwidth_mbps=10.0, latency_ms=0.0, packet_loss_pct=0.0)
        self.assertEqual(
            cmd,
            ["tc", "qdisc", "replace", "dev", "s1-eth2", "root", "netem", "rate", "10.00mbit"],
        )


class TestNetemMockOperations(unittest.TestCase):
    """Test execution wrappers using mocks."""

    @patch("subprocess.run")
    def test_set_conditions_success(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        set_conditions("s1-eth2", bandwidth_mbps=10.0, latency_ms=100.0, packet_loss_pct=5.0)
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        self.assertEqual(args[0], "tc")
        self.assertIn("s1-eth2", args)

    @patch("subprocess.run")
    def test_set_conditions_failure(self, mock_run):
        mock_run.return_value = MagicMock(returncode=2, stdout="", stderr="RTNETLINK answers: Operation not permitted")
        with self.assertRaises(RuntimeError) as ctx:
            set_conditions("s1-eth2", bandwidth_mbps=10.0)
        self.assertIn("Operation not permitted", str(ctx.exception))

    @patch("subprocess.run")
    def test_reset_network(self, mock_run):
        import subprocess
        mock_run.return_value = MagicMock(returncode=0)
        reset_network("s1-eth2")
        mock_run.assert_called_once_with(
            ["tc", "qdisc", "del", "dev", "s1-eth2", "root"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )

    @patch("subprocess.run")
    def test_reset_topology_impairment(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        reset_topology_impairment(interfaces=["s1-eth2", "s2-eth1"])
        self.assertEqual(mock_run.call_count, 2)

    @patch("subprocess.run")
    def test_get_qdisc_info(self, mock_run):
        import subprocess
        mock_run.return_value = MagicMock(returncode=0, stdout="qdisc netem 8001: root limit 1000 delay 100ms loss 5%")
        info = get_qdisc_info("s1-eth2")
        self.assertIn("delay 100ms", info)
        mock_run.assert_called_once_with(
            ["tc", "qdisc", "show", "dev", "s1-eth2"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )


if __name__ == "__main__":
    unittest.main()
