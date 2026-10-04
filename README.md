# NetPulse

NetPulse is an interactive, real-time network protocol benchmarking platform designed to measure, compare, and analyze **TCP**, **UDP**, and **QUIC** under precisely controlled network impairment conditions (bandwidth constraints, latency injection, and packet loss).

It combines a modern Next.js topology dashboard with an asynchronous FastAPI experiment orchestration backend, executing real experiments over **Mininet**, **Open vSwitch (OVS)**, Linux network namespaces, and system-level benchmarking tools.

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        Web Browser (Next.js 14)                         │
│                         http://localhost:3000                           │
│  ├── Topology Builder (React Flow Canvas)                               │
│  ├── Live Monitor (WebSocket Metric Streaming)                          │
│  ├── Protocol Explorer (Timeline & Impairment Charts)                   │
│  ├── Comparison Matrix (Efficiency, Inflation & CPU Ratios)             │
│  └── Research Results (CSV/JSON Export & Raw JSON Viewer)               │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │ HTTP (REST) / WebSocket (:8000)
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                        FastAPI Backend (:8000)                          │
│         (Runs as unprivileged user, validates request parameters)       │
│  ├── REST API (/experiment/run, /presets, /experiments, /export, /raw)  │
│  ├── WebSocket Server (/ws/metrics/{id})                                │
│  ├── Comparative Analytics Engine (app/services/analytics.py)           │
│  └── SQLAlchemy ORM with PostgreSQL (:5432)                             │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │ Scoped sudo execution
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│         Root Helper: /usr/local/libexec/netpulse-runner                 │
│  ├── Builds isolated Mininet network (h1 ── s1 ── s2 ── h2)             │
│  ├── Applies Linux tc/netem qdiscs on inter-switch link (s1-eth2)       │
│  ├── Measures ICMP ping baseline, latency, and packet loss              │
│  ├── Executes real iperf3 server on h2, client on h1 (TCP / UDP)        │
│  ├── Executes real aioquic server on h2, client on h1 (QUIC)            │
│  └── Always tears down topology and resets tc qdiscs in finally block   │
└───────────────────┬─────────────────────────────────┬───────────────────┘
                    │                                 │
                    ▼                                 ▼
       ┌────────────────────────┐        ┌────────────────────────┐
       │ Raw Output Files (.json│        │  PostgreSQL Database   │
       │    in results/raw/     │        │   (metrics & status)   │
       └────────────────────────┘        └────────────────────────┘
```

---

## Key Features

- **Multi-Protocol Benchmarking**:
  - **TCP**: Throughput (Mbps), retransmissions, CPU utilization, transfer time via `iperf3`.
  - **UDP**: Throughput, jitter (ms), packet loss (%), CPU utilization via `iperf3`.
  - **QUIC**: Ephemeral TLS 1.3 handshake, 0-RTT/1-RTT connection time, stream throughput, CPU utilization via `aioquic`.
- **Precise Traffic Impairment via Linux `tc/netem`**:
  - Symmetric inter-switch bottleneck impairment (`s1-eth2` and `s2-eth1`).
  - Configurable bandwidth constraints (0.01 – 10,000 Mbps).
  - Configurable round-trip latency injection (0 – 10,000 ms).
  - Configurable packet loss rates (0 – 100%).
- **Standardized Network Presets**:
  - Predefined real-world network profiles: Fiber (500M / 2ms / 0%), 4G LTE (30M / 50ms / 1.5%), Home Broadband (25M / 45ms / 1%), Satellite (20M / 600ms / 3%), Lossy IoT (1M / 150ms / 8%), and standard grades (Excellent, Average, Poor, Very Poor).
- **Interactive Topology Builder**:
  - Visual React Flow canvas supporting `h1 ---- s1 ---- s2 ---- h2` Mininet topologies.
  - Interactive host and switch configuration with protocol selectors.
- **Live WebSocket Telemetry**:
  - Streaming real-time snapshot metrics from experiment execution directly to browser charts.
- **Comparative Research Analytics**:
  - Automated calculation of throughput efficiency (`throughput / bottleneck_bandwidth * 100`).
  - Protocol throughput ratio vs. TCP baseline (`protocol_throughput / tcp_throughput`).
  - Latency inflation factor (`measured_latency / configured_target_latency`).
  - CPU cost efficiency (`throughput_mbps / cpu_usage_pct`).
- **Structured Data Export & Raw Artifacts**:
  - Downloadable CSV and JSON research datasets (`/experiment/export/{id}?format=csv|json`).
  - Direct raw JSON benchmark output viewer (`/experiment/raw/{id}/{protocol}`).
- **Secure Privilege Model**:
  - FastAPI backend and Next.js frontend run entirely as regular, non-root users.
  - Root access is strictly restricted to a single compiled/installed helper executable (`/usr/local/libexec/netpulse-runner`) and `mn -c` via `/etc/sudoers.d/netpulse`.

---

## Technology Stack

| Layer | Technologies |
| :--- | :--- |
| **Frontend** | Next.js 14 (App Router), React 18, TypeScript, Tailwind CSS, Lucide React, Recharts, React Flow (`@xyflow/react`), Zustand, Framer Motion |
| **Backend** | FastAPI, Uvicorn, SQLAlchemy 2, Pydantic v2, PostgreSQL (`psycopg2-binary`), Python Dotenv |
| **Networking & Simulation** | Mininet 2.3+, Open vSwitch (OVS), Linux Traffic Control (`tc` / `netem`), `iperf3`, `aioquic`, `cryptography` (X.509 TLS 1.3) |
| **Database** | PostgreSQL 14+ |

---

## Quick Start (Ubuntu Linux / Ubuntu VM)

For detailed first-time and team setup instructions, refer to:
- [docs/TEAM_SETUP.md](docs/TEAM_SETUP.md) — **Team 5-Person Setup & Workflow Guide**
- [docs/SETUP.md](docs/SETUP.md) — **Fresh Machine Prerequisites & Installation**
- [docs/RUN_PROJECT.md](docs/RUN_PROJECT.md) — **Execution, Testing & Troubleshooting Guide**

```bash
# 1. Clone repository
git clone https://github.com/Kenrich64/Netpulse.git ~/Netpulse
cd ~/Netpulse

# 2. Run automated setup script (configures venv, dependencies, .env, and root helper)
./scripts/install_netpulse.sh

# 3. Configure PostgreSQL password in .env (if not using defaults)
# Edit .env and update: DATABASE_URL=postgresql://netpulse_user:YOUR_PASSWORD@localhost:5432/netpulse

# 4. Initialize Database Schema
cd ~/Netpulse/backend
source .venv/bin/activate
python3 -c "from app.db.database import create_tables; create_tables(); print('Database tables ready!')"

# 5. Start Backend Server (Terminal 1)
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 6. Start Frontend Dashboard (Terminal 2)
cd ~/Netpulse/frontend
npm install
npm run dev
```

Open your browser at **http://localhost:3000**.

---

## Running the Dashboard

Once both services are running:

| Page | URL | Purpose |
| :--- | :--- | :--- |
| **Home / Overview** | `http://localhost:3000/` | System status, architecture summary, quick run launcher |
| **Topology Builder / Lab** | `http://localhost:3000/experiment-lab` | Visual network topology, parameter configuration, preset selector, and execution trigger |
| **Live Monitor** | `http://localhost:3000/live-monitor` | Real-time WebSocket streaming telemetry and execution logs |
| **Protocol Explorer** | `http://localhost:3000/protocol-explorer` | Multi-protocol performance comparisons across bandwidth, latency, and loss |
| **Comparison Matrix** | `http://localhost:3000/comparison` | Detailed side-by-side metric tables and derived efficiency analytics |
| **Research Results** | `http://localhost:3000/research-results` | Historic experiment table, CSV/JSON export, and raw JSON artifact viewer |
| **API Documentation** | `http://localhost:8000/docs` | Interactive FastAPI Swagger documentation |

---

## Running Tests

From the repository root:

```bash
# Activate backend virtual environment
cd ~/Netpulse/backend
source .venv/bin/activate
cd ~/Netpulse

# 1. Run Complete Python Test Suite (45 tests: unit + integration)
python3 -m unittest discover -s tests

# 2. Run Unit Tests Only (does not require root helper)
python3 -m unittest tests/test_presets_unit.py tests/test_netem_unit.py

# 3. Run Stage 5, 6, and 7 Integration Tests
python3 -m unittest tests/test_stage5_pipeline.py tests/test_stage6_quic.py tests/test_stage7_research.py

# 4. Frontend Linting & Type Checking (Terminal 2)
cd ~/Netpulse/frontend
npm run lint
npx tsc --noEmit
npm run build
```

---

## Repository Structure

```text
Netpulse/
├── backend/                  # FastAPI backend application
│   ├── app/
│   │   ├── api/routes.py     # REST endpoints & WebSocket handlers
│   │   ├── db/               # SQLAlchemy database engine and ORM models
│   │   ├── models/schemas.py # Pydantic v2 validation schemas
│   │   └── services/         # Experiment orchestrator & analytics engine
│   └── requirements.txt      # Python backend dependencies
├── database/                 # PostgreSQL schema definition
│   └── schema.sql            # Table definitions (experiments, results)
├── docs/                     # Project documentation
│   ├── TEAM_SETUP.md         # 5-person team setup and collaboration guide
│   ├── SETUP.md              # Fresh Ubuntu & VM installation guide
│   └── RUN_PROJECT.md        # Comprehensive runtime execution & debugging guide
├── experiments/              # Protocol benchmarking modules
│   ├── privileged_helper.py  # Root-owned Mininet & tc/netem execution helper
│   ├── tcp/run_tcp_test.py   # Real TCP benchmark runner
│   ├── udp/run_udp_test.py   # Real UDP benchmark runner
│   ├── quic/                 # QUIC protocol modules (server, client, certs, runner)
│   └── requirements.txt      # Protocol runner dependencies
├── frontend/                 # Next.js 14 web dashboard
│   ├── src/app/              # Next.js App Router pages
│   ├── src/components/       # UI components & topology canvas
│   └── package.json          # Frontend npm dependencies
├── network/                  # Mininet network configuration
│   ├── topology.py           # 2-host, 2-switch Mininet topology builder
│   ├── netem.py              # Traffic control qdisc helper
│   └── presets.py            # Predefined impairment profiles
├── results/                  # Test artifacts storage
│   ├── raw/                  # Source-of-truth JSON dumps
│   ├── processed/            # Aggregated metric summaries
│   └── plots/                # Comparison charts and graphs
├── scripts/                  # Automation scripts
│   ├── install_netpulse.sh   # One-step automated installer
│   └── update_helper.sh      # Privileged helper update script
├── tests/                    # Comprehensive unit and integration test suite
├── .env.example              # Template environment configuration
└── README.md                 # Project overview and quick start
```

---

## Security & Scoped Sudo Model

Mininet and Linux Traffic Control require `CAP_NET_ADMIN` to manage Open vSwitch bridges, network namespaces, and virtual ethernet pairs.

To maintain system security:
1. **FastAPI never runs as root**.
2. Sudo privileges are **never** granted to user-writable scripts in project directories.
3. The privileged executable is installed to `/usr/local/libexec/netpulse-runner`, owned by `root:root` with `0755` permissions.
4. Sudoers permissions are narrowly scoped via `/etc/sudoers.d/netpulse` allowing only the exact helper executable and `mn -c`.
5. All experiment parameters (duration, bandwidth, protocol, experiment ID) are strictly validated via type checks and regular expressions before execution.
6. Ephemeral TLS certificates used for QUIC experiments are generated dynamically with SAN validation and cleaned up immediately after testing.
