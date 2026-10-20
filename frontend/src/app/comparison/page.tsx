'use client';

import { useEffect, useState, useMemo, Suspense } from 'react';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Legend,
  CartesianGrid,
  Cell,
} from 'recharts';
import { Download, RefreshCw, AlertCircle, ArrowUpRight, CheckCircle2 } from 'lucide-react';
import { RouteShell } from '@/components/RouteShell';
import {
  ComparisonResponse,
  ExperimentSummaryItem,
  getComparison,
  getExperiments,
  getExportUrl,
} from '@/lib/api';

const PROTO_COLORS: Record<string, string> = {
  tcp: '#4BC7FF',
  udp: '#E06A8B',
  quic: '#315BFF',
};

function ComparisonContent() {
  const searchParams = useSearchParams();
  const queryId = searchParams.get('id');

  const [experiments, setExperiments] = useState<ExperimentSummaryItem[]>([]);
  const [selectedId, setSelectedId] = useState<string>(queryId || '');
  const [comparison, setComparison] = useState<ComparisonResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Load experiment list once on mount
  useEffect(() => {
    async function loadList() {
      try {
        const list = await getExperiments();
        setExperiments(list);
        // Seed initial selection only if no ID was provided via URL
        if (!queryId && list.length > 0) {
          const firstCompleted = list.find((e) => e.status === 'COMPLETE') || list[0];
          setSelectedId(firstCompleted.experiment_id);
        }
      } catch (err: unknown) {
        console.error('Failed to load experiments list:', err);
      }
    }
    loadList();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Load comparison data when selectedId changes
  useEffect(() => {
    if (!selectedId) {
      setLoading(false);
      return;
    }
    let isCancelled = false;
    async function loadComparison() {
      setLoading(true);
      setError(null);
      try {
        const data = await getComparison(selectedId);
        if (!isCancelled) {
          setComparison(data);
        }
      } catch (err: unknown) {
        if (!isCancelled) {
          setError(err instanceof Error ? err.message : 'Failed to load comparison');
          setComparison(null);
        }
      } finally {
        if (!isCancelled) {
          setLoading(false);
        }
      }
    }
    loadComparison();
    return () => {
      isCancelled = true;
    };
  }, [selectedId]);

  // Format chart data
  const chartData = useMemo(() => {
    if (!comparison) return [];
    return Object.entries(comparison.protocols).map(([proto, metrics]) => ({
      protocol: proto.toUpperCase(),
      rawProto: proto,
      throughput: metrics.throughput_mbps,
      latency: metrics.latency_ms,
      packet_loss: metrics.packet_loss_pct,
      cpu_usage: metrics.cpu_usage_pct,
      jitter: metrics.jitter_ms ?? 0,
      efficiency: metrics.throughput_efficiency_pct ?? 0,
      ratio_vs_tcp: metrics.throughput_ratio_vs_tcp ?? 1.0,
      cpu_cost: metrics.cpu_cost_per_mbps ?? 0,
    }));
  }, [comparison]);

  return (
    <RouteShell active="/comparison" title="COMPARE" eyebrow="Multi-Protocol Research Analysis / 04">
      {/* Header controls: experiment selector & export actions */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 12, marginBottom: 20 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span className="field-label" style={{ width: 'auto', margin: 0 }}>Select Experiment:</span>
          <select
            className="select-input"
            value={selectedId}
            onChange={(e) => setSelectedId(e.target.value)}
          >
            {experiments.map((exp) => (
              <option key={exp.experiment_id} value={exp.experiment_id}>
                {exp.experiment_id} ({exp.protocols.map((p) => p.toUpperCase()).join(', ')}) — {exp.status}
              </option>
            ))}
          </select>
        </div>

        {selectedId && (
          <div style={{ display: 'flex', gap: 8 }}>
            <a
              href={getExportUrl(selectedId, 'csv')}
              download
              className="btn-action"
              title="Download research CSV"
            >
              <Download size={13} /> Export CSV
            </a>
            <a
              href={getExportUrl(selectedId, 'json')}
              download
              className="btn-action"
              title="Download research JSON"
            >
              <Download size={13} /> Export JSON
            </a>
          </div>
        )}
      </div>

      {loading && (
        <div className="route-panel" style={{ textAlign: 'center', padding: 40 }}>
          <p>Loading comparative analytics for {selectedId}...</p>
        </div>
      )}

      {error && (
        <div className="route-panel" style={{ borderColor: 'var(--color-error)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--color-error)' }}>
            <AlertCircle size={18} />
            <strong>Comparison Error: {error}</strong>
          </div>
          <p style={{ marginTop: 8 }}>
            Ensure the experiment has completed successfully. If you just launched a run, wait for completion in the Experiment Lab.
          </p>
        </div>
      )}

      {!loading && !error && comparison && (
        <>
          {/* Executive Metrics Overview */}
          <div className="route-grid" style={{ marginBottom: 20 }}>
            <div className="route-panel">
              <span className="eyebrow">Peak Throughput</span>
              <strong className="metric">
                {comparison.summary.fastest_protocol
                  ? `${comparison.protocols[comparison.summary.fastest_protocol]?.throughput_mbps ?? '—'} `
                  : '—'}
                <small style={{ fontSize: 14, fontFamily: 'DM Mono' }}>Mbps</small>
              </strong>
              <p>
                Winner: <b style={{ color: PROTO_COLORS[comparison.summary.fastest_protocol || ''] || 'var(--color-ink)' }}>
                  {comparison.summary.fastest_protocol?.toUpperCase() || 'N/A'}
                </b>
              </p>
            </div>

            <div className="route-panel">
              <span className="eyebrow">Lowest Observed Latency</span>
              <strong className="metric">
                {comparison.summary.lowest_latency_protocol
                  ? `${comparison.protocols[comparison.summary.lowest_latency_protocol]?.latency_ms ?? '—'} `
                  : '—'}
                <small style={{ fontSize: 14, fontFamily: 'DM Mono' }}>ms</small>
              </strong>
              <p>
                Leader: <b style={{ color: PROTO_COLORS[comparison.summary.lowest_latency_protocol || ''] || 'var(--color-ink)' }}>
                  {comparison.summary.lowest_latency_protocol?.toUpperCase() || 'N/A'}
                </b>
              </p>
            </div>

            <div className="route-panel">
              <span className="eyebrow">Computational Efficiency</span>
              <strong className="metric">
                {comparison.summary.most_cpu_efficient
                  ? `${comparison.protocols[comparison.summary.most_cpu_efficient]?.cpu_cost_per_mbps ?? '—'} `
                  : '—'}
                <small style={{ fontSize: 14, fontFamily: 'DM Mono' }}>% CPU/Mbps</small>
              </strong>
              <p>
                Most efficient: <b style={{ color: PROTO_COLORS[comparison.summary.most_cpu_efficient || ''] || 'var(--color-ink)' }}>
                  {comparison.summary.most_cpu_efficient?.toUpperCase() || 'N/A'}
                </b>
              </p>
            </div>
          </div>

          {/* Side-by-Side Visual Comparison Charts */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(360px, 1fr))', gap: 16, marginBottom: 20 }}>
            {/* Chart 1: Throughput */}
            <div className="chart-card">
              <h4>
                <span>Throughput Comparison</span>
                <span className="mono tiny">Megabits / sec</span>
              </h4>
              <div style={{ width: '100%', height: 240 }}>
                <ResponsiveContainer>
                  <BarChart data={chartData} margin={{ top: 10, right: 10, left: -10, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--color-line)" />
                    <XAxis dataKey="protocol" stroke="var(--color-ink-muted)" tick={{ fill: 'var(--color-ink-muted)', fontSize: 11, fontFamily: 'DM Mono' }} />
                    <YAxis stroke="var(--color-ink-muted)" tick={{ fill: 'var(--color-ink-muted)', fontSize: 11, fontFamily: 'DM Mono' }} unit="M" />
                    <Tooltip
                      contentStyle={{ background: 'var(--color-bg-alt)', borderColor: 'var(--color-line)', color: 'var(--color-ink)', font: '11px DM Mono' }}
                    />
                    <Bar dataKey="throughput" name="Throughput (Mbps)">
                      {chartData.map((entry) => (
                        <Cell key={`cell-${entry.rawProto}`} fill={PROTO_COLORS[entry.rawProto] || 'var(--color-primary)'} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>

            {/* Chart 2: Latency & CPU */}
            <div className="chart-card">
              <h4>
                <span>Latency & CPU Overhead</span>
                <span className="mono tiny">ms &amp; % Utilization</span>
              </h4>
              <div style={{ width: '100%', height: 240 }}>
                <ResponsiveContainer>
                  <BarChart data={chartData} margin={{ top: 10, right: 10, left: -10, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--color-line)" />
                    <XAxis dataKey="protocol" stroke="var(--color-ink-muted)" tick={{ fill: 'var(--color-ink-muted)', fontSize: 11, fontFamily: 'DM Mono' }} />
                    <YAxis stroke="var(--color-ink-muted)" tick={{ fill: 'var(--color-ink-muted)', fontSize: 11, fontFamily: 'DM Mono' }} />
                    <Tooltip
                      contentStyle={{ background: 'var(--color-bg-alt)', borderColor: 'var(--color-line)', color: 'var(--color-ink)', font: '11px DM Mono' }}
                    />
                    <Legend wrapperStyle={{ fontSize: 11, fontFamily: 'DM Mono' }} />
                    <Bar dataKey="latency" name="Latency (ms)" fill="#E7C766" />
                    <Bar dataKey="cpu_usage" name="CPU Usage (%)" fill="#45E0B6" />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
          </div>

          {/* Structured Comparative Analysis Table */}
          <div className="table-wrap" style={{ marginBottom: 20 }}>
            <table className="data-table">
              <thead>
                <tr>
                  <th>Protocol</th>
                  <th>Throughput</th>
                  <th>Latency</th>
                  <th>Jitter</th>
                  <th>Packet Loss</th>
                  <th>CPU Usage</th>
                  <th>Transfer Time</th>
                  <th>Throughput Efficiency</th>
                  <th>Ratio vs TCP</th>
                  <th>CPU Cost</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(comparison.protocols).map(([proto, m]) => (
                  <tr key={proto}>
                    <td>
                      <b style={{ color: PROTO_COLORS[proto] || 'var(--color-ink)' }}>{proto.toUpperCase()}</b>
                    </td>
                    <td className="mono">{m.throughput_mbps.toFixed(2)} Mbps</td>
                    <td className="mono">{m.latency_ms > 0 ? `${m.latency_ms.toFixed(2)} ms` : '—'}</td>
                    <td className="mono">{m.jitter_ms !== null ? `${m.jitter_ms.toFixed(2)} ms` : 'N/A'}</td>
                    <td className="mono">{m.packet_loss_pct !== null ? `${m.packet_loss_pct.toFixed(2)}%` : 'N/A'}</td>
                    <td className="mono">{m.cpu_usage_pct.toFixed(2)}%</td>
                    <td className="mono">{m.transfer_time_sec.toFixed(2)} s</td>
                    <td className="mono">
                      {m.throughput_efficiency_pct !== null ? `${m.throughput_efficiency_pct.toFixed(1)}%` : '—'}
                    </td>
                    <td className="mono">
                      {m.throughput_ratio_vs_tcp !== null ? `${m.throughput_ratio_vs_tcp.toFixed(2)}x` : '—'}
                    </td>
                    <td className="mono">
                      {m.cpu_cost_per_mbps !== null ? `${m.cpu_cost_per_mbps.toFixed(3)}` : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Research Observations & Injected Conditions */}
          <div className="route-panel">
            <span className="eyebrow">Research Analysis &amp; Observations</span>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 20 }}>
              <div>
                <h3 style={{ margin: '0 0 10px' }}>Injected Network Impairment</h3>
                <p>
                  <b>Configured Bandwidth:</b> {comparison.config.bandwidth_mbps} Mbps<br />
                  <b>Configured Delay:</b> {comparison.config.latency_ms} ms<br />
                  <b>Configured Packet Loss:</b> {comparison.config.packet_loss_pct}%<br />
                  <b>Duration:</b> {comparison.config.duration_sec} seconds
                </p>
              </div>

              <div>
                <h3 style={{ margin: '0 0 10px' }}>Experimental Takeaways</h3>
                <ul style={{ paddingLeft: 18, margin: 0, color: 'var(--color-ink-muted)', fontSize: 13, lineHeight: 1.6 }}>
                  {comparison.summary.notes.map((note, index) => (
                    <li key={index}>{note}</li>
                  ))}
                  {comparison.summary.notes.length === 0 && (
                    <li>No significant performance deviations recorded under baseline link conditions.</li>
                  )}
                </ul>
              </div>
            </div>
          </div>
        </>
      )}

      {!loading && !comparison && !error && (
        <div className="route-panel" style={{ textAlign: 'center', padding: 48 }}>
          <p>No experiments available for comparison yet.</p>
          <Link href="/experiment-lab" className="btn-action" style={{ marginTop: 12 }}>
            Go to Experiment Lab ↗
          </Link>
        </div>
      )}
    </RouteShell>
  );
}

export default function ComparisonPage() {
  return (
    <Suspense
      fallback={
        <RouteShell
          active="/comparison"
          title="COMPARE"
          eyebrow="Multi-Protocol Research Analysis / 04"
        >
          <div className="route-panel" style={{ textAlign: 'center', padding: 48 }}>
            <p>Loading comparative analytics...</p>
          </div>
        </RouteShell>
      }
    >
      <ComparisonContent />
    </Suspense>
  );
}
