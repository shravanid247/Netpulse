'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  addEdge, Background, BaseEdge, Controls, Edge, EdgeProps, Handle, MiniMap,
  Node, NodeProps, Position, ReactFlow, ReactFlowProvider, useEdgesState, useNodesState,
  getBezierPath, useReactFlow, Connection,
} from '@xyflow/react';
import { Laptop, Network, Play, Server, X, Gauge, MousePointer2, Loader2, AlertCircle } from 'lucide-react';
import { create } from 'zustand';
import {
  ExperimentConfig,
  ExperimentResponse,
  Protocol,
  TopologySpec,
  getExperimentResults,
  getExperimentStatus,
  getExperiments,
  startExperiment,
} from '@/lib/api';

type DeviceType = 'client' | 'switch' | 'server';
type DeviceData = { label: string; type: DeviceType; protocol?: Protocol; onDelete?: (id: string) => void; onRename?: (id: string, label: string) => void; onSelect?: (id: string) => void };
type PacketEdgeData = { protocol?: Protocol; running?: boolean; latency?: number; loss?: number; speed?: number; onSelect?: (id: string) => void };

export type SimulationStatus = 'IDLE' | 'PENDING' | 'RUNNING' | 'COMPLETE' | 'FAILED';

export type BuilderState = {
  selectedId: string | null;
  selectedEdgeId: string | null;
  running: boolean;
  speed: number;
  status: SimulationStatus;
  experimentId: string | null;
  error: string | null;
  latestResult: ExperimentResponse | null;
  setSelected: (id: string | null) => void;
  setSelectedEdge: (id: string | null) => void;
  setRunning: (running: boolean) => void;
  setSpeed: (speed: number) => void;
  setStatus: (status: SimulationStatus) => void;
  setExperimentId: (id: string | null) => void;
  setError: (error: string | null) => void;
  setLatestResult: (result: ExperimentResponse | null) => void;
};

export const useBuilderStore = create<BuilderState>((set) => ({
  selectedId: null,
  selectedEdgeId: null,
  running: false,
  speed: 1,
  status: 'IDLE',
  experimentId: null,
  error: null,
  latestResult: null,
  setSelected: (selectedId) => set({ selectedId, selectedEdgeId: null }),
  setSelectedEdge: (selectedEdgeId) => set({ selectedEdgeId, selectedId: null }),
  setRunning: (running) => set({ running }),
  setSpeed: (speed) => set({ speed }),
  setStatus: (status) => set({ status }),
  setExperimentId: (experimentId) => set({ experimentId }),
  setError: (error) => set({ error }),
  setLatestResult: (latestResult) => set({ latestResult }),
}));

const colors = { tcp: '#4BC7FF', udp: '#E06A8B', quic: '#315BFF' } as const;
const initialNodes: Node<DeviceData>[] = [
  { id: 'h1', type: 'deviceNode', position: { x: 70, y: 175 }, data: { label: 'h1', type: 'client' } },
  { id: 's1', type: 'deviceNode', position: { x: 320, y: 175 }, data: { label: 's1', type: 'switch' } },
  { id: 's2', type: 'deviceNode', position: { x: 570, y: 175 }, data: { label: 's2', type: 'switch' } },
  { id: 'h2', type: 'deviceNode', position: { x: 820, y: 175 }, data: { label: 'h2', type: 'server' } },
];
const initialEdges: Edge<PacketEdgeData>[] = [
  { id: 'e-h1-s1', source: 'h1', target: 's1', type: 'packetEdge', data: { protocol: 'quic' } },
  { id: 'e-s1-s2', source: 's1', target: 's2', type: 'packetEdge', data: { protocol: 'quic' } },
  { id: 'e-s2-h2', source: 's2', target: 'h2', type: 'packetEdge', data: { protocol: 'quic' } },
];

function DeviceNode({ id, data, selected }: NodeProps<Node<DeviceData>>) {
  const Icon = data.type === 'client' ? Laptop : data.type === 'server' ? Server : Network;
  const color = data.protocol ? colors[data.protocol] : 'var(--color-line)';
  const [editing, setEditing] = useState(false);
  const [label, setLabel] = useState(data.label);
  const commit = () => { setEditing(false); data.onRename?.(id, label.trim() || data.label); };
  return <div className={`device-node ${selected ? 'selected' : ''}`} style={{ '--node-color': color } as React.CSSProperties} onDoubleClick={() => setEditing(true)}>
    <Handle type="target" position={Position.Left} className="device-port" id="in" />
    <span className="port-label port-label-in">IN</span>
    <button className="device-delete nodrag" onClick={() => data.onDelete?.(id)} aria-label={`Delete ${data.label}`}><X size={12} /></button>
    <div className="device-icon"><Icon size={28} strokeWidth={1.6} /></div>
    <span className="device-type">{data.type}</span>
    {editing ? <input autoFocus className="device-name-input nodrag" value={label} onChange={(event) => setLabel(event.target.value)} onBlur={commit} onKeyDown={(event) => event.key === 'Enter' && commit()} /> : <span className="device-name">{data.label}</span>}
    <span className="port-label port-label-out">OUT</span><Handle type="source" position={Position.Right} className="device-port" id="out" />
  </div>;
}

function AnimatedPacketEdge({ id, sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition, data, selected }: EdgeProps<Edge<PacketEdgeData>>) {
  const [path] = getBezierPath({ sourceX, sourceY, sourcePosition, targetX, targetY, targetPosition, curvature: .22 });
  const protocol = data?.protocol || 'quic';
  const color = colors[protocol] || colors.quic;
  const running = Boolean(data?.running);
  return <>
    <BaseEdge id={id} path={path} interactionWidth={22} style={{ stroke: color, strokeWidth: selected ? 4 : 2.5, filter: `drop-shadow(0 0 8px ${color})` }} />
    {running && [0, 1, 2].map((offset) => <circle key={`${id}-${offset}`} r="4" fill={color} filter={`drop-shadow(0 0 7px ${color})`}><animateMotion dur={`${1.8 / (data?.speed || 1)}s`} begin={`${offset * .55}s`} repeatCount="indefinite" path={path} /></circle>)}
  </>;
}

const nodeTypes = { deviceNode: DeviceNode };
const edgeTypes = { packetEdge: AnimatedPacketEdge };

function DeviceToolbox() {
  const devices: { type: DeviceType; label: string; icon: typeof Laptop }[] = [{ type: 'client', label: 'Client host', icon: Laptop }, { type: 'switch', label: 'Switch', icon: Network }, { type: 'server', label: 'Server', icon: Server }];
  return <aside className="device-toolbox"><div className="toolbox-title"><span className="eyebrow">Palette</span><h3>Devices</h3></div>{devices.map(({ type, label, icon: Icon }) => <div key={type} className="toolbox-item" draggable onDragStart={(event) => { event.dataTransfer.setData('application/netpulse-device', type); event.dataTransfer.effectAllowed = 'move'; }}><Icon size={19} /><span>{label}</span><span className="drag-hint">+</span></div>)}<div className="toolbox-note"><MousePointer2 size={14} /> Drag onto canvas</div></aside>;
}

function SimulationToolbar({ nodes, edges }: { nodes: Node<DeviceData>[]; edges: Edge<PacketEdgeData>[] }) {
  const { running, setRunning, speed, setSpeed, status, setStatus, experimentId, setExperimentId, error, setError, setLatestResult } = useBuilderStore();
  const pollRef = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  const startSimulation = async () => {
    if (status === 'PENDING' || status === 'RUNNING') return;

    setError(null);

    // Validate graph requirements
    const clientNodes = nodes.filter((n) => n.data?.type === 'client');
    const serverNodes = nodes.filter((n) => n.data?.type === 'server');

    if (clientNodes.length === 0) {
      setError('Topology requires at least one client host (traffic generator)');
      return;
    }
    if (serverNodes.length === 0) {
      setError('Topology requires at least one server host (traffic receiver)');
      return;
    }
    if (edges.length === 0) {
      setError('Topology links are missing. Connect devices via ports before running.');
      return;
    }

    setStatus('PENDING');

    const edgeProtocols = Array.from(new Set(edges.map((e) => e.data?.protocol).filter(Boolean))) as Protocol[];
    const targetProtocols: Protocol[] = edgeProtocols.length > 0 ? edgeProtocols : ['quic', 'tcp'];

    const serializedTopology: TopologySpec = {
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
        bandwidth_mbps: e.data?.speed ? 25 * e.data.speed : undefined,
        latency_ms: e.data?.latency,
        packet_loss_pct: e.data?.loss,
      })),
    };

    const config: ExperimentConfig = {
      protocols: targetProtocols,
      bandwidth_mbps: 25,
      latency_ms: 45,
      packet_loss_pct: 1,
      duration_sec: 5,
      topology: serializedTopology,
    };

    try {
      const res = await startExperiment(config);
      setExperimentId(res.experiment_id);
      setStatus('PENDING');

      pollRef.current = setInterval(async () => {
        try {
          const s = await getExperimentStatus(res.experiment_id);
          if (s.status === 'RUNNING') {
            setStatus('RUNNING');
            setRunning(true);
          } else if (s.status === 'COMPLETE') {
            if (pollRef.current) clearInterval(pollRef.current);
            setStatus('COMPLETE');
            setRunning(false);
            try {
              const fullResults = await getExperimentResults(res.experiment_id);
              setLatestResult(fullResults);
            } catch (resErr: unknown) {
              console.warn('Failed to retrieve experiment results:', resErr);
            }
          } else if (s.status === 'FAILED') {
            if (pollRef.current) clearInterval(pollRef.current);
            setStatus('FAILED');
            setRunning(false);
            setError(s.error || 'Experiment execution failed');
          }
        } catch (pollErr: unknown) {
          console.error('Experiment polling error:', pollErr);
        }
      }, 1000);
    } catch (err: unknown) {
      setStatus('FAILED');
      setRunning(false);
      setError(err instanceof Error ? err.message : 'Failed to start experiment');
    }
  };

  const isBusy = status === 'PENDING' || status === 'RUNNING';

  return (
    <div className="simulation-toolbar">
      <button className={`simulation-run ${isBusy ? 'running' : ''}`} onClick={startSimulation} disabled={isBusy} aria-busy={isBusy}>
        {status === 'PENDING' ? (
          <>
            <Loader2 size={15} className="animate-spin" />
            INITIALIZING...
          </>
        ) : status === 'RUNNING' ? (
          <>
            <Loader2 size={15} className="animate-spin" />
            BENCHMARKING...
          </>
        ) : (
          <>
            <Play size={15} />
            RUN SIMULATION
          </>
        )}
      </button>
      <span className="toolbar-divider" />
      <Gauge size={15} className="toolbar-icon" />
      <span className="toolbar-label">VISUAL SPEED</span>
      {[.5, 1, 2].map((value) => (
        <button key={value} className={`speed-button ${speed === value ? 'active' : ''}`} onClick={() => setSpeed(value)}>
          {value}x
        </button>
      ))}
      <div className="toolbar-status">
        <span className={`badge badge-${status.toLowerCase()}`}>{status === 'IDLE' ? 'READY' : status}</span>
        {experimentId && <span className="mono tiny" style={{ fontSize: 10 }}>{experimentId}</span>}
      </div>
      {error && (
        <div className="toolbar-error" title={error}>
          <AlertCircle size={13} />
          <span style={{ maxWidth: 240, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{error}</span>
          <button onClick={() => setError(null)} style={{ border: 0, background: 'transparent', padding: 0, display: 'flex', color: 'inherit' }} aria-label="Dismiss error">
            <X size={12} />
          </button>
        </div>
      )}
    </div>
  );
}

function NodeInspector({ nodes, edges, onClose }: { nodes: Node<DeviceData>[]; edges: Edge<PacketEdgeData>[]; onClose: () => void }) {
  const { selectedId, selectedEdgeId, latestResult, experimentId } = useBuilderStore();
  const node = nodes.find((item) => item.id === selectedId);
  const edge = edges.find((item) => item.id === selectedEdgeId);
  if (!node && !edge) return null;
  const linked = node ? edges.filter((item) => item.source === node.id || item.target === node.id) : [];
  const primaryResult = latestResult?.results && latestResult.results.length > 0 ? latestResult.results[0] : null;

  return (
    <aside className="node-inspector">
      <button className="inspector-close" onClick={onClose} aria-label="Close inspector">
        <X size={16} />
      </button>
      <span className="eyebrow">Inspector</span>
      {node ? (
        <>
          <h3>{node.data.label}</h3>
          <span className="inspector-type">{node.data.type} device</span>
          <div className="inspector-section">
            <span className="field-label">Connected links</span>
            {linked.length ? (
              linked.map((item) => (
                <div className="linked-row" key={item.id}>
                  <span>{item.source} → {item.target}</span>
                  <b style={{ color: item.data?.protocol ? colors[item.data.protocol] : 'var(--color-ink-muted)' }}>
                    {item.data?.protocol?.toUpperCase() || 'QUIC'}
                  </b>
                </div>
              ))
            ) : (
              <p>No links connected.</p>
            )}
          </div>
          {node.data.type === 'server' && (
            <div className="inspector-result">
              <span className="field-label">
                Last experiment {latestResult?.experiment_id ? `(${latestResult.experiment_id})` : experimentId ? `(${experimentId})` : ''}
              </span>
              {primaryResult ? (
                <>
                  <strong>{primaryResult.throughput_mbps.toFixed(2)} Mbps</strong>
                  <small>
                    {primaryResult.latency_ms > 0 ? `${primaryResult.latency_ms.toFixed(1)} ms latency` : '0.0 ms latency'} / {primaryResult.packet_loss_pct.toFixed(2)}% loss ({primaryResult.protocol.toUpperCase()})
                  </small>
                </>
              ) : (
                <>
                  <strong style={{ fontSize: 16, color: 'var(--color-ink-muted)' }}>Unavailable</strong>
                  <small>No experiment measurements recorded yet.</small>
                </>
              )}
            </div>
          )}
        </>
      ) : (
        <>
          <h3>Link assignment</h3>
          <span className="inspector-type">{edge?.source} → {edge?.target}</span>
          <div className="protocol-assignment">
            <span className="field-label">Simulated protocol</span>
            {(['tcp', 'udp', 'quic'] as Protocol[]).map((protocol) => (
              <button
                key={protocol}
                className={`assign-button ${(edge?.data?.protocol || 'quic') === protocol ? 'selected' : ''}`}
                style={{ '--assign-color': colors[protocol] } as React.CSSProperties}
                onClick={() => window.dispatchEvent(new CustomEvent('netpulse:assign-edge', { detail: { id: edge?.id, protocol } }))}
              >
                {protocol.toUpperCase()}
              </button>
            ))}
          </div>
        </>
      )}
    </aside>
  );
}

function CanvasInner() {
  const [nodes, setNodes, onNodesChange] = useNodesState<Node<DeviceData>>(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge<PacketEdgeData>>(initialEdges);
  const { screenToFlowPosition } = useReactFlow();
  const { running, speed, setSelected, setSelectedEdge, setLatestResult, setExperimentId } = useBuilderStore();

  useEffect(() => {
    let isMounted = true;
    async function loadLatestMetrics() {
      try {
        const list = await getExperiments();
        if (!isMounted || !list || list.length === 0) return;
        const completed = list.find((e) => e.status === 'COMPLETE') || list[0];
        if (completed && completed.status === 'COMPLETE') {
          const res = await getExperimentResults(completed.experiment_id);
          if (isMounted) {
            setLatestResult(res);
            setExperimentId(res.experiment_id);
          }
        }
      } catch {
        // Backend offline or no experiments yet; metrics will display 'Unavailable'
      }
    }
    loadLatestMetrics();
    return () => {
      isMounted = false;
    };
  }, [setLatestResult, setExperimentId]);

  const removeNode = useCallback((id: string) => { setNodes((items) => items.filter((item) => item.id !== id)); setEdges((items) => items.filter((item) => item.source !== id && item.target !== id)); }, [setNodes, setEdges]);
  const updateName = useCallback((id: string, label: string) => setNodes((items) => items.map((item) => item.id === id ? { ...item, data: { ...item.data, label } } : item)), [setNodes]);
  const hydratedNodes = useMemo(() => nodes.map((node) => ({ ...node, data: { ...node.data, onDelete: removeNode, onRename: updateName, onSelect: setSelected } })), [nodes, removeNode, updateName, setSelected]);
  const hydratedEdges = useMemo(() => edges.map((edge) => ({ ...edge, data: { protocol: edge.data?.protocol || 'quic', ...edge.data, running, speed } })), [edges, running, speed]);
  const onConnect = useCallback((connection: Connection) => setEdges((items) => addEdge({ ...connection, type: 'packetEdge', data: { protocol: 'quic' } }, items)), [setEdges]);
  const onDrop = useCallback((event: React.DragEvent) => { event.preventDefault(); const type = event.dataTransfer.getData('application/netpulse-device') as DeviceType; if (!type) return; const position = screenToFlowPosition({ x: event.clientX, y: event.clientY }); const id = `${type}-${Date.now()}`; setNodes((items) => items.concat({ id, type: 'deviceNode', position, data: { type, label: `${type}-${items.length + 1}` } })); }, [screenToFlowPosition, setNodes]);
  const onAssign = useCallback((event: Event) => { const detail = (event as CustomEvent<{ id: string; protocol: Protocol }>).detail; setEdges((items) => items.map((edge) => edge.id === detail.id ? { ...edge, data: { ...edge.data, protocol: detail.protocol } } : edge)); }, [setEdges]);
  useEffect(() => { window.addEventListener('netpulse:assign-edge', onAssign); return () => window.removeEventListener('netpulse:assign-edge', onAssign); }, [onAssign]);
  return <div className="topology-builder"><DeviceToolbox /><SimulationToolbar nodes={nodes} edges={edges} /><ReactFlow nodes={hydratedNodes} edges={hydratedEdges} nodeTypes={nodeTypes} edgeTypes={edgeTypes} onNodesChange={onNodesChange} onEdgesChange={onEdgesChange} onConnect={onConnect} onNodeClick={(_, node) => setSelected(node.id)} onEdgeClick={(_, edge) => setSelectedEdge(edge.id)} onPaneClick={() => { setSelected(null); setSelectedEdge(null); }} onDrop={onDrop} onDragOver={(event) => { event.preventDefault(); event.dataTransfer.dropEffect = 'move'; }} fitView colorMode="dark"><Background color="#26304A" gap={24} size={1} /><Controls /><MiniMap nodeColor={(node) => node.data?.type === 'server' ? '#45E0B6' : node.data?.type === 'client' ? '#315BFF' : '#64749A'} maskColor="rgba(8,10,18,.82)" /></ReactFlow><div className="canvas-hint">CONNECT DEVICES BY DRAGGING FROM A PORT</div><NodeInspector nodes={nodes} edges={edges} onClose={() => { setSelected(null); setSelectedEdge(null); }} /></div>;
}

export function TopologyCanvas() { return <ReactFlowProvider><CanvasInner /></ReactFlowProvider>; }
