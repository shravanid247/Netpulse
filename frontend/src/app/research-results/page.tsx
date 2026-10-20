'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { Download, Eye, BarChart2, RefreshCw, X, AlertCircle } from 'lucide-react';
import { RouteShell } from '@/components/RouteShell';
import {
  ExperimentSummaryItem,
  getExperiments,
  getExportUrl,
  getRawResult,
} from '@/lib/api';

const STATUS_CLASS: Record<string, string> = {
  COMPLETE: 'badge-complete',
  RUNNING: 'badge-running',
  PENDING: 'badge-pending',
  FAILED: 'badge-failed',
};

const PROTO_COLORS: Record<string, string> = {
  tcp: '#4BC7FF',
  udp: '#E06A8B',
  quic: '#315BFF',
};

export default function ResearchResultsPage() {
  const [experiments, setExperiments] = useState<ExperimentSummaryItem[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Raw modal inspection state
  const [modalOpen, setModalOpen] = useState<boolean>(false);
  const [rawContent, setRawContent] = useState<string>('');
  const [modalTitle, setModalTitle] = useState<string>('');
  const [rawLoading, setRawLoading] = useState<boolean>(false);

  const fetchList = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getExperiments();
      setExperiments(data);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to load experiments');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchList();
  }, []);

  const openRawModal = async (experimentId: string, protocol: string) => {
    setModalTitle(`${experimentId} (${protocol.toUpperCase()}) Raw Benchmark Output`);
    setModalOpen(true);
    setRawLoading(true);
    setRawContent('');
    try {
      const data = await getRawResult(experimentId, protocol);
      setRawContent(JSON.stringify(data, null, 2));
    } catch (err: unknown) {
      setRawContent(err instanceof Error ? `Error loading raw artifact: ${err.message}` : 'Failed to load artifact');
    } finally {
      setRawLoading(false);
    }
  };

  return (
    <RouteShell active="/research-results" title="RESULTS" eyebrow="Experiment Archive & Research Datasets / 06">
      {/* Header toolbar */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 18 }}>
        <div>
          <span className="eyebrow" style={{ marginBottom: 4 }}>Relational Archive</span>
          <span className="mono tiny">POSTGRESQL / STORED EXPERIMENTS</span>
        </div>
        <button className="btn-action" onClick={fetchList} disabled={loading}>
          <RefreshCw size={13} className={loading ? 'animate-spin' : ''} /> Refresh Archive
        </button>
      </div>

      {error && (
        <div className="route-panel" style={{ borderColor: 'var(--color-error)', marginBottom: 18 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--color-error)' }}>
            <AlertCircle size={18} />
            <strong>Failed to retrieve archive: {error}</strong>
          </div>
        </div>
      )}

      {/* Main Experiment Table */}
      <div className="table-wrap">
        <table className="data-table">
          <thead>
            <tr>
              <th>Experiment ID</th>
              <th>Status</th>
              <th>Protocols</th>
              <th>Network Condition</th>
              <th>Summary Metrics</th>
              <th>Timestamp</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr>
                <td colSpan={7} style={{ textAlign: 'center', padding: 32 }}>
                  Loading experiment archive...
                </td>
              </tr>
            )}

            {!loading && experiments.length === 0 && (
              <tr>
                <td colSpan={7} style={{ textAlign: 'center', padding: 32 }}>
                  No experiments recorded yet.{' '}
                  <Link href="/experiment-lab" style={{ color: 'var(--color-primary)', textDecoration: 'underline' }}>
                    Run an experiment now
                  </Link>
                </td>
              </tr>
            )}

            {!loading &&
              experiments.map((exp) => (
                <tr key={exp.experiment_id}>
                  {/* ID */}
                  <td>
                    <b className="mono">{exp.experiment_id}</b>
                  </td>

                  {/* Status Badge */}
                  <td>
                    <span className={`badge ${STATUS_CLASS[exp.status] || 'badge-pending'}`}>
                      {exp.status}
                    </span>
                  </td>

                  {/* Protocols */}
                  <td>
                    <div style={{ display: 'flex', gap: 5, flexWrap: 'wrap' }}>
                      {exp.protocols.map((p) => (
                        <span
                          key={p}
                          className="mono"
                          style={{
                            fontSize: 10,
                            padding: '2px 5px',
                            background: 'var(--color-bg-raised)',
                            border: `1px solid ${PROTO_COLORS[p] || 'var(--color-line)'}`,
                            color: PROTO_COLORS[p] || 'var(--color-ink)',
                          }}
                        >
                          {p.toUpperCase()}
                        </span>
                      ))}
                    </div>
                  </td>

                  {/* Network Condition */}
                  <td className="mono" style={{ fontSize: 11 }}>
                    {exp.bandwidth_mbps !== undefined && exp.bandwidth_mbps !== null ? (
                      <>
                        {exp.bandwidth_mbps}M / {exp.latency_ms}ms / {exp.packet_loss_pct}% loss
                        <br />
                        <small style={{ color: 'var(--color-ink-muted)' }}>{exp.duration_sec}s duration</small>
                      </>
                    ) : (
                      '—'
                    )}
                  </td>

                  {/* Summary Metrics */}
                  <td>
                    {exp.results_summary && exp.results_summary.length > 0 ? (
                      <div style={{ display: 'flex', flexDirection: 'column', gap: 3, fontSize: 11 }}>
                        {exp.results_summary.map((r) => (
                          <div key={r.protocol} className="mono" style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                            <span style={{ color: PROTO_COLORS[r.protocol] || 'var(--color-ink)', fontWeight: 600 }}>
                              {r.protocol.toUpperCase()}:
                            </span>
                            <span>{r.throughput_mbps.toFixed(1)} Mbps</span>
                            <small style={{ color: 'var(--color-ink-muted)' }}>
                              ({r.latency_ms > 0 ? `${r.latency_ms.toFixed(0)}ms` : '0ms'})
                            </small>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <span style={{ color: 'var(--color-ink-muted)' }}>—</span>
                    )}
                  </td>

                  {/* Date / Time */}
                  <td className="mono" style={{ fontSize: 11, color: 'var(--color-ink-muted)' }}>
                    {exp.created_at ? new Date(exp.created_at).toLocaleString() : '—'}
                  </td>

                  {/* Actions */}
                  <td>
                    <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                      <Link
                        href={`/comparison?id=${exp.experiment_id}`}
                        className="btn-action"
                        title="View comparative charts"
                      >
                        <BarChart2 size={12} /> Compare
                      </Link>

                      <a
                        href={getExportUrl(exp.experiment_id, 'csv')}
                        download
                        className="btn-action"
                        title="Download CSV report"
                      >
                        <Download size={12} /> CSV
                      </a>

                      <a
                        href={getExportUrl(exp.experiment_id, 'json')}
                        download
                        className="btn-action"
                        title="Download JSON dataset"
                      >
                        <Download size={12} /> JSON
                      </a>

                      {/* Raw Artifact inspector for each protocol */}
                      {exp.protocols.map((p) => (
                        <button
                          key={p}
                          className="btn-action"
                          onClick={() => openRawModal(exp.experiment_id, p)}
                          title={`Inspect raw JSON for ${p.toUpperCase()}`}
                        >
                          <Eye size={12} /> {p.toUpperCase()} Raw
                        </button>
                      ))}
                    </div>
                  </td>
                </tr>
              ))}
          </tbody>
        </table>
      </div>

      {/* Aggregate Statistics Footer */}
      <div className="route-grid" style={{ marginTop: 18 }}>
        <div className="route-panel">
          <span className="eyebrow">Archived Runs</span>
          <strong className="metric">{experiments.length}</strong>
          <p>Historical benchmark runs stored in PostgreSQL database.</p>
        </div>

        <div className="route-panel">
          <span className="eyebrow">Completed Successfully</span>
          <strong className="metric">
            {experiments.filter((e) => e.status === 'COMPLETE').length}
          </strong>
          <p>Experiments available for cross-protocol comparison and export.</p>
        </div>

        <div className="route-panel">
          <span className="eyebrow">Export Formats</span>
          <strong className="metric">CSV / JSON</strong>
          <p>Standards-compliant structured datasets ready for research reports.</p>
        </div>
      </div>

      {/* Raw Output Modal */}
      {modalOpen && (
        <div className="modal-backdrop" onClick={() => setModalOpen(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <span className="eyebrow" style={{ margin: 0 }}>
                {modalTitle}
              </span>
              <button
                className="btn-action"
                onClick={() => setModalOpen(false)}
                aria-label="Close modal"
              >
                <X size={15} />
              </button>
            </div>
            <div className="modal-body">
              {rawLoading ? 'Loading raw benchmark JSON...' : rawContent}
            </div>
          </div>
        </div>
      )}
    </RouteShell>
  );
}
