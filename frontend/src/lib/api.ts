/**
 * NetPulse Typed Frontend API Client
 * Centralizes all communication with the FastAPI backend.
 */

export type Protocol = 'tcp' | 'udp' | 'quic';
export type NodeType = 'client' | 'switch' | 'server';

export interface TopologyNode {
  id: string;
  label: string;
  type: NodeType;
}

export interface TopologyEdge {
  id: string;
  source: string;
  target: string;
  protocol?: Protocol | null;
  bandwidth_mbps?: number | null;
  latency_ms?: number | null;
  packet_loss_pct?: number | null;
}

export interface TopologySpec {
  nodes: TopologyNode[];
  edges: TopologyEdge[];
}

export interface ExperimentConfig {
  protocols: Protocol[];
  bandwidth_mbps: number;
  latency_ms: number;
  packet_loss_pct: number;
  duration_sec: number;
  topology?: TopologySpec;
}

export interface PresetItem {
  bandwidth_mbps: number;
  latency_ms: number;
  packet_loss_pct: number;
}

export interface ResultResponse {
  protocol: Protocol;
  throughput_mbps: number;
  latency_ms: number;
  jitter_ms: number | null;
  packet_loss_pct: number;
  cpu_usage_pct: number;
  transfer_time_sec: number;
  handshake_success: boolean | null;
  raw_output?: string | null;
}

export interface ExperimentResponse {
  experiment_id: string;
  status: 'PENDING' | 'RUNNING' | 'COMPLETE' | 'FAILED';
  config: ExperimentConfig;
  results: ResultResponse[];
  raw_result_path?: string | null;
  error?: string | null;
}

export interface ProtocolMetrics {
  protocol: Protocol;
  throughput_mbps: number;
  latency_ms: number;
  jitter_ms: number | null;
  packet_loss_pct: number;
  cpu_usage_pct: number;
  transfer_time_sec: number;
  handshake_success: boolean | null;
  throughput_efficiency_pct: number | null;
  throughput_ratio_vs_tcp: number | null;
  latency_inflation_pct: number | null;
  cpu_cost_per_mbps: number | null;
}

export interface ComparisonSummary {
  fastest_protocol: string | null;
  lowest_latency_protocol: string | null;
  most_cpu_efficient: string | null;
  protocol_count: number;
  notes: string[];
}

export interface ComparisonResponse {
  experiment_id: string;
  status: string;
  config: ExperimentConfig;
  protocols: Record<string, ProtocolMetrics>;
  summary: ComparisonSummary;
}

export interface ExperimentSummaryItem {
  experiment_id: string;
  status: string;
  protocols: string[];
  bandwidth_mbps?: number | null;
  latency_ms?: number | null;
  packet_loss_pct?: number | null;
  duration_sec?: number | null;
  created_at?: string | null;
  completed_at?: string | null;
  results_summary?: Array<{
    protocol: string;
    throughput_mbps: number;
    latency_ms: number;
    packet_loss_pct: number;
    cpu_usage_pct: number;
    handshake_success?: boolean | null;
  }>;
}

export const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000';

async function fetchJson<T>(path: string, options?: RequestInit): Promise<T> {
  const url = `${API_BASE}${path}`;
  const response = await fetch(url, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
      ...options?.headers,
    },
  });

  if (!response.ok) {
    let errorDetail = `Request failed: ${response.status} ${response.statusText}`;
    try {
      const errJson = await response.json();
      if (errJson && errJson.detail) {
        errorDetail = errJson.detail;
      }
    } catch {
      // Ignore text parse errors
    }
    throw new Error(errorDetail);
  }

  return response.json() as Promise<T>;
}

export async function getPresets(): Promise<Record<string, PresetItem>> {
  return fetchJson<Record<string, PresetItem>>('/presets');
}

export async function startExperiment(config: ExperimentConfig): Promise<{ experiment_id: string; status: string }> {
  return fetchJson<{ experiment_id: string; status: string }>('/experiment/start', {
    method: 'POST',
    body: JSON.stringify(config),
  });
}

export async function getExperimentStatus(experimentId: string): Promise<{ experiment_id: string; status: string; error?: string | null }> {
  return fetchJson<{ experiment_id: string; status: string; error?: string | null }>(`/experiment/status/${encodeURIComponent(experimentId)}`);
}

export async function getExperimentResults(experimentId: string): Promise<ExperimentResponse> {
  return fetchJson<ExperimentResponse>(`/experiment/results/${encodeURIComponent(experimentId)}`);
}

export async function getExperiments(): Promise<ExperimentSummaryItem[]> {
  return fetchJson<ExperimentSummaryItem[]>('/experiments');
}

export async function getComparison(experimentId: string): Promise<ComparisonResponse> {
  return fetchJson<ComparisonResponse>(`/experiment/compare/${encodeURIComponent(experimentId)}`);
}

export function getExportUrl(experimentId: string, format: 'csv' | 'json' = 'csv'): string {
  return `${API_BASE}/experiment/export/${encodeURIComponent(experimentId)}?format=${format}`;
}

export async function getRawResult(experimentId: string, protocol: string): Promise<Record<string, unknown>> {
  return fetchJson<Record<string, unknown>>(`/experiment/raw/${encodeURIComponent(experimentId)}/${encodeURIComponent(protocol)}`);
}
