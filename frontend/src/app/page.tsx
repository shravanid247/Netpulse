'use client';

import { useState, useEffect, useRef } from 'react';
import Link from 'next/link';
import { ArrowUpRight, CheckCircle2, AlertCircle, Loader2, Play, Pause } from 'lucide-react';
import { TopologyCanvas } from '@/components/topology-builder/TopologyCanvas';
import {
  ExperimentConfig,
  ExperimentResponse,
  PresetItem,
  Protocol,
  getExperimentResults,
  getExperimentStatus,
  getPresets,
  startExperiment,
} from '@/lib/api';

const DEFAULT_PRESETS: Record<string, { label: string; detail: string; color: string; values: [number, number, number] }> = {
  excellent: { label: 'Excellent', detail: 'Clean fiber link', color: '#45E0B6', values: [100, 8, 0] },
  average: { label: 'Average', detail: 'Typical home network', color: '#E7C766', values: [25, 45, 1] },
  poor: { label: 'Poor', detail: 'Congested mobile link', color: '#315BFF', values: [10, 100, 5] },
  very_poor: { label: 'Very Poor', detail: 'Edge case stress test', color: '#E06A8B', values: [2, 220, 12] },
};

const NAV_LINKS = [
  ['01', 'Dashboard', '/'],
  ['02', 'Experiment lab', '/experiment-lab'],
  ['03', 'Live monitor', '/live-monitor'],
  ['04', 'Comparison', '/comparison'],
  ['05', 'Protocols', '/protocol-explorer'],
  ['06', 'Research results', '/research-results'],
];

export default function Dashboard() {
  // Protocol selection (supports multi-protocol)
  const [selectedProtocols, setSelectedProtocols] = useState<Protocol[]>(['quic']);

  // Network condition sliders: [bandwidth_mbps, latency_ms, packet_loss_pct, duration_sec]
  const [values, setValues] = useState<[number, number, number, number]>([25, 45, 1, 5]);
  const [selectedPreset, setSelectedPreset] = useState<string>('average');
  const [availablePresets, setAvailablePresets] = useState<Record<string, PresetItem>>({});

  // Experiment execution lifecycle state
  const [experimentId, setExperimentId] = useState<string | null>(null);
  const [status, setStatus] = useState<'IDLE' | 'PENDING' | 'RUNNING' | 'COMPLETE' | 'FAILED'>('IDLE');
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [experimentResult, setExperimentResult] = useState<ExperimentResponse | null>(null);

  const pollIntervalRef = useRef<NodeJS.Timeout | null>(null);

  // Load backend presets dynamically on mount
  useEffect(() => {
    async function loadPresets() {
      try {
        const presets = await getPresets();
        setAvailablePresets(presets);
      } catch (err: unknown) {
        console.warn('Using default presets (backend unreachable):', err);
      }
    }
    loadPresets();
  }, []);

  // Cleanup polling on unmount
  useEffect(() => {
    return () => {
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current);
      }
    };
  }, []);

  const toggleProtocol = (proto: Protocol) => {
    if (selectedProtocols.includes(proto)) {
      if (selectedProtocols.length > 1) {
        setSelectedProtocols(selectedProtocols.filter((p) => p !== proto));
      }
    } else {
      setSelectedProtocols([...selectedProtocols, proto]);
    }
  };

  const applyPreset = (key: string) => {
    setSelectedPreset(key);
    const preset = availablePresets[key];
    if (preset) {
      setValues([preset.bandwidth_mbps, preset.latency_ms, preset.packet_loss_pct, values[3]]);
    } else if (DEFAULT_PRESETS[key]) {
      const v = DEFAULT_PRESETS[key].values;
      setValues([v[0], v[1], v[2], values[3]]);
    }
  };

  const handleStartExperiment = async () => {
    if (status === 'PENDING' || status === 'RUNNING') {
      return;
    }

    setStatus('PENDING');
    setErrorMessage(null);
    setExperimentResult(null);

    const config: ExperimentConfig = {
      protocols: selectedProtocols,
      bandwidth_mbps: values[0],
      latency_ms: values[1],
      packet_loss_pct: values[2],
      duration_sec: values[3],
    };

    try {
      const startRes = await startExperiment(config);
      const expId = startRes.experiment_id;
      setExperimentId(expId);
      setStatus('PENDING');

      // Poll status until completion
      pollIntervalRef.current = setInterval(async () => {
        try {
          const statusRes = await getExperimentStatus(expId);
          if (statusRes.status === 'RUNNING') {
            setStatus('RUNNING');
          } else if (statusRes.status === 'COMPLETE') {
            if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
            setStatus('COMPLETE');
            const res = await getExperimentResults(expId);
            setExperimentResult(res);
          } else if (statusRes.status === 'FAILED') {
            if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
            setStatus('FAILED');
            setErrorMessage(statusRes.error || 'Experiment execution failed');
          }
        } catch (pollErr: unknown) {
          console.error('Polling error:', pollErr);
        }
      }, 1000);
    } catch (startErr: unknown) {
      setStatus('FAILED');
      setErrorMessage(startErr instanceof Error ? startErr.message : 'Failed to start experiment');
    }
  };

  // Compute primary throughput for display
  const primaryResult = experimentResult?.results[0];
  const peakThroughput = experimentResult
    ? Math.max(...experimentResult.results.map((r) => r.throughput_mbps))
    : null;

  return (
    <main className="app-shell">
      {/* Sidebar Navigation */}
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark">N</span>
          <span>NETPULSE</span>
        </div>
        <nav>
          {NAV_LINKS.map(([number, label, href]) => (
            <Link key={href} className={`nav-link ${href === '/' ? 'active' : ''}`} href={href}>
              <span>{number}</span>
              {label}
            </Link>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="system-status">
            <i /> System ready
          </div>
          <span className="mono tiny">v1.0.0 / PROTOCOL LAB</span>
        </div>
      </aside>

      {/* Main Content Area */}
      <div className="content">
        <header className="topbar">
          <span>NETWORK PERFORMANCE ANALYSIS</span>
          <span className="mono">REAL TRANSPORT BENCHMARKING</span>
        </header>

        {/* Hero Banner */}
        <section className="hero">
          <div>
            <span className="eyebrow">Interactive protocol laboratory</span>
            <h1>
              NET<span>PULSE</span>
            </h1>
            <p>
              Evaluate real TCP, UDP, and QUIC transport behavior across Linux Mininet namespaces and controlled network impairments.
            </p>
          </div>
          <div className="hero-stamp">
            <strong>03</strong>
            <span>
              protocols
              <br />
              under test
            </span>
          </div>
        </section>

        {/* Workbench Grid */}
        <section className="dashboard-grid">
          <div className="workbench">
            <div className="section-head">
              <div>
                <span className="eyebrow">Experiment lab / 01</span>
                <h2>Configure &amp; Execute Run</h2>
              </div>
              <span className="mono tiny">
                {status === 'IDLE' ? 'READY' : status}
              </span>
            </div>

            {/* Protocol Multi-Selector */}
            <div className="protocol-row">
              <span className="field-label">Target Protocols (Click to toggle)</span>
              {(['tcp', 'udp', 'quic'] as const).map((item) => (
                <button
                  key={item}
                  type="button"
                  onClick={() => toggleProtocol(item)}
                  className={`protocol-chip ${selectedProtocols.includes(item) ? 'selected' : ''} ${item}`}
                >
                  <i />
                  {item.toUpperCase()}
                </button>
              ))}
            </div>

            {/* Preset Row */}
            <div className="preset-row">
              <span className="field-label">Network Presets</span>
              {Object.entries(DEFAULT_PRESETS).map(([key, preset]) => (
                <button
                  key={key}
                  type="button"
                  onClick={() => applyPreset(key)}
                  className={`preset ${selectedPreset === key ? 'selected' : ''}`}
                >
                  <i style={{ background: preset.color }} />
                  <strong>{preset.label}</strong>
                  <small>{preset.detail}</small>
                </button>
              ))}
            </div>

            {/* Sliders */}
            <div className="sliders">
              <label>
                <span>
                  Bandwidth <b className="mono">{values[0]} Mbps</b>
                </span>
                <input
                  type="range"
                  min="1"
                  max="100"
                  value={values[0]}
                  onChange={(e) => {
                    setValues([Number(e.target.value), values[1], values[2], values[3]]);
                    setSelectedPreset('');
                  }}
                />
              </label>

              <label>
                <span>
                  Latency <b className="mono">{values[1]} ms</b>
                </span>
                <input
                  type="range"
                  min="0"
                  max="300"
                  value={values[1]}
                  onChange={(e) => {
                    setValues([values[0], Number(e.target.value), values[2], values[3]]);
                    setSelectedPreset('');
                  }}
                />
              </label>

              <label>
                <span>
                  Packet Loss <b className="mono">{values[2]} %</b>
                </span>
                <input
                  type="range"
                  min="0"
                  max="20"
                  value={values[2]}
                  onChange={(e) => {
                    setValues([values[0], values[1], Number(e.target.value), values[3]]);
                    setSelectedPreset('');
                  }}
                />
              </label>
            </div>

            {/* Run Button */}
            <button
              type="button"
              className={`run-button ${status === 'RUNNING' || status === 'PENDING' ? 'running' : ''}`}
              onClick={handleStartExperiment}
              disabled={status === 'RUNNING' || status === 'PENDING'}
            >
              <span>
                {status === 'PENDING'
                  ? 'LAUNCHING EXPERIMENT...'
                  : status === 'RUNNING'
                  ? 'EXECUTING REAL BENCHMARK...'
                  : 'RUN EXPERIMENT'}
              </span>
              <b>
                {status === 'RUNNING' || status === 'PENDING' ? (
                  <Loader2 className="animate-spin" size={20} />
                ) : (
                  '↗'
                )}
              </b>
            </button>

            {/* Execution status banner */}
            {experimentId && (
              <div style={{ marginTop: 14, padding: '10px 14px', background: 'var(--color-bg-raised)', border: '1px solid var(--color-line)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span className={`badge badge-${status.toLowerCase()}`}>{status}</span>
                  <span className="mono" style={{ fontSize: 12 }}>{experimentId}</span>
                </div>
                {status === 'COMPLETE' && (
                  <Link
                    href={`/comparison?id=${experimentId}`}
                    style={{ color: 'var(--color-primary)', fontSize: 11, fontFamily: 'DM Mono', display: 'flex', alignItems: 'center', gap: 4 }}
                  >
                    View Full Comparison <ArrowUpRight size={13} />
                  </Link>
                )}
              </div>
            )}

            {errorMessage && (
              <div style={{ marginTop: 10, padding: 10, background: 'rgba(224,106,139,.1)', border: '1px solid var(--color-error)', color: 'var(--color-error)', fontSize: 12 }}>
                <AlertCircle size={14} style={{ display: 'inline', marginRight: 6 }} />
                {errorMessage}
              </div>
            )}
          </div>

          {/* Real Telemetry Insight Panel */}
          <div className="insight-panel">
            <span className="eyebrow">Real Telemetry / Signal</span>
            <div className="big-number">
              {status === 'COMPLETE' && peakThroughput !== null
                ? peakThroughput.toFixed(1)
                : status === 'RUNNING'
                ? '...'
                : '—'}
              <small>Mbps</small>
            </div>
            <p>
              {status === 'COMPLETE' && experimentResult
                ? `Run finished successfully across ${experimentResult.results.length} protocol(s). Full comparative telemetry is ready.`
                : status === 'RUNNING'
                ? 'Mininet hosts are streaming benchmark data through the configured bottleneck link.'
                : 'Run an experiment above to measure real transport throughput and latency under impairment.'}
            </p>

            {/* Mini Bar Preview when completed */}
            {experimentResult && (
              <div style={{ margin: '15px 0', borderTop: '1px solid rgba(0,0,0,0.15)', paddingTop: 12 }}>
                {experimentResult.results.map((r) => (
                  <div key={r.protocol} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, fontFamily: 'DM Mono', marginBottom: 4 }}>
                    <span>{r.protocol.toUpperCase()}:</span>
                    <b>{r.throughput_mbps.toFixed(2)} Mbps ({r.latency_ms > 0 ? `${r.latency_ms.toFixed(1)}ms` : '0ms'})</b>
                  </div>
                ))}
              </div>
            )}

            <div className="insight-meta">
              <span>Execution State</span>
              <span className="mono">{status}</span>
            </div>
          </div>
        </section>

        {/* Topology Section */}
        <section className="builder-section" style={{ marginTop: 32 }}>
          <div className="section-head">
            <div>
              <span className="eyebrow">Topology builder / 02</span>
              <h2>Design the packet path</h2>
            </div>
            <span className="mono tiny">MININET / H1 - S1 - S2 - H2</span>
          </div>
          <TopologyCanvas />
        </section>
      </div>
    </main>
  );
}
