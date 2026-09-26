# NetPulse

NetPulse is an interactive, real-time network protocol benchmarking platform designed to measure and compare **TCP**, **UDP**, and **QUIC** under precisely controlled network impairment conditions (bandwidth constraints, latency, and packet loss).

It pairs a modern Next.js topology dashboard with a FastAPI experiment orchestration backend, executing real experiments over **Mininet**, **Open vSwitch (OVS)**, Linux network namespaces, and system-level benchmarking tools.

---

## Key Features & Architecture

- **Real Network Measurements**: Real TCP and UDP throughput, latency, jitter, loss, and CPU utilization measured using system `iperf3` inside isolated Mininet network namespaces.
- **Controlled Privilege Model**: FastAPI and frontend run entirely non-root; privileged network virtualization operations are delegated to a tightly scoped, root-controlled helper executable (`/usr/local/libexec/netpulse-runner`).
- **Relational Persistence**: PostgreSQL stores structured experiment runs, metric comparisons, and raw execution outputs.
- **Live WebSocket Telemetry**: Streaming real-time snapshot metrics from experiment execution to the dashboard.
- **Topology Builder**: Visual React Flow canvas supporting `h1 ---- s1 ---- s2 ---- h2` Mininet topologies.

```
┌─────────────────────────────────────────────────────────────┐
│                      Web Browser                            │
│                 (http://localhost:3000)                     │
└──────────────────────────────┬──────────────────────────────┘
                               │ HTTP / WebSocket
                               ▼
┌─────────────────────────────────────────────────────────────┐
│               FastAPI Backend (:8000)                       │
│        (Runs as unprivileged user, validates request)       │
└──────────────────────────────┬──────────────────────────────┘
                               │ Scoped sudo execution
                               ▼
┌─────────────────────────────────────────────────────────────┐
│    Root Helper: /usr/local/libexec/netpulse-runner          │
│    ├── Builds isolated Mininet (h1 ── s1 ── s2 ── h2)       │
│    ├── Spawns iperf3 server on h2                           │
│    ├── Executes iperf3 client on h1                         │
│    └── Always tears down topology in finally block          │
└──────────────┬───────────────────────────────┬──────────────┘
               │                               │
               ▼                               ▼
  ┌────────────────────────┐      ┌────────────────────────┐
  │ Raw Output Files (.json│      │  PostgreSQL Database   │
  │    in results/raw/     │      │   (metrics & status)   │
  └────────────────────────┘      └────────────────────────┘
```

---

## Quick Start (Ubuntu Linux)

For complete setup and execution details, refer to [docs/RUN_PROJECT.md](docs/RUN_PROJECT.md).

```bash
# 1. Clone repository
git clone https://github.com/Kenrich64/Netpulse.git
cd Netpulse

# 2. Run automated setup script
./scripts/install_netpulse.sh

# 3. Configure PostgreSQL password in .env
# Edit .env and update: DATABASE_URL=postgresql://netpulse_user:YOUR_PASSWORD@localhost:5432/netpulse

# 4. Start Backend Server (Terminal 1)
cd backend
source .venv/bin/activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 5. Start Frontend Dashboard (Terminal 2)
cd ../frontend
npm install
npm run dev
```

Open your browser at **http://localhost:3000**.

---

## Project Structure

```text
Netpulse/
├── backend/                  # FastAPI application & database models
│   ├── app/
│   │   ├── api/routes.py     # REST and WebSocket endpoints
│   │   ├── db/               # SQLAlchemy models and engine
│   │   ├── models/schemas.py # Pydantic request/response schemas
│   │   └── services/         # Experiment runner orchestration
│   └── requirements.txt      # Python backend dependencies
├── experiments/              # Protocol runner modules
│   ├── privileged_helper.py  # Root-controlled Mininet execution helper
│   ├── tcp/run_tcp_test.py   # Real iperf3 TCP runner
│   ├── udp/run_udp_test.py   # Real iperf3 UDP runner
│   └── quic/                 # QUIC protocol modules (Stage 4)
├── frontend/                 # Next.js 14 web application & topology canvas
├── network/                  # Mininet topology (h1-s1-s2-h2) & cleanup
├── database/                 # PostgreSQL DDL schema (schema.sql)
├── scripts/                  # Reproducible install script (install_netpulse.sh)
├── docs/                     # Guides: RUN_PROJECT.md, SETUP.md
└── results/                  # Structured test artifacts
    ├── raw/                  # Source-of-truth iperf3 JSON dumps
    ├── processed/            # Extracted metric summaries
    └── plots/                # Protocol comparison graphs
```

---

## Security & Privilege Model

Mininet requires Linux `CAP_NET_ADMIN` to manage Open vSwitch bridges, network namespaces, and virtual ethernet pairs.

To prevent security vulnerabilities:
1. **FastAPI never runs as root**.
2. Sudo privileges are never granted to user-writable scripts in project directories.
3. The privileged executable is installed to `/usr/local/libexec/netpulse-runner`, owned by `root:root` with `0755` permissions.
4. Sudoers permissions are narrowly scoped via `/etc/sudoers.d/netpulse` allowing only the exact helper executable and `mn -c`.
5. All experiment parameters (duration, bandwidth, protocol, experiment ID) are strictly validated via type checks and regular expressions before execution.

---

## Documentation Links

- [docs/RUN_PROJECT.md](docs/RUN_PROJECT.md) — Comprehensive execution and troubleshooting guide for team members.
- [docs/SETUP.md](docs/SETUP.md) — Prerequisites and system dependency installation guide.

