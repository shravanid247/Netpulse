'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  addEdge, Background, BaseEdge, Controls, Edge, EdgeProps, Handle, MiniMap,
  Node, NodeProps, Position, ReactFlow, ReactFlowProvider, useEdgesState, useNodesState,
  getBezierPath, useReactFlow, Connection,
} from '@xyflow/react';
import { Laptop, Network, Play, Pause, Server, X, Gauge, MousePointer2 } from 'lucide-react';
import { create } from 'zustand';

type Protocol = 'tcp' | 'udp' | 'quic';
type DeviceType = 'client' | 'switch' | 'server';
type DeviceData = { label: string; type: DeviceType; protocol?: Protocol; onDelete?: (id: string) => void; onRename?: (id: string, label: string) => void; onSelect?: (id: string) => void };
type PacketEdgeData = { protocol?: Protocol; running?: boolean; latency?: number; loss?: number; speed?: number; onSelect?: (id: string) => void };
type BuilderState = { selectedId: string | null; selectedEdgeId: string | null; running: boolean; speed: number; setSelected: (id: string | null) => void; setSelectedEdge: (id: string | null) => void; setRunning: (running: boolean) => void; setSpeed: (speed: number) => void };
const useBuilderStore = create<BuilderState>((set) => ({ selectedId: null, selectedEdgeId: null, running: false, speed: 1, setSelected: (selectedId) => set({ selectedId, selectedEdgeId: null }), setSelectedEdge: (selectedEdgeId) => set({ selectedEdgeId, selectedId: null }), setRunning: (running) => set({ running }), setSpeed: (speed) => set({ speed }) }));

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
  const protocol = data?.protocol;
  const color = protocol ? colors[protocol] : 'var(--color-line)';
  const running = Boolean(data?.running && protocol);
  return <>
    <BaseEdge id={id} path={path} interactionWidth={22} style={{ stroke: color, strokeWidth: selected ? 4 : protocol ? 2.5 : 1.5, filter: protocol ? `drop-shadow(0 0 8px ${color})` : undefined }} />
    {running && [0, 1, 2].map((offset) => <circle key={`${id}-${offset}`} r="4" fill={color} filter={`drop-shadow(0 0 7px ${color})`}><animateMotion dur={`${1.8 / (data?.speed || 1)}s`} begin={`${offset * .55}s`} repeatCount="indefinite" path={path} /></circle>)}
  </>;
}

const nodeTypes = { deviceNode: DeviceNode };
const edgeTypes = { packetEdge: AnimatedPacketEdge };

function DeviceToolbox() {
  const devices: { type: DeviceType; label: string; icon: typeof Laptop }[] = [{ type: 'client', label: 'Client host', icon: Laptop }, { type: 'switch', label: 'Switch', icon: Network }, { type: 'server', label: 'Server', icon: Server }];
  return <aside className="device-toolbox"><div className="toolbox-title"><span className="eyebrow">Palette</span><h3>Devices</h3></div>{devices.map(({ type, label, icon: Icon }) => <div key={type} className="toolbox-item" draggable onDragStart={(event) => { event.dataTransfer.setData('application/netpulse-device', type); event.dataTransfer.effectAllowed = 'move'; }}><Icon size={19} /><span>{label}</span><span className="drag-hint">+</span></div>)}<div className="toolbox-note"><MousePointer2 size={14} /> Drag onto canvas</div></aside>;
}

function SimulationToolbar() {
  const { running, setRunning, speed, setSpeed } = useBuilderStore();
  const startSimulation = async () => { setRunning(!running); if (!running) { try { await fetch('http://127.0.0.1:8000/experiment/start', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ protocols: ['quic'], bandwidth_mbps: 25, latency_ms: 45, packet_loss_pct: 1, duration_sec: 10 }) }); } catch { /* visual simulation remains available offline */ } } };
  return <div className="simulation-toolbar"><button className="simulation-run" onClick={startSimulation}>{running ? <Pause size={15} /> : <Play size={15} />}{running ? 'PAUSE' : 'RUN SIMULATION'}</button><span className="toolbar-divider" /><Gauge size={15} className="toolbar-icon" /><span className="toolbar-label">VISUAL SPEED</span>{[.5, 1, 2].map((value) => <button key={value} className={`speed-button ${speed === value ? 'active' : ''}`} onClick={() => setSpeed(value)}>{value}x</button>)}</div>;
}

function NodeInspector({ nodes, edges, onClose }: { nodes: Node<DeviceData>[]; edges: Edge<PacketEdgeData>[]; onClose: () => void }) {
  const { selectedId, selectedEdgeId } = useBuilderStore();
  const node = nodes.find((item) => item.id === selectedId); const edge = edges.find((item) => item.id === selectedEdgeId);
  if (!node && !edge) return null;
  const linked = node ? edges.filter((item) => item.source === node.id || item.target === node.id) : [];
  return <aside className="node-inspector"><button className="inspector-close" onClick={onClose} aria-label="Close inspector"><X size={16} /></button><span className="eyebrow">Inspector</span>{node ? <><h3>{node.data.label}</h3><span className="inspector-type">{node.data.type} device</span><div className="inspector-section"><span className="field-label">Connected links</span>{linked.length ? linked.map((item) => <div className="linked-row" key={item.id}><span>{item.source} → {item.target}</span><b style={{ color: item.data?.protocol ? colors[item.data.protocol] : 'var(--color-ink-muted)' }}>{item.data?.protocol?.toUpperCase() || 'UNASSIGNED'}</b></div>) : <p>No links connected.</p>}</div>{node.data.type === 'server' && <div className="inspector-result"><span className="field-label">Last experiment</span><strong>8.4 Mbps</strong><small>42 ms latency / 1.20% loss</small></div>}</> : <><h3>Link assignment</h3><span className="inspector-type">{edge?.source} → {edge?.target}</span><div className="protocol-assignment"><span className="field-label">Simulated protocol</span>{(['tcp', 'udp', 'quic'] as Protocol[]).map((protocol) => <button key={protocol} className={`assign-button ${edge?.data?.protocol === protocol ? 'selected' : ''}`} style={{ '--assign-color': colors[protocol] } as React.CSSProperties} onClick={() => window.dispatchEvent(new CustomEvent('netpulse:assign-edge', { detail: { id: edge?.id, protocol } }))}>{protocol.toUpperCase()}</button>)}</div></>}</aside>;
}

function CanvasInner() {
  const [nodes, setNodes, onNodesChange] = useNodesState<Node<DeviceData>>(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge<PacketEdgeData>>(initialEdges);
  const { screenToFlowPosition } = useReactFlow();
  const { running, speed, setSelected, setSelectedEdge } = useBuilderStore();
  const removeNode = useCallback((id: string) => { setNodes((items) => items.filter((item) => item.id !== id)); setEdges((items) => items.filter((item) => item.source !== id && item.target !== id)); }, [setNodes, setEdges]);
  const updateName = useCallback((id: string, label: string) => setNodes((items) => items.map((item) => item.id === id ? { ...item, data: { ...item.data, label } } : item)), [setNodes]);
  const hydratedNodes = useMemo(() => nodes.map((node) => ({ ...node, data: { ...node.data, onDelete: removeNode, onRename: updateName, onSelect: setSelected } })), [nodes, removeNode, updateName, setSelected]);
  const hydratedEdges = useMemo(() => edges.map((edge) => ({ ...edge, data: { ...edge.data, running, speed } })), [edges, running, speed]);
  const onConnect = useCallback((connection: Connection) => setEdges((items) => addEdge({ ...connection, type: 'packetEdge', data: {} }, items)), [setEdges]);
  const onDrop = useCallback((event: React.DragEvent) => { event.preventDefault(); const type = event.dataTransfer.getData('application/netpulse-device') as DeviceType; if (!type) return; const position = screenToFlowPosition({ x: event.clientX, y: event.clientY }); const id = `${type}-${Date.now()}`; setNodes((items) => items.concat({ id, type: 'deviceNode', position, data: { type, label: `${type}-${items.length + 1}` } })); }, [screenToFlowPosition, setNodes]);
  const onAssign = useCallback((event: Event) => { const detail = (event as CustomEvent<{ id: string; protocol: Protocol }>).detail; setEdges((items) => items.map((edge) => edge.id === detail.id ? { ...edge, data: { ...edge.data, protocol: detail.protocol } } : edge)); }, [setEdges]);
  useEffect(() => { window.addEventListener('netpulse:assign-edge', onAssign); return () => window.removeEventListener('netpulse:assign-edge', onAssign); }, [onAssign]);
  return <div className="topology-builder"><DeviceToolbox /><SimulationToolbar /><ReactFlow nodes={hydratedNodes} edges={hydratedEdges} nodeTypes={nodeTypes} edgeTypes={edgeTypes} onNodesChange={onNodesChange} onEdgesChange={onEdgesChange} onConnect={onConnect} onNodeClick={(_, node) => setSelected(node.id)} onEdgeClick={(_, edge) => setSelectedEdge(edge.id)} onPaneClick={() => { setSelected(null); setSelectedEdge(null); }} onDrop={onDrop} onDragOver={(event) => { event.preventDefault(); event.dataTransfer.dropEffect = 'move'; }} fitView colorMode="dark"><Background color="#26304A" gap={24} size={1} /><Controls /><MiniMap nodeColor={(node) => node.data?.type === 'server' ? '#45E0B6' : node.data?.type === 'client' ? '#315BFF' : '#64749A'} maskColor="rgba(8,10,18,.82)" /></ReactFlow><div className="canvas-hint">CONNECT DEVICES BY DRAGGING FROM A PORT</div><NodeInspector nodes={nodes} edges={edges} onClose={() => { setSelected(null); setSelectedEdge(null); }} /></div>;
}

export function TopologyCanvas() { return <ReactFlowProvider><CanvasInner /></ReactFlowProvider>; }
