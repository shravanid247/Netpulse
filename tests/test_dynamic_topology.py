import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = PROJECT_ROOT / "backend"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import unittest
from app.models.schemas import ExperimentRequest, TopologyEdge, TopologyNode, TopologySpec
from network.topology import analyze_topology_path, sanitize_node_id


class TestDynamicTopologyValidation(unittest.TestCase):
    """Test graph structure, Pydantic validation, and safety invariants."""

    def test_valid_topology_validation(self):
        """A valid 4-node linear topology h1-s1-s2-h2 should validate cleanly."""
        spec_dict = {
            "nodes": [
                {"id": "client-1", "label": "Client Host", "type": "client"},
                {"id": "switch-1", "label": "Edge Switch", "type": "switch"},
                {"id": "switch-2", "label": "Core Switch", "type": "switch"},
                {"id": "server-1", "label": "Web Server", "type": "server"},
            ],
            "edges": [
                {"id": "e1", "source": "client-1", "target": "switch-1"},
                {"id": "e2", "source": "switch-1", "target": "switch-2", "bandwidth_mbps": 10.0, "latency_ms": 20.0},
                {"id": "e3", "source": "switch-2", "target": "server-1"},
            ],
        }
        topo = TopologySpec(**spec_dict)
        self.assertEqual(len(topo.nodes), 4)
        self.assertEqual(len(topo.edges), 3)

        req = ExperimentRequest(
            protocols=["tcp", "quic"],
            bandwidth_mbps=25.0,
            latency_ms=45.0,
            packet_loss_pct=1.0,
            duration_sec=5,
            topology=topo,
        )
        self.assertIsNotNone(req.topology)

    def test_reject_missing_client_or_server(self):
        """Topologies missing a client or server should be rejected with clear errors."""
        # Missing server
        with self.assertRaises(ValueError) as ctx:
            TopologySpec(
                nodes=[
                    TopologyNode(id="c1", label="c1", type="client"),
                    TopologyNode(id="s1", label="s1", type="switch"),
                ],
                edges=[TopologyEdge(id="e1", source="c1", target="s1")],
            )
        self.assertIn("server host", str(ctx.exception))

        # Missing client
        with self.assertRaises(ValueError) as ctx:
            TopologySpec(
                nodes=[
                    TopologyNode(id="s1", label="s1", type="switch"),
                    TopologyNode(id="srv1", label="srv1", type="server"),
                ],
                edges=[TopologyEdge(id="e1", source="s1", target="srv1")],
            )
        self.assertIn("client host", str(ctx.exception))

    def test_reject_duplicate_node_ids(self):
        """Duplicate node IDs should be rejected immediately."""
        with self.assertRaises(ValueError) as ctx:
            TopologySpec(
                nodes=[
                    TopologyNode(id="node-1", label="c1", type="client"),
                    TopologyNode(id="node-1", label="srv1", type="server"),
                ],
                edges=[TopologyEdge(id="e1", source="node-1", target="node-1")],
            )
        self.assertIn("Duplicate node IDs", str(ctx.exception))

    def test_reject_invalid_edge_references(self):
        """Edges referencing nonexistent nodes must be rejected."""
        with self.assertRaises(ValueError) as ctx:
            TopologySpec(
                nodes=[
                    TopologyNode(id="c1", label="c1", type="client"),
                    TopologyNode(id="srv1", label="srv1", type="server"),
                ],
                edges=[TopologyEdge(id="e1", source="c1", target="nonexistent_node")],
            )
        self.assertIn("does not exist in topology nodes", str(ctx.exception))

    def test_reject_disconnected_graph(self):
        """Disconnected client and server nodes with no connecting path must be rejected."""
        with self.assertRaises(ValueError) as ctx:
            TopologySpec(
                nodes=[
                    TopologyNode(id="c1", label="Client", type="client"),
                    TopologyNode(id="s1", label="Switch", type="switch"),
                    TopologyNode(id="srv1", label="Server", type="server"),
                    TopologyNode(id="s2", label="Isolated Switch", type="switch"),
                ],
                edges=[
                    # c1 connected to s1, but srv1 only connected to isolated s2
                    TopologyEdge(id="e1", source="c1", target="s1"),
                    TopologyEdge(id="e2", source="s2", target="srv1"),
                ],
            )
        self.assertIn("No connected path found", str(ctx.exception))

    def test_reject_unsafe_node_identifier_injection(self):
        """Node IDs containing shell metacharacters must be rejected by validator."""
        for unsafe_id in ["h1; rm -rf /", "h1 && whoami", "h1`reboot`", "h1|cat"]:
            with self.assertRaises(ValueError):
                TopologyNode(id=unsafe_id, label="Unsafe Host", type="client")


class TestTopologyPathAnalysis(unittest.TestCase):
    """Test BFS path traversal, hop counting, and bottleneck metrics."""

    def test_shortest_path_and_bottleneck_detection(self):
        """Analyze a multi-hop path and verify bottleneck bandwidth and cumulative latency."""
        spec = {
            "nodes": [
                {"id": "client-101", "type": "client"},
                {"id": "switch-1", "type": "switch"},
                {"id": "switch-2", "type": "switch"},
                {"id": "server-202", "type": "server"},
            ],
            "edges": [
                {"source": "client-101", "target": "switch-1", "bandwidth_mbps": 100.0, "latency_ms": 5.0, "packet_loss_pct": 0.0},
                {"source": "switch-1", "target": "switch-2", "bandwidth_mbps": 10.0, "latency_ms": 30.0, "packet_loss_pct": 2.0},
                {"source": "switch-2", "target": "server-202", "bandwidth_mbps": 50.0, "latency_ms": 10.0, "packet_loss_pct": 1.0},
            ],
        }

        res = analyze_topology_path(spec)
        self.assertEqual(res["client"]["id"], "client-101")
        self.assertEqual(res["server"]["id"], "server-202")
        self.assertEqual(res["hop_count"], 3)
        self.assertEqual(res["switch_count"], 2)

        # Bottleneck bandwidth should be min(100, 10, 50) = 10.0 Mbps
        self.assertEqual(res["effective_bandwidth_mbps"], 10.0)

        # Cumulative latency: 5 + 30 + 10 + 2ms (for 2 switches) = 47.0 ms
        self.assertEqual(res["cumulative_latency_ms"], 47.0)

        # Compound packet loss: 1 - (1 - 0.02) * (1 - 0.01) = 1 - 0.98 * 0.99 = 1 - 0.9702 = 2.98%
        self.assertAlmostEqual(res["aggregate_loss_pct"], 2.98, places=2)

    def test_mininet_node_id_sanitization(self):
        """Long React Flow IDs must be sanitized to <= 8 chars to avoid Linux IFNAMSIZ overflow."""
        long_client_id = "client-1729420000000-long-id"
        long_switch_id = "switch-1729420000000-long-id"
        long_server_id = "server-1729420000000-long-id"

        short_c = sanitize_node_id(long_client_id, "client", 1)
        short_s = sanitize_node_id(long_switch_id, "switch", 1)
        short_srv = sanitize_node_id(long_server_id, "server", 1)

        self.assertLessEqual(len(short_c), 8)
        self.assertLessEqual(len(short_s), 8)
        self.assertLessEqual(len(short_srv), 8)

        # Resulting interface name (e.g. short_c + '-eth0') must be <= 15 chars (IFNAMSIZ limit)
        self.assertLessEqual(len(f"{short_c}-eth0"), 15)
        self.assertLessEqual(len(f"{short_s}-eth0"), 15)
        self.assertLessEqual(len(f"{short_srv}-eth0"), 15)


if __name__ == "__main__":
    unittest.main()
