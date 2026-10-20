"""Unit tests for network.presets module."""
import unittest

from network.presets import PRESETS, get_preset, list_presets


class TestPresets(unittest.TestCase):
    """Test preset lookup, structure, and integrity."""

    def test_standard_presets_present(self):
        """Core expected presets must exist."""
        expected = ["excellent", "average", "poor", "very_poor", "fiber", "4g_lte", "satellite", "lossy_iot"]
        for name in expected:
            self.assertIn(name, PRESETS)
            preset = get_preset(name)
            self.assertIn("bandwidth_mbps", preset)
            self.assertIn("latency_ms", preset)
            self.assertIn("packet_loss_pct", preset)
            self.assertGreater(preset["bandwidth_mbps"], 0)
            self.assertGreaterEqual(preset["latency_ms"], 0)
            self.assertGreaterEqual(preset["packet_loss_pct"], 0)
            self.assertLessEqual(preset["packet_loss_pct"], 100)

    def test_case_insensitivity(self):
        p1 = get_preset("POOR")
        p2 = get_preset("poor")
        p3 = get_preset("  Poor  ")
        self.assertEqual(p1, p2)
        self.assertEqual(p2, p3)

    def test_unknown_preset_raises_keyerror(self):
        with self.assertRaises(KeyError):
            get_preset("super_hyperspeed_quantum")

    def test_immutability_of_returned_dict(self):
        """Mutating the returned preset dict must not modify the global preset map."""
        p = get_preset("poor")
        original_bw = p["bandwidth_mbps"]
        p["bandwidth_mbps"] = 9999.0
        fresh_p = get_preset("poor")
        self.assertEqual(fresh_p["bandwidth_mbps"], original_bw)

    def test_list_presets(self):
        all_presets = list_presets()
        self.assertIsInstance(all_presets, dict)
        self.assertIn("excellent", all_presets)
        self.assertEqual(len(all_presets), len(PRESETS))


if __name__ == "__main__":
    unittest.main()
