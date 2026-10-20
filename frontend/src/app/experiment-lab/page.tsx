'use client';

import { useState, useEffect, useRef } from 'react';
import Link from 'next/link';
import { ArrowUpRight, Play, Loader2, AlertCircle, CheckCircle2, Sliders } from 'lucide-react';
import { RouteShell } from '@/components/RouteShell';
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
  average: { label: 'Average', detail: 'Typical home broadband', color: '#E7C766', values: [25, 45, 1] },
  poor: { label: 'Poor', detail: 'Congested mobile link', color: '#315BFF', values: [10, 100, 5] },
  very_poor: { label: 'Very Poor', detail: 'Edge case stress test', color: '#E06A8B', values: [2, 220, 12] },
  satellite: { label: 'Satellite', detail: 'High latency path', color: '#B37FFF', values: [20, 600, 3] },
  lossy_iot: { label: 'Lossy IoT', detail: 'High drop link', color: '#FF7373', values: [1, 150, 8] },
};

export default function ExperimentLabPage() {
  const [protocols, setProtocols] = useState<Protocol[]>(['tcp', 'quic']);
  const [bandwidth, setBandwidth] = useState<number>(25);
  const [latency, setLatency] = useState<number>(45);
  const [loss, setLoss] = useState<number>(1);
  const [duration, setDuration] = useState<number>(5);
  const [selectedPreset, setSelectedPreset] = useState<string>('average');

  const [status, setStatus] = useState<'IDLE' | 'PENDING' | 'RUNNING' | 'COMPLETE' | 'FAILED'>('IDLE');
  const [experimentId, setExperimentId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ExperimentResponse | null>(null);

  const pollRef = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  const toggleProtocol = (proto: Protocol) => {
    if (protocols.includes(proto)) {
      if (protocols.length > 1) {
        setProtocols(protocols.filter((p) => p !== proto));
      }
    } else {
      setProtocols([...protocols, proto]);
    }
  };

  const applyPreset = (key: string) => {
    setSelectedPreset(key);
    if (DEFAULT_PRESETS[key]) {
      const v = DEFAULT_PRESETS[key].values;
      setBandwidth(v[0]);
      setLatency(v[1]);
      setLoss(v[2]);
    }
  };

  const handleRun = async () => {
    if (status === 'PENDING' || status === 'RUNNING') return;
    setStatus('PENDING');
    setError(null);
    setResult(null);

    const config: ExperimentConfig = {
      protocols,
      bandwidth_mbps: bandwidth,
      latency_ms: latency,
      packet_loss_pct: loss,
      duration_sec: duration,
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
          } else if (s.status === 'COMPLETE') {
            if (pollRef.current) clearInterval(pollRef.current);
            setStatus('COMPLETE');
            const data = await getExperimentResults(res.experiment_id);
            setResult(data);
          } else if (s.status === 'FAILED') {
            if (pollRef.current) clearInterval(pollRef.current);
            setStatus('FAILED');
            setError(s.error || 'Experiment execution failed');
          }
        } catch (pollErr: unknown) {
          console.error('Polling error:', pollErr);
        }
      }, 1000);
    } catch (err: unknown) {
      setStatus('FAILED');
      setError(err instanceof Error ? err.message : 'Failed to start experiment');
    }
  };

  return (
    <RouteShell active="/experiment-lab" title="LAB" eyebrow="Experimental Control & Configuration / 02">
      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1.4fr) minmax(0, 1fr)', gap: 18 }}>
        {/* Left Column: Configuration Controls */}
        <div className="workbench">
          <div className="section-head">
            <div>
              <span className="eyebrow">Parameters</span>
              <h3 style={{ margin: 0, fontSize: 18 }}>Network Impairment Setup</h3>
            </div>
            <span className="mono tiny">STATUS: {status}</span>
          </div>

          {/* Protocols */}
          <div className="protocol-row">
            <span className="field-label">Target Protocols</span>
            {(['tcp', 'udp', 'quic'] as const).map((proto) => (
              <button
                key={proto}
                type="button"
                onClick={() => toggleProtocol(proto)}
                className={`protocol-chip ${protocols.includes(proto) ? 'selected' : ''} ${proto}`}
              >
                <i />
                {proto.toUpperCase()}
              </button>
            ))}
          </div>

          {/* Presets */}
          <div className="preset-row">
            <span className="field-label">Condition Profiles</span>
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

          {/* Custom Sliders */}
          <div className="sliders" style={{ gridTemplateColumns: 'repeat(2, 1fr)', gap: 20 }}>
            <label>
              <span>
                Bandwidth <b className="mono">{bandwidth} Mbps</b>
              </span>
              <input
                type="range"
                min="1"
                max="100"
                value={bandwidth}
                onChange={(e) => {
                  setBandwidth(Number(e.target.value));
                  setSelectedPreset('');
                }}
              />
            </label>

            <label>
              <span>
                Latency <b className="mono">{latency} ms</b>
              </span>
              <input
                type="range"
                min="0"
                max="300"
                value={latency}
                onChange={(e) => {
                  setLatency(Number(e.target.value));
                  setSelectedPreset('');
                }}
              />
            </label>

            <label>
              <span>
                Packet Loss <b className="mono">{loss} %</b>
              </span>
              <input
                type="range"
                min="0"
                max="20"
                value={loss}
                onChange={(e) => {
                  setLoss(Number(e.target.value));
                  setSelectedPreset('');
                }}
              />
            </label>

            <label>
              <span>
                Duration <b className="mono">{duration} s</b>
              </span>
              <input
                type="range"
                min="1"
                max="30"
                value={duration}
                onChange={(e) => setDuration(Number(e.target.value))}
              />
            </label>
          </div>

          {/* Launch Button */}
          <button
            type="button"
            className={`run-button ${status === 'RUNNING' || status === 'PENDING' ? 'running' : ''}`}
            onClick={handleRun}
            disabled={status === 'RUNNING' || status === 'PENDING'}
          >
            <span>
              {status === 'PENDING'
                ? 'INITIALIZING...'
                : status === 'RUNNING'
                ? 'BENCHMARK IN PROGRESS...'
                : 'START EXPERIMENT RUN'}
            </span>
            <b>
              {status === 'RUNNING' || status === 'PENDING' ? (
                <Loader2 className="animate-spin" size={18} />
              ) : (
                '↗'
              )}
            </b>
          </button>
        </div>

        {/* Right Column: Execution Monitor & Real-Time Results */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          {/* Status Panel */}
          <div className="route-panel">
            <span className="eyebrow">Execution Monitor</span>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', margin: '14px 0' }}>
              <span className={`badge badge-${status.toLowerCase()}`}>{status}</span>
              {experimentId && <span className="mono" style={{ fontSize: 13 }}>{experimentId}</span>}
            </div>

            {error && (
              <div style={{ padding: 10, background: 'rgba(224,106,139,.1)', border: '1px solid var(--color-error)', color: 'var(--color-error)', fontSize: 12 }}>
                <AlertCircle size={14} style={{ display: 'inline', marginRight: 6 }} />
                {error}
              </div>
            )}

            {!error && status === 'IDLE' && (
              <p>Configure network parameters and select protocols to begin an experiment.</p>
            )}

            {!error && (status === 'PENDING' || status === 'RUNNING') && (
              <p>
                Virtual network link conditions applied via Linux tc/netem. Benchmarking traffic is actively traversing the Mininet path.
              </p>
            )}

            {result && status === 'COMPLETE' && (
              <div style={{ marginTop: 12 }}>
                <p style={{ color: 'var(--color-success)', marginBottom: 12 }}>
                  ✓ Experiment completed. Results persisted to database.
                </p>
                <div style={{ display: 'flex', gap: 8 }}>
                  <Link
                    href={`/comparison?id=${result.experiment_id}`}
                    className="btn-action"
                    style={{ flex: 1, justifyContent: 'center' }}
                  >
                    View Comparison Charts <ArrowUpRight size={13} />
                  </Link>
                  <Link
                    href="/research-results"
                    className="btn-action"
                    style={{ flex: 1, justifyContent: 'center' }}
                  >
                    All Results Archive
                  </Link>
                </div>
              </div>
            )}
          </div>

          {/* Result Telemetry Table */}
          {result && (
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Protocol</th>
                    <th>Throughput</th>
                    <th>Latency</th>
                    <th>Loss</th>
                    <th>CPU</th>
                  </tr>
                </thead>
                <tbody>
                  {result.results.map((r) => (
                    <tr key={r.protocol}>
                      <td>
                        <b className="mono">{r.protocol.toUpperCase()}</b>
                      </td>
                      <td className="mono">{r.throughput_mbps.toFixed(2)} Mbps</td>
                      <td className="mono">{r.latency_ms > 0 ? `${r.latency_ms.toFixed(1)} ms` : '—'}</td>
                      <td className="mono">{r.packet_loss_pct.toFixed(2)}%</td>
                      <td className="mono">{r.cpu_usage_pct.toFixed(1)}%</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </RouteShell>
  );
}
