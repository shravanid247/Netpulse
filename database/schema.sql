CREATE TABLE IF NOT EXISTS experiments (
  id VARCHAR(32) PRIMARY KEY,
  status VARCHAR(16) NOT NULL,
  protocols TEXT NOT NULL,
  bandwidth_mbps DOUBLE PRECISION NOT NULL,
  latency_ms DOUBLE PRECISION NOT NULL,
  packet_loss_pct DOUBLE PRECISION NOT NULL,
  duration_sec INTEGER NOT NULL,
  error TEXT,
  raw_result_path TEXT,
  created_at TIMESTAMP WITH TIME ZONE NOT NULL,
  completed_at TIMESTAMP WITH TIME ZONE
);

CREATE TABLE IF NOT EXISTS results (
  id SERIAL PRIMARY KEY,
  experiment_id VARCHAR(32) NOT NULL REFERENCES experiments(id),
  protocol VARCHAR(8) NOT NULL,
  throughput_mbps DOUBLE PRECISION NOT NULL,
  latency_ms DOUBLE PRECISION NOT NULL,
  jitter_ms DOUBLE PRECISION,
  packet_loss_pct DOUBLE PRECISION NOT NULL,
  cpu_usage_pct DOUBLE PRECISION NOT NULL,
  transfer_time_sec DOUBLE PRECISION NOT NULL,
  handshake_success BOOLEAN,
  raw_output TEXT
);

