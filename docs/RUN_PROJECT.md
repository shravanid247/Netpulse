# NetPulse Execution, Run & Operations Guide

Welcome to the **NetPulse** runtime operations guide. This document provides step-by-step instructions for starting, operating, testing, benchmarking, and troubleshooting the complete NetPulse platform.

---

## 1. Starting System Services

Ensure that both PostgreSQL and Open vSwitch are running on your Ubuntu system:

```bash
# Check service status
sudo systemctl status postgresql --no-pager
sudo systemctl status openvswitch-switch --no-pager

# If either service is stopped, start them:
sudo systemctl start postgresql
sudo systemctl start openvswitch-switch
```

---

## 2. Starting the Application

Running NetPulse requires two active terminals (one for the backend and one for the frontend).

### Terminal 1: FastAPI Backend Server

```bash
cd ~/Netpulse/backend

# Activate virtual environment
source .venv/bin/activate

# Optional: Ensure database tables are created
python3 -c "from app.db.database import create_tables; create_tables()"

# Start FastAPI with live reload on port 8000
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Verify backend health:
```bash
curl http://localhost:8000/health
# Response: {"status":"healthy","database":"connected","version":"1.0.0","service":"netpulse-backend"}
```

- **API Base URL**: `http://localhost:8000`
- **Interactive Swagger Docs**: `http://localhost:8000/docs`
- **OpenAPI JSON**: `http://localhost:8000/openapi.json`

---

### Terminal 2: Next.js Frontend Dashboard

```bash
cd ~/Netpulse/frontend

# Ensure dependencies are installed
npm install

# Start Next.js development server
npm run dev
```

Open your browser at **http://localhost:3000**.

---

## 3. Using the Web Dashboard

| Page | URL | Description & Workflow |
| :--- | :--- | :--- |
| **Overview** | `http://localhost:3000/` | High-level system overview, active configuration, quick links to other modules. |
| **Experiment Lab** | `http://localhost:3000/experiment-lab` | Visual Mininet topology canvas (`h1 ---- s1 ---- s2 ---- h2`), protocol selectors (TCP, UDP, QUIC), network preset selector, custom sliders for bandwidth/latency/loss, and execution trigger button. |
| **Live Monitor** | `http://localhost:3000/live-monitor` | Real-time WebSocket streaming telemetry during an active experiment run. Displays live throughput gauges, latency graphs, packet loss meters, and terminal execution logs. |
| **Protocol Explorer** | `http://localhost:3000/protocol-explorer` | Interactive timeline charts comparing throughput, latency, jitter, and packet loss across multiple test runs and protocols. |
| **Comparison Matrix** | `http://localhost:3000/comparison` | Side-by-side metric tables and derived comparative analytics: Throughput Efficiency (%), Throughput Ratio vs. TCP, Latency Inflation, and CPU Cost Efficiency. |
| **Research Results** | `http://localhost:3000/research-results` | Searchable experiment history table, CSV/JSON dataset export buttons, and raw JSON benchmark artifact inspection modal. |

---

## 4. Running Experiments

You can run experiments either through the **Web Dashboard UI**, via the **FastAPI REST API**, or directly using the **Privileged CLI Helper**.

---

### Method A: Via Web Dashboard (Recommended)

1. Open `http://localhost:3000/experiment-lab` in your browser.
2. Select your desired protocols: **TCP**, **UDP**, and/or **QUIC**.
3. Choose a network condition preset (e.g., **Home Broadband**, **4G LTE**, **Satellite**, **Fiber**, **Poor WAN**) OR configure custom impairment:
   - **Bandwidth**: `1.0` – `1000.0` Mbps
   - **Latency (RTT)**: `0.0` – `600.0` ms
   - **Packet Loss**: `0.0` – `15.0` %
   - **Duration**: `3` – `30` seconds
4. Click **"Run Experiment"**.
5. The dashboard will automatically transition or stream metrics to the **Live Monitor** (`/live-monitor`), recording results to PostgreSQL and writing raw JSON artifacts to `results/raw/`.

---

### Method B: Via Privileged CLI Helper (`netpulse-runner`)

The root helper can be run directly from the command line for fast manual benchmarking and scripting:

#### 1. Verify Topology Connectivity (h1 <-> h2)
```bash
sudo /usr/local/libexec/netpulse-runner --action verify
```

#### 2. Test Real Linux `tc/netem` Impairment Injection
```bash
sudo /usr/local/libexec/netpulse-runner \
  --action impairment_test \
  --bandwidth 25 \
  --latency 50 \
  --packet-loss 2
```

#### 3. Run Real TCP Experiment
```bash
sudo /usr/local/libexec/netpulse-runner \
  --action run \
  --experiment-id EXP-MANUAL-TCP \
  --protocol tcp \
  --duration 5 \
  --bandwidth 100 \
  --latency 20 \
  --packet-loss 0.5
```
Output JSON artifact is written to `results/raw/EXP-MANUAL-TCP_tcp.json`.

#### 4. Run Real UDP Experiment
```bash
sudo /usr/local/libexec/netpulse-runner \
  --action run \
  --experiment-id EXP-MANUAL-UDP \
  --protocol udp \
  --duration 5 \
  --bandwidth 50 \
  --latency 45 \
  --packet-loss 1.0
```
Output JSON artifact is written to `results/raw/EXP-MANUAL-UDP_udp.json`.

#### 5. Run Real QUIC Experiment
```bash
sudo /usr/local/libexec/netpulse-runner \
  --action run \
  --experiment-id EXP-MANUAL-QUIC \
  --protocol quic \
  --duration 5 \
  --bandwidth 100 \
  --latency 20 \
  --packet-loss 1.0
```
Output JSON artifact is written to `results/raw/EXP-MANUAL-QUIC_quic.json`.

---

### Method C: Via REST API (`curl`)

Trigger a multi-protocol experiment via the FastAPI backend:

```bash
curl -X POST http://localhost:8000/experiment/run \
  -H "Content-Type: application/json" \
  -d '{
    "protocols": ["tcp", "udp", "quic"],
    "bandwidth_mbps": 50.0,
    "latency_ms": 30.0,
    "packet_loss_pct": 1.5,
    "duration_sec": 5
  }'
```

**Response**:
```json
{
  "id": "EXP-XXXXXX",
  "status": "QUEUED",
  "protocols": ["tcp", "udp", "quic"],
  "bandwidth_mbps": 50.0,
  "latency_ms": 30.0,
  "packet_loss_pct": 1.5,
  "duration_sec": 5,
  "created_at": "..."
}
```

#### Check Experiment Status & Results:
```bash
curl http://localhost:8000/experiment/EXP-XXXXXX
```

#### Export Structured Results (CSV):
```bash
curl "http://localhost:8000/experiment/export/EXP-XXXXXX?format=csv" -o exp_results.csv
```

#### Export Structured Results (JSON):
```bash
curl "http://localhost:8000/experiment/export/EXP-XXXXXX?format=json" -o exp_results.json
```

#### Inspect Raw Protocol Benchmark Output:
```bash
curl "http://localhost:8000/experiment/raw/EXP-XXXXXX/tcp"
curl "http://localhost:8000/experiment/raw/EXP-XXXXXX/quic"
```

---

## 5. Execution Modes: Simulation vs. Real

The backend behavior is governed by the `NETPULSE_EXECUTION_MODE` variable in `.env`:

| Mode | Configuration | Description |
| :--- | :--- | :--- |
| **`simulation`** | `NETPULSE_EXECUTION_MODE=simulation` | Generates realistic, deterministic mock metrics mathematically conditioned on impairment parameters. Does **not** invoke sudo or Mininet. Useful for UI development, rapid prototyping, and automated CI pipelines. |
| **`real`** | `NETPULSE_EXECUTION_MODE=real` | Invokes `/usr/local/libexec/netpulse-runner` under scoped sudo to construct real Mininet topologies, configure `tc/netem` qdiscs, and run live `iperf3` and `aioquic` benchmarks. |

To switch modes, edit `~/Netpulse/.env` and restart the backend.

---

## 6. Running Tests

### Complete Python Test Suite
Run the full 45-test suite covering units, API routes, database models, Mininet integration, QUIC execution, and analytics:

```bash
cd ~/Netpulse/backend
source .venv/bin/activate
cd ~/Netpulse

python3 -m unittest discover -s tests
```

### Running Individual Test Modules
```bash
# 1. Unit tests for impairment presets
python3 -m unittest tests/test_presets_unit.py

# 2. Unit tests for Linux tc/netem command construction
python3 -m unittest tests/test_netem_unit.py

# 3. Pipeline integration tests (WebSocket, SQLite/Postgres fallback, REST routes)
python3 -m unittest tests/test_stage5_pipeline.py

# 4. QUIC protocol tests (TLS 1.3 cert generation, server/client handshake, loss recovery)
python3 -m unittest tests/test_stage6_quic.py

# 5. Research analytics and data export tests
python3 -m unittest tests/test_stage7_research.py

# 6. Real Mininet & tc/netem integration tests (requires root helper)
python3 -m unittest tests/test_netem_integration.py
```

### Frontend Validation & Production Build
```bash
cd ~/Netpulse/frontend

# Run ESLint
npm run lint

# Run TypeScript compilation check
npx tsc --noEmit

# Test production build
npm run build
```

---

## 7. Stopping Services & Cleanup

### Stopping Backend & Frontend
Press `Ctrl + C` in both active terminal windows.

### Cleaning Up Lingering Mininet Resources
If an experiment is interrupted unexpectedly, Mininet virtual interfaces (`s1-eth*`, `h1-eth0`) or Open vSwitch flows might remain in the Linux kernel:

```bash
# Clean Mininet state
sudo mn -c

# OR clean via the privileged helper
sudo /usr/local/libexec/netpulse-runner --action cleanup
```

### Freeing Occupied Ports
If port `8000` (FastAPI), `3000` (Next.js), or `5201` (iperf3) remains occupied:

```bash
# Find and kill process on port 8000
sudo lsof -t -i :8000 | xargs -r kill -9

# Find and kill process on port 3000
sudo lsof -t -i :3000 | xargs -r kill -9

# Terminate lingering iperf3 daemons
sudo killall -9 iperf3 2>/dev/null || true
```

---

## 8. Comprehensive Troubleshooting Matrix

| Issue | Root Cause | Diagnosis Command | Resolution |
| :--- | :--- | :--- | :--- |
| **`Connection refused` on :8000** | FastAPI backend is not running | `curl http://localhost:8000/health` | Start backend with `uvicorn app.main:app --reload --port 8000` in `backend/` venv. |
| **`PostgreSQL connection failed`** | PostgreSQL daemon is inactive or password in `.env` is incorrect | `sudo systemctl status postgresql` | Run `sudo systemctl start postgresql` and verify `DATABASE_URL` credentials in `.env`. |
| **`Mininet: Cannot find default OpenFlow controller`** | Direct `mn` command run without standalone switch configuration | `sudo mn` without flags | Use `sudo /usr/local/libexec/netpulse-runner` which configures `OVSSwitch` with `failMode="standalone"`. |
| **`sudo: /usr/local/libexec/netpulse-runner: command not found`** | Root helper has not been copied to target system location | `ls -la /usr/local/libexec/netpulse-runner` | Run `./scripts/update_helper.sh` or copy `experiments/privileged_helper.py` to `/usr/local/libexec/netpulse-runner` with `chmod 0755`. |
| **`sudo: a password is required`** | Sudoers rule is missing or user mismatch in `/etc/sudoers.d/netpulse` | `sudo -l` | Run `echo "$(id -un) ALL=(root) NOPASSWD: /usr/local/libexec/netpulse-runner, /usr/bin/mn -c" \| sudo tee /etc/sudoers.d/netpulse && sudo chmod 0440 /etc/sudoers.d/netpulse`. |
| **`Frontend CORS error` in browser console** | `CORS_ORIGIN` in `.env` does not match frontend address | Check browser DevTools console | Ensure `.env` contains `CORS_ORIGIN=http://localhost:3000` and restart backend. |
| **`ModuleNotFoundError: No module named 'aioquic'`** | Backend virtual environment is inactive or dependencies missing | `which python3` | Ensure `source .venv/bin/activate` is run and execute `pip install -r requirements.txt`. |
| **`QUIC handshake failed: certificate verify failed`** | Stale or invalid TLS certificates | Check backend logs | NetPulse automatically generates SAN-validated ephemeral certificates for `10.0.0.2`. Ensure `experiments/quic/certs.py` is present. |
| **`iperf3: error - unable to connect to server`** | Lingering iperf3 server on host or port conflict | `ps aux \| grep iperf3` | Run `sudo killall -9 iperf3` and `sudo mn -c`. |
| **`tc: Cannot find device "s1-eth2"`** | Network namespace or switch link not created yet | `ip link show` | Ensure Mininet network is started before invoking `tc` (the privileged helper handles this ordering automatically). |
