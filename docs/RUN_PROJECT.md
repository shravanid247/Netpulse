# NetPulse Project Execution & Run Guide

Welcome to **NetPulse** — an automated network protocol benchmarking platform designed to measure and compare real **TCP**, **UDP**, and **QUIC** performance across controlled virtual topologies using Mininet, Open vSwitch, and system-level measurement tools.

---

## Quick Start for Team Members

If your system already has the prerequisites installed (Ubuntu with Python 3, PostgreSQL, Mininet, Open vSwitch, iperf3):

```bash
# 1. Clone repository
git clone https://github.com/Kenrich64/Netpulse.git
cd Netpulse

# 2. Run automated setup script (configures venv, dependencies, .env, and helper)
./scripts/install_netpulse.sh

# 3. Configure your database password in .env
# Edit .env and update DATABASE_URL with your PostgreSQL password:
# DATABASE_URL=postgresql://netpulse_user:YOUR_PASSWORD@localhost:5432/netpulse

# 4. Initialize Database Schema
cd backend
source .venv/bin/activate
python3 -c "from app.db.database import create_tables; create_tables(); print('Database tables created successfully!')"

# 5. Start Backend Server (Terminal 1)
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 6. Start Frontend Dashboard (Terminal 2)
cd ../frontend
npm install
npm run dev
```

Open your browser at **http://localhost:3000** to interact with NetPulse.

---

## Detailed Step-by-Step Guide

---

### A. System Requirements

NetPulse executes **real network namespaces** and **Open vSwitch virtual networks**, requiring a Linux kernel with network isolation capabilities.

- **Operating System**: Ubuntu 22.04 LTS or 24.04 LTS (recommended).
- **Python**: Python 3.10+ (tested on Python 3.10–3.14).
- **Database**: PostgreSQL 14+ with `psycopg2` support.
- **Networking Tools**:
  - Mininet (`mn` 2.3.0+)
  - Open vSwitch (`openvswitch-switch` / `ovs-vsctl`)
  - iperf3 (`iperf3` 3.9+)
  - Linux Traffic Control (`tc` / `iproute2`)
- **Frontend Environment**: Node.js 18+ and `npm`.

> [!NOTE]
> **Windows Users**: Native Windows cannot run Linux network namespaces or Mininet. Windows users must run NetPulse inside an **Ubuntu Virtual Machine** (e.g. VirtualBox, VMware) or a Linux secondary boot. WSL2 requires custom kernel compilation for Open vSwitch and is not recommended over a standard VM.

---

### B. Clone the Project

```bash
git clone https://github.com/Kenrich64/Netpulse.git
cd Netpulse
```

---

### C. Check System Dependencies

Verify all required command-line utilities:

```bash
python3 --version     # Expected: Python 3.10+
git --version         # Expected: git version 2.x+
psql --version        # Expected: psql (PostgreSQL) 14+
mn --version          # Expected: 2.3.0 or higher
ovs-vsctl --version   # Expected: ovs-vsctl (Open vSwitch) 2.17+ / 3.x+
iperf3 --version      # Expected: iperf 3.x+
tc -V                 # Expected: tc utility, iproute2-ss...
ip -V                 # Expected: ip utility, iproute2-ss...
```

If any tool is missing, install the required packages:
```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip git postgresql mininet openvswitch-switch iperf3 iproute2
```

---

### D. Database Setup

Configure a local PostgreSQL database and user:

1. **Log in to PostgreSQL as superuser**:
   ```bash
   sudo -u postgres psql
   ```

2. **Create the user and database** (replace `CHANGE_ME` with your preferred secure password):
   ```sql
   CREATE USER netpulse_user WITH PASSWORD 'CHANGE_ME';
   CREATE DATABASE netpulse OWNER netpulse_user;
   GRANT ALL PRIVILEGES ON DATABASE netpulse TO netpulse_user;
   \c netpulse
   GRANT ALL ON SCHEMA public TO netpulse_user;
   \q
   ```

3. **Configure connection string in `.env`**:
   Copy `.env.example` to `.env` if not already present:
   ```bash
   cp .env.example .env
   ```
   Update `DATABASE_URL` in `.env`:
   ```ini
   DATABASE_URL=postgresql://netpulse_user:CHANGE_ME@localhost:5432/netpulse
   ```

4. **Initialize tables**:
   ```bash
   cd backend
   source .venv/bin/activate
   python3 -c "from app.db.database import create_tables; create_tables(); print('Tables ready!')"
   ```

---

### E. Backend Setup

```bash
cd backend

# Create and activate Python virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install backend dependencies
pip install --upgrade pip
pip install -r requirements.txt
```

---

### F. Privilege & NetPulse Runner Setup

#### Security Architecture
- **FastAPI runs as your regular non-root user**.
- Privileged operations (creating network namespaces, Open vSwitch bridges, and virtual ethernet pairs) are delegated to a single root-owned helper executable located outside user directories at `/usr/local/libexec/netpulse-runner`.
- Sudo access is strictly restricted to that single binary and the Mininet cleanup utility.

#### Installation of the Privileged Helper
```bash
# 1. Install root-owned helper
sudo mkdir -p /usr/local/libexec
sudo cp experiments/privileged_helper.py /usr/local/libexec/netpulse-runner
sudo chown root:root /usr/local/libexec/netpulse-runner
sudo chmod 0755 /usr/local/libexec/netpulse-runner

# 2. Grant scoped sudo permission for your current user
echo "$(id -un) ALL=(root) NOPASSWD: /usr/local/libexec/netpulse-runner, /usr/bin/mn -c" | sudo tee /etc/sudoers.d/netpulse
sudo chmod 0440 /etc/sudoers.d/netpulse

# 3. Validate sudoers syntax
sudo visudo -c -f /etc/sudoers.d/netpulse
```

---

### G. Basic Network Test

Verify that Mininet can instantiate the 2-host, 2-switch virtual network topology:

```bash
sudo /usr/local/libexec/netpulse-runner --action verify
```

**Expected JSON output**:
```json
{
  "success": true,
  "action": "verify",
  "ping_loss": 0.0,
  "nodes": [
    "h1",
    "h2",
    "s1",
    "s2"
  ]
}
```

---

### H. Run Real TCP Experiment

Execute a real TCP throughput test over the Mininet topology:

```bash
sudo /usr/local/libexec/netpulse-runner --action run --experiment-id manual_tcp_01 --protocol tcp --duration 5 --bandwidth 100
```

- **Raw JSON output location**: `results/raw/manual_tcp_01_tcp.json`
- **Output metrics**: Throughput (Mbps), Retransmissions, CPU utilization, Transfer time.

---

### I. Run Real UDP Experiment

Execute a real UDP test measuring bandwidth, jitter, and packet loss:

```bash
sudo /usr/local/libexec/netpulse-runner --action run --experiment-id manual_udp_01 --protocol udp --duration 5 --bandwidth 50
```

- **Raw JSON output location**: `results/raw/manual_udp_01_udp.json`
- **Output metrics**: Throughput (Mbps), Jitter (ms), Packet Loss (%), CPU utilization.

---

### J. Start FastAPI Backend

```bash
cd backend
source .venv/bin/activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

- API Base URL: `http://localhost:8000`
- Interactive API Documentation (Swagger): `http://localhost:8000/docs`
- Health Check: `http://localhost:8000/health`

---

### K. Start Next.js Frontend

In a separate terminal:

```bash
cd frontend
npm install
npm run dev
```

- Frontend URL: `http://localhost:3000`

---

### L. End-to-End Workflow

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

### M. Troubleshooting

| Symptom | Check Command | Likely Cause | Fix | Verification |
| :--- | :--- | :--- | :--- | :--- |
| **Database connection refused** | `systemctl status postgresql` | PostgreSQL service stopped | `sudo systemctl start postgresql` | Run `check_db_connection()` script |
| **Mininet permission denied** | `sudo -l` | User lacks sudoers entry | Check `/etc/sudoers.d/netpulse` | Run `sudo /usr/local/libexec/netpulse-runner --action verify` |
| **Open vSwitch error** | `systemctl status openvswitch-switch` | OVS daemon not running | `sudo systemctl start openvswitch-switch` | `ovs-vsctl show` returns clean state |
| **Missing iperf3 binary** | `which iperf3` | Package not installed | `sudo apt install -y iperf3` | `iperf3 --version` |
| **Lingering Mininet interfaces**| `ip link show` | Abrupt test termination | `sudo mn -c` | `ip link show` shows no orphan `s1-eth*` |
| **Port 8000 in use** | `lsof -i :8000` | Stale backend process | Kill existing process: `kill -9 <PID>` | Restart `uvicorn` |
| **Port 3000 in use** | `lsof -i :3000` | Stale Next.js process | Kill existing process: `kill -9 <PID>` | Restart `npm run dev` |
| **CORS errors in browser** | Check browser console | CORS origin mismatch in `.env` | Set `CORS_ORIGIN=http://localhost:3000` in `.env` | Reload browser |
| **ModuleNotFoundError: psycopg** | `python3 -c "import psycopg2"` | Missing driver | `pip install psycopg2-binary` | `python3 -c "import psycopg2"` |
| **Database schema missing** | `psql -U netpulse_user -d netpulse -c "\dt"` | Tables not migrated | Run `python3 -c "from app.db.database import create_tables; create_tables()"` | `\dt` shows `experiments` and `results` |
| **Sudoers syntax error** | `sudo visudo -c` | Corrupted rule file | `sudo rm /etc/sudoers.d/netpulse` and reinstall | `sudo visudo -c` passes |
| **Helper not found** | `ls -l /usr/local/libexec/netpulse-runner` | Helper not installed | Run `./scripts/install_netpulse.sh` or copy manually | Executable exists with 0755 |

---

### N. Cleanup

To clean lingering Mininet namespaces, switches, or iperf3 processes at any time:

```bash
sudo mn -c
```

---

### O. Reset & Uninstall

To remove the installed root helper and sudoers rule cleanly:

```bash
sudo rm -f /etc/sudoers.d/netpulse
sudo rm -f /usr/local/libexec/netpulse-runner
```
