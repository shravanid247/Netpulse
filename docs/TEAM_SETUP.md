# NetPulse Team 5-Person Local Setup & Collaboration Guide

This guide is specifically written for our **5-person project team** to ensure that **every team member can clone the repository and run the complete NetPulse project locally on their own laptop with 100% reproducibility**.

---

## A. Local Setup Architecture

Every team member runs their own self-contained, complete instance of NetPulse locally. There is **no shared central server** required for development or benchmarking.

### End-to-End Stack Flow:

```
[Developer Laptop]
  │
  ├──► [Ubuntu Linux / Ubuntu VM]
  │      │
  │      ├──► Next.js 14 Web Frontend (:3000)
  │      │      │ (HTTP REST / WebSockets)
  │      │      ▼
  │      ├──► FastAPI Orchestration Backend (:8000)
  │      │      │ (SQLAlchemy ORM)
  │      │      ├──► PostgreSQL Relational Database (:5432)
  │      │      │
  │      │      ▼ (Scoped Sudo Delegation)
  │      └──► Privileged Helper (/usr/local/libexec/netpulse-runner)
  │             │
  │             ├──► Mininet (Isolated Network Namespaces: h1, h2)
  │             ├──► Open vSwitch (Software Switches: s1, s2)
  │             ├──► Linux Traffic Control (tc/netem qdiscs on s1-eth2)
  │             ├──► iperf3 (Real TCP & UDP Measurements)
  │             └──► aioquic (Real QUIC TLS 1.3 Measurements)
```

---

## B. Windows Laptop Team Members

If your primary operating system is Windows, **Linux kernel networking features (network namespaces, Open vSwitch bridges, and `tc/netem` packet manipulation) cannot run directly in Windows**.

### Recommended VM Setup:
```
[Windows Host Machine]
  │
  └──► [VirtualBox 7.x OR VMware Workstation Player 17+]
         │
         └──► [Ubuntu 22.04 LTS / 24.04 LTS Guest VM]
                │
                └──► [NetPulse Full Stack]
```

### VM Configuration Guidelines:
1. **CPU / Cores**: Assign 4 CPU cores (minimum 2).
2. **Memory (RAM)**: Assign 8 GB RAM (minimum 4 GB).
3. **Storage**: 25 GB+ virtual disk.
4. **Network Settings**: Set Virtual Machine Adapter to **Bridged Networking** (or **NAT** with Port Forwarding for ports `3000` and `8000`).
5. **Path Independence**: Do **not** assume everyone shares the same username, home directory, machine name, or private IP address. Always use generic relative paths (`~/Netpulse`), `$PROJECT_ROOT`, or environment variables.

---

## C. First-Time Setup (Copy-Paste in Order)

Open a terminal inside your Ubuntu environment and run each section in order:

### 1. Install System Packages
```bash
sudo apt update && sudo apt install -y \
  build-essential curl git wget python3 python3-venv python3-pip python3-dev \
  libpq-dev postgresql postgresql-contrib mininet openvswitch-switch iperf3 iproute2
```

### 2. Install Node.js 20 LTS & npm
```bash
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs
```

### 3. Enable Background Daemons
```bash
sudo systemctl enable --now postgresql
sudo systemctl enable --now openvswitch-switch
```

### 4. Configure PostgreSQL Role & Database
```bash
sudo -u postgres psql <<EOF
CREATE USER netpulse_user WITH PASSWORD 'CHANGE_ME';
CREATE DATABASE netpulse OWNER netpulse_user;
GRANT ALL PRIVILEGES ON DATABASE netpulse TO netpulse_user;
\c netpulse
GRANT ALL ON SCHEMA public TO netpulse_user;
EOF
```

### 5. Clone the NetPulse Repository
```bash
git clone https://github.com/Kenrich64/Netpulse.git ~/Netpulse
cd ~/Netpulse
```

### 6. Setup Backend Virtual Environment & Dependencies
```bash
cd ~/Netpulse/backend
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip setuptools wheel
pip install -r requirements.txt
```

### 7. Setup Frontend Dependencies
```bash
cd ~/Netpulse/frontend
npm install
```

### 8. Configure Environment Variables (`.env`)
```bash
cd ~/Netpulse
cp .env.example .env
```
*(Optionally open `.env` and verify your `DATABASE_URL` matches your local password).*

### 9. Install Privileged NetPulse Helper
```bash
sudo mkdir -p /usr/local/libexec
sudo cp ~/Netpulse/experiments/privileged_helper.py /usr/local/libexec/netpulse-runner
sudo chown root:root /usr/local/libexec/netpulse-runner
sudo chmod 0755 /usr/local/libexec/netpulse-runner

# Grant scoped sudoers permission for your local user
echo "$(id -un) ALL=(root) NOPASSWD: /usr/local/libexec/netpulse-runner, /usr/bin/mn -c" | sudo tee /etc/sudoers.d/netpulse
sudo chmod 0440 /etc/sudoers.d/netpulse
sudo visudo -c -f /etc/sudoers.d/netpulse
```

### 10. Initialize Database Tables
```bash
cd ~/Netpulse/backend
source .venv/bin/activate
python3 -c "from app.db.database import create_tables; create_tables(); print('Database tables initialized!')"
```

---

## D. Daily Development Workflow

For day-to-day development, team members follow this standard routine:

```bash
# 1. Pull latest team updates
cd ~/Netpulse
git pull origin main

# 2. Ensure system services are active
sudo systemctl start postgresql
sudo systemctl start openvswitch-switch

# 3. Start Backend Server (Terminal 1)
cd ~/Netpulse/backend
source .venv/bin/activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 4. Start Frontend Dashboard (Terminal 2)
cd ~/Netpulse/frontend
npm run dev

# 5. Open browser at http://localhost:3000
```

---

## E. Team Verification & Testing Checklist

Every team member can verify every component of the system using the following exact commands:

| Target Component | Verification Command | Expected Outcome |
| :--- | :--- | :--- |
| **1. Backend Health** | `curl http://localhost:8000/health` | `{"status":"healthy","database":"connected",...}` |
| **2. Frontend Dashboard** | Open `http://localhost:3000` | NetPulse web application loads without errors |
| **3. PostgreSQL** | `cd ~/Netpulse/backend && source .venv/bin/activate && python3 -c "from app.db.database import check_db_connection; print(check_db_connection())"` | `(True, 'Database connection successful')` |
| **4. Mininet Connectivity** | `sudo /usr/local/libexec/netpulse-runner --action verify` | `{"success": true, "ping_loss": 0.0, "nodes": [...]}` |
| **5. Linux tc/netem** | `sudo /usr/local/libexec/netpulse-runner --action impairment_test --bandwidth 10 --latency 50 --packet-loss 2` | `{"success": true, ...}` with higher impaired ping RTT |
| **6. System iperf3** | `iperf3 --version` | `iperf 3.x+` binary output |
| **7. Real TCP Run** | `sudo /usr/local/libexec/netpulse-runner --action run --protocol tcp --duration 3 --bandwidth 50` | `{"protocol": "tcp", "throughput_mbps": ..., "success": true}` |
| **8. Real UDP Run** | `sudo /usr/local/libexec/netpulse-runner --action run --protocol udp --duration 3 --bandwidth 25` | `{"protocol": "udp", "jitter_ms": ..., "packet_loss_pct": ..., "success": true}` |
| **9. Real QUIC Run** | `sudo /usr/local/libexec/netpulse-runner --action run --protocol quic --duration 3 --bandwidth 50` | `{"protocol": "quic", "handshake_success": true, "success": true}` |
| **10. Full Python Test Suite**| `cd ~/Netpulse/backend && source .venv/bin/activate && python3 -m unittest discover -s ~/Netpulse/tests` | `Ran 45 tests in ...s - OK` |
| **11. Frontend Lint** | `cd ~/Netpulse/frontend && npm run lint` | No ESLint errors |
| **12. TypeScript Types** | `cd ~/Netpulse/frontend && npx tsc --noEmit` | Clean typecheck compilation |
| **13. Production Build** | `cd ~/Netpulse/frontend && npm run build` | Next.js production build completes successfully |

---

## F. Troubleshooting Common Team Issues

### 1. `PostgreSQL connection failed / FATAL: password authentication failed`
- **Cause**: Password in `.env` doesn't match PostgreSQL user password.
- **Fix**: Re-set the user password:
  ```bash
  sudo -u postgres psql -c "ALTER USER netpulse_user WITH PASSWORD 'YOUR_PASSWORD';"
  ```
  Update `DATABASE_URL` in `~/Netpulse/.env` accordingly.

### 2. `Port 8000 or Port 3000 already in use`
- **Cause**: A background or stale process is occupying the port.
- **Fix**:
  ```bash
  sudo lsof -t -i :8000 | xargs -r kill -9
  sudo lsof -t -i :3000 | xargs -r kill -9
  ```

### 3. `Mininet cleanup / Lingering virtual interfaces`
- **Cause**: An experiment was terminated abruptly before cleanup could complete.
- **Fix**:
  ```bash
  sudo mn -c
  sudo killall -9 iperf3 2>/dev/null || true
  ```

### 4. `Open vSwitch daemon is not active`
- **Cause**: Open vSwitch switch service stopped or crashed.
- **Fix**:
  ```bash
  sudo systemctl restart openvswitch-switch
  sudo ovs-vsctl show
  ```

### 5. `sudo: /usr/local/libexec/netpulse-runner: command not found`
- **Cause**: Privileged helper was not copied to the system library directory.
- **Fix**:
  ```bash
  sudo cp ~/Netpulse/experiments/privileged_helper.py /usr/local/libexec/netpulse-runner
  sudo chown root:root /usr/local/libexec/netpulse-runner
  sudo chmod 0755 /usr/local/libexec/netpulse-runner
  ```

### 6. `Python ModuleNotFoundError (e.g. aioquic or psycopg2)`
- **Cause**: Virtual environment not activated or dependencies missing.
- **Fix**:
  ```bash
  cd ~/Netpulse/backend
  source .venv/bin/activate
  pip install -r requirements.txt
  ```

### 7. `Node dependency / node_modules issues`
- **Cause**: Stale or corrupted `node_modules`.
- **Fix**:
  ```bash
  cd ~/Netpulse/frontend
  rm -rf node_modules package-lock.json
  npm install
  ```

### 8. `Frontend cannot reach backend / CORS error`
- **Cause**: Backend is not running or `CORS_ORIGIN` in `.env` is incorrect.
- **Fix**: Ensure backend is running on `http://localhost:8000` and `.env` contains `CORS_ORIGIN=http://localhost:3000`.

### 9. `QUIC certificate or dependency error`
- **Cause**: Missing `cryptography` or `aioquic` packages.
- **Fix**: Run `pip install aioquic cryptography` in your backend venv. Ephemeral certificates with Subject Alternative Names are automatically generated for each test run by `experiments/quic/certs.py`.

---

## G. Git Team Workflow & Collaboration Rules

To maintain codebase integrity and avoid merge conflicts across our 5 team members:

### Standard Feature Branching Flow
```bash
# 1. Always start from up-to-date main branch
git checkout main
git pull origin main

# 2. Create your isolated feature branch
git checkout -b feature/your-feature-name

# 3. Check status and stage only relevant files
git status
git add <specific-files-only>

# 4. Commit with descriptive semantic message
git commit -m "feat: implement feature description"

# 5. Push to GitHub
git push -u origin feature/your-feature-name

# 6. Open a Pull Request on GitHub for team review
```

### Critical Rules: What NEVER to Commit to Git
Before running `git commit`, verify that none of the following are staged:
1. **`.env` files** (Contains local passwords and database credentials).
2. **Passwords, secrets, or API keys**.
3. **TLS private keys / ephemeral certificates**.
4. **Machine-specific configuration or hardcoded local paths** (`/home/username/...`).
5. **`node_modules/`** directory.
6. **`.venv/` or Python virtual environments**.
7. **`__pycache__/` and `*.pyc` files**.
8. **`.next/` build output cache**.
9. **`results/raw/*.json` benchmark dumps generated from local test runs**.

---

## H. Team Member Reproducibility Checklist

Before submitting or reviewing code, every team member must be able to check off each item below on their local laptop:

- [ ] Fresh Ubuntu 22.04 / 24.04 (or Ubuntu VM) running
- [ ] Git works (`git --version`)
- [ ] Python 3.10+ works (`python3 --version`)
- [ ] Node.js & npm work (`node -v && npm -v`)
- [ ] PostgreSQL service is active (`sudo systemctl is-active postgresql`)
- [ ] Mininet works (`mn --version`)
- [ ] Open vSwitch service is active (`sudo systemctl is-active openvswitch-switch`)
- [ ] iperf3 works (`iperf3 --version`)
- [ ] Linux Traffic Control (`tc`) works (`tc -V`)
- [ ] Repository cloned to local workspace (`~/Netpulse`)
- [ ] Backend dependencies installed in `backend/.venv` (`pip list`)
- [ ] Frontend dependencies installed in `frontend/node_modules`
- [ ] `.env` configured with local database credentials
- [ ] Privileged runner installed (`/usr/local/libexec/netpulse-runner`) with scoped sudoers
- [ ] Backend starts without errors (`uvicorn app.main:app --port 8000`)
- [ ] Frontend starts without errors (`npm run dev`)
- [ ] Dashboard opens at `http://localhost:3000`
- [ ] TCP experiment executes and outputs valid throughput
- [ ] UDP experiment executes and outputs valid throughput, jitter, and loss
- [ ] QUIC experiment executes with TLS 1.3 handshake and outputs throughput
- [ ] All 45 Python unit and integration tests pass (`python3 -m unittest discover -s tests`)
