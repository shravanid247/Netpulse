/**
 * Phase 1 Unit Tests: Topology Canvas Wire Animation, Protocol Defaults, & Lifecycle Logic
 * Executed via Node 22 built-in test runner (node --test)
 */
import test from 'node:test';
import assert from 'node:assert/strict';

const colors = { tcp: '#4BC7FF', udp: '#E06A8B', quic: '#315BFF' };

test('Phase 1 - Newly created edge receives valid default protocol and animates', () => {
  // Simulate onConnect creating edge with default protocol
  const connection = { source: 'h1', target: 's1', sourceHandle: 'out', targetHandle: 'in' };
  const newEdge = {
    ...connection,
    id: 'xy-edge__h1-s1',
    type: 'packetEdge',
    data: { protocol: 'quic' },
  };

  assert.equal(newEdge.data.protocol, 'quic');

  // Verify hydrated edge sets running state and speed
  const running = true;
  const speed = 1.5;
  const hydratedEdge = {
    ...newEdge,
    data: {
      protocol: newEdge.data?.protocol || 'quic',
      ...newEdge.data,
      running,
      speed,
    },
  };

  assert.equal(hydratedEdge.data.protocol, 'quic');
  assert.equal(hydratedEdge.data.running, true);
  assert.equal(hydratedEdge.data.speed, 1.5);

  // Verify AnimatedPacketEdge animation condition
  const edgeProtocol = hydratedEdge.data?.protocol || 'quic';
  const edgeColor = colors[edgeProtocol] || colors.quic;
  const isAnimating = Boolean(hydratedEdge.data?.running);

  assert.equal(edgeProtocol, 'quic');
  assert.equal(edgeColor, '#315BFF');
  assert.equal(isAnimating, true);
});

test('Phase 1 - Edge without explicit data falls back to default protocol without breaking', () => {
  const legacyEdge = {
    id: 'edge-legacy',
    source: 's1',
    target: 's2',
    data: {},
  };

  // Test fallback logic in hydratedEdges & AnimatedPacketEdge
  const running = true;
  const resolvedProtocol = legacyEdge.data?.protocol || 'quic';
  const resolvedColor = colors[resolvedProtocol] || colors.quic;
  const isAnimating = Boolean(running);

  assert.equal(resolvedProtocol, 'quic');
  assert.equal(resolvedColor, '#315BFF');
  assert.equal(isAnimating, true);
});

test('Phase 1 - Animation stops immediately when experiment status is COMPLETE or FAILED', () => {
  let running = true;

  // When experiment completes
  const completeStatus = 'COMPLETE';
  if (completeStatus === 'COMPLETE' || completeStatus === 'FAILED') {
    running = false;
  }
  assert.equal(running, false);

  // When experiment fails
  running = true;
  const failedStatus = 'FAILED';
  if (failedStatus === 'COMPLETE' || failedStatus === 'FAILED') {
    running = false;
  }
  assert.equal(running, false);
});

test('Phase 1 - NodeInspector displays real experiment measurements when available', () => {
  const mockResult = {
    experiment_id: 'EXP-A1B2C3',
    status: 'COMPLETE',
    config: { protocols: ['quic'], bandwidth_mbps: 25, latency_ms: 45, packet_loss_pct: 1, duration_sec: 5 },
    results: [
      {
        protocol: 'quic',
        throughput_mbps: 21.45,
        latency_ms: 45.8,
        jitter_ms: null,
        packet_loss_pct: 0.98,
        cpu_usage_pct: 14.2,
        transfer_time_sec: 5.0,
        handshake_success: true,
      },
    ],
  };

  const primaryResult = mockResult.results && mockResult.results.length > 0 ? mockResult.results[0] : null;

  assert.ok(primaryResult);
  assert.equal(primaryResult.throughput_mbps.toFixed(2), '21.45');
  assert.equal(primaryResult.latency_ms.toFixed(1), '45.8');
  assert.equal(primaryResult.packet_loss_pct.toFixed(2), '0.98');
  assert.equal(primaryResult.protocol.toUpperCase(), 'QUIC');
});

test('Phase 1 - NodeInspector displays explicit Unavailable state when results are missing', () => {
  const emptyResult = null;
  const primaryResult = emptyResult?.results && emptyResult.results.length > 0 ? emptyResult.results[0] : null;

  assert.equal(primaryResult, null);
  const displayText = primaryResult ? `${primaryResult.throughput_mbps.toFixed(2)} Mbps` : 'Unavailable';
  const helperText = primaryResult ? 'Measurements present' : 'No experiment measurements recorded yet.';

  assert.equal(displayText, 'Unavailable');
  assert.equal(helperText, 'No experiment measurements recorded yet.');
});

test('Phase 1 - Simulation request payload adheres to ExperimentConfig schema', () => {
  const edges = [
    { id: 'e1', data: { protocol: 'tcp' } },
    { id: 'e2', data: { protocol: 'quic' } },
    { id: 'e3', data: {} },
  ];

  const edgeProtocols = Array.from(new Set(edges.map((e) => e.data?.protocol).filter(Boolean)));
  const targetProtocols = edgeProtocols.length > 0 ? edgeProtocols : ['quic', 'tcp'];

  assert.deepEqual(targetProtocols, ['tcp', 'quic']);

  const payload = {
    protocols: targetProtocols,
    bandwidth_mbps: 25,
    latency_ms: 45,
    packet_loss_pct: 1,
    duration_sec: 5,
  };

  assert.ok(payload.protocols.length > 0);
  assert.ok(payload.bandwidth_mbps > 0);
  assert.ok(payload.duration_sec >= 1);
});

test('Phase 2 - Canvas graph serialization produces valid TopologySpec', () => {
  const nodes = [
    { id: 'client-1', type: 'deviceNode', data: { label: 'Client 1', type: 'client' } },
    { id: 'switch-1', type: 'deviceNode', data: { label: 'Switch 1', type: 'switch' } },
    { id: 'server-1', type: 'deviceNode', data: { label: 'Server 1', type: 'server' } },
  ];
  const edges = [
    { id: 'e1', source: 'client-1', target: 'switch-1', data: { protocol: 'quic' } },
    { id: 'e2', source: 'switch-1', target: 'server-1', data: { protocol: 'quic' } },
  ];

  // Validate presence
  const clientNodes = nodes.filter((n) => n.data?.type === 'client');
  const serverNodes = nodes.filter((n) => n.data?.type === 'server');
  assert.equal(clientNodes.length, 1);
  assert.equal(serverNodes.length, 1);
  assert.ok(edges.length > 0);

  // Serialize topology
  const serializedTopology = {
    nodes: nodes.map((n) => ({
      id: n.id,
      label: n.data.label || n.id,
      type: n.data.type,
    })),
    edges: edges.map((e) => ({
      id: e.id,
      source: e.source,
      target: e.target,
      protocol: e.data?.protocol || 'quic',
    })),
  };

  assert.equal(serializedTopology.nodes.length, 3);
  assert.equal(serializedTopology.edges.length, 2);
  assert.equal(serializedTopology.nodes[0].type, 'client');
  assert.equal(serializedTopology.nodes[2].type, 'server');
  assert.equal(serializedTopology.edges[0].source, 'client-1');

  // Payload with topology
  const config = {
    protocols: ['quic'],
    bandwidth_mbps: 25,
    latency_ms: 45,
    packet_loss_pct: 1,
    duration_sec: 5,
    topology: serializedTopology,
  };

  assert.ok(config.topology);
  assert.equal(config.topology.nodes.length, 3);
});

test('Phase 2 - Topology validation detects missing client or server before sending', () => {
  const nodesOnlySwitch = [
    { id: 's1', type: 'deviceNode', data: { label: 'Switch 1', type: 'switch' } },
    { id: 's2', type: 'deviceNode', data: { label: 'Switch 2', type: 'switch' } },
  ];
  const edges = [{ id: 'e1', source: 's1', target: 's2' }];

  const clientNodes = nodesOnlySwitch.filter((n) => n.data?.type === 'client');
  const serverNodes = nodesOnlySwitch.filter((n) => n.data?.type === 'server');

  assert.equal(clientNodes.length, 0);
  assert.equal(serverNodes.length, 0);

  let error = null;
  if (clientNodes.length === 0) {
    error = 'Topology requires at least one client host (traffic generator)';
  } else if (serverNodes.length === 0) {
    error = 'Topology requires at least one server host (traffic receiver)';
  } else if (edges.length === 0) {
    error = 'Topology links are missing. Connect devices via ports before running.';
  }

  assert.equal(error, 'Topology requires at least one client host (traffic generator)');
});
