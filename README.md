# NetPulse

NetPulse is an interactive lab for comparing QUIC, TCP, and UDP under changing network conditions. It combines a dark, packet-tracer-style topology builder with a FastAPI experiment service and Linux-ready network hooks.

## Current status

- The frontend is fully runnable on Windows with simulated experiment metrics.
- The topology builder uses React Flow: drag devices from the palette, connect `OUT` to `IN`, click a link to assign a protocol, and run the visual simulation.
- The FastAPI service persists experiments in SQLite by default and streams metric snapshots over WebSockets.
- `network/` and `experiments/` retain the Linux/Mininet integration seams for the later WSL2 or Ubuntu run.
- The current TCP, UDP, and QUIC runner modules are clearly marked seams; they return simulation metadata until the Linux binaries and Mininet hosts are enabled.

## Project layout

```text
frontend/       Next.js dashboard, topology builder, comparison views
backend/        FastAPI API, SQLAlchemy models, async experiment runner
experiments/    TCP, UDP, QUIC runner seams and shared metrics logic
network/        Mininet topology, tc/netem hooks, condition presets
database/       Portable SQL schema for PostgreSQL/Linux deployment
```

## Windows quick start

Open two terminals from the project root.

### Backend

```powershell
$env:PYTHONPATH="backend"
python -m pip install -r backend/requirements.txt
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

### Frontend

```powershell
cd frontend
npm install
npx next dev -H 127.0.0.1 -p 3000
```

Open:

- Dashboard: http://127.0.0.1:3000
- Interactive monitor: http://127.0.0.1:3000/live-monitor
- API health: http://127.0.0.1:8000/health
- API docs: http://127.0.0.1:8000/docs

## Topology builder

1. Open Live Monitor.
2. Drag a Client, Switch, or Server from the left palette onto the canvas.
3. Drag a device's glowing `OUT` port to another device's `IN` port.
4. Click an edge and choose TCP, UDP, or QUIC in the inspector.
5. Use `RUN SIMULATION` to start packet animation and trigger the backend experiment endpoint.
6. Use the speed buttons for visual playback only; they do not change experiment timing.
7. Double-click a device to rename it. Select a node to inspect connected links.

The default `h1 -> s1 -> s2 -> h2` path is already connected. Extra visual devices are illustrative until the Mininet topology is extended to match them.

## API

| Method | Endpoint | Purpose |
| --- | --- | --- |
| GET | `/health` | Service health check |
| POST | `/experiment/start` | Validate and start an experiment |
| GET | `/experiment/status/{id}` | Read lifecycle status |
| GET | `/experiment/results/{id}` | Read persisted metrics |
| GET | `/experiments` | List experiment history |
| WS | `/ws/experiment/{id}` | Receive live metric snapshots |

Example request:

```json
{
	"protocols": ["tcp", "udp", "quic"],
	"bandwidth_mbps": 25,
	"latency_ms": 45,
	"packet_loss_pct": 1,
	"duration_sec": 10
}
```

## Linux / WSL2 handoff

The network layer is intentionally kept separate from the web dependencies. On Ubuntu or WSL2:

```bash
sudo apt update
sudo apt install -y mininet openvswitch-switch iproute2 iperf3 tcpdump
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
pip install -r experiments/requirements.txt
```

Linux-only pieces:

- `network/topology.py` defines `h1 - s1 - s2 - h2` using Mininet.
- `network/netem.py` applies bandwidth, delay, and packet-loss rules through `tc`.
- `experiments/tcp/run_tcp_test.py` is the iperf3 TCP integration point.
- `experiments/udp/run_udp_test.py` is the iperf3 UDP integration point.
- `experiments/quic/run_quic_test.py` is the aioquic integration point.

The next integration step is to replace the simulated calculations in `backend/app/services/experiment_runner.py` with calls that start the Mininet topology, apply netem to the selected interface, invoke the protocol runner, persist parsed metrics, and always reset the network in a `finally` block.

## Generated files

Do not commit `frontend/.next/`, Python `__pycache__/` folders, or `backend/netpulse.db`. The SQLite database is a local development store; PostgreSQL can be selected later with `DATABASE_URL`.
