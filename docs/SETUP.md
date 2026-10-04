# NetPulse System Setup & Prerequisites Guide

This document provides a comprehensive, step-by-step setup guide for configuring a fresh **Ubuntu Linux** machine or virtual machine to run the complete NetPulse project.

---

## 1. System & Hardware Requirements

### Recommended Hardware
- **CPU**: 4 cores or more (2 cores absolute minimum).
- **RAM**: 8 GB or more (4 GB minimum; needed to run Next.js, FastAPI, PostgreSQL, and Mininet concurrently).
- **Disk Space**: 15 GB+ free storage.
- **Virtualization**: Intel VT-x or AMD-V enabled in BIOS/UEFI if running inside a Virtual Machine.

### Recommended Operating System
- **Ubuntu 22.04 LTS (Jammy Jellyfish)** or **Ubuntu 24.04 LTS (Noble Numbat)**.
- Native Linux kernel with network namespace (`netns`) and Open vSwitch support.

---

## 2. Windows Users: Ubuntu VM Recommendation

> [!IMPORTANT]
> **Windows Notice**: Mininet, Linux Traffic Control (`tc/netem`), and network namespaces are native Linux kernel features and **cannot run natively on Windows**.

### Recommended VM Setup for Windows Laptops:
1. Install **Oracle VirtualBox 7.x** or **VMware Workstation Player 17+**.
2. Download the official **Ubuntu 22.04 LTS** or **24.04 LTS Desktop ISO**.
3. Create a new virtual machine with:
   - **RAM**: At least 4096 MB (8192 MB recommended).
   - **Processors**: At least 2 CPUs (4 CPUs recommended).
   - **Storage**: 25 GB dynamically allocated disk.
   - **Network**: NAT or Bridged Adapter.
   - **Port Forwarding (if using NAT)**:
     - Guest Port `3000` -> Host Port `3000` (Next.js Dashboard)
     - Guest Port `8000` -> Host Port `8000` (FastAPI Backend)
4. Boot into Ubuntu and complete the standard installation.

> [!NOTE]
> **WSL2 Note**: Standard WSL2 kernels do not include full Open vSwitch kernel modules or proper `netem` qdiscs by default. Running inside a full **VirtualBox / VMware Ubuntu VM** is strongly recommended for guaranteed reproducibility across all team members.

---

## 3. Required Software & System Packages

### Step 3.1: System Update & Core Build Utilities
Open a terminal in Ubuntu and run:

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y \
  build-essential \
  curl \
  wget \
  git \
  ca-certificates \
  gnupg \
  lsb-release
```

### Step 3.2: Python 3 & Development Packages
```bash
sudo apt install -y \
  python3 \
  python3-venv \
  python3-pip \
  python3-dev \
  libpq-dev
```

### Step 3.3: Node.js 20 LTS & npm
Install Node.js 20.x from the official NodeSource repository:

```bash
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs
```

### Step 3.4: PostgreSQL Database Server
```bash
sudo apt install -y postgresql postgresql-contrib
sudo systemctl enable --now postgresql
```

### Step 3.5: Mininet, Open vSwitch, iperf3, and iproute2
```bash
sudo apt install -y \
  mininet \
  openvswitch-switch \
  iperf3 \
  iproute2
sudo systemctl enable --now openvswitch-switch
```

---

## 4. Verification of Installed Software

Verify that all required binaries and services are available on your system:

```bash
echo "=== Checking System Dependencies ==="
git --version          # Expected: git version 2.x+
python3 --version      # Expected: Python 3.10+
node --version         # Expected: v18+ or v20+
npm --version          # Expected: 9.x or 10.x
psql --version         # Expected: psql (PostgreSQL) 14+
mn --version           # Expected: 2.3.0+
ovs-vsctl --version    # Expected: ovs-vsctl (Open vSwitch) 2.17+ / 3.x+
iperf3 --version       # Expected: iperf 3.x+
tc -V                  # Expected: tc utility, iproute2-ss...
ip -V                  # Expected: ip utility, iproute2-ss...
```

Check that background daemons are active:
```bash
sudo systemctl is-active postgresql          # Expected: active
sudo systemctl is-active openvswitch-switch  # Expected: active
```

---

## 5. Clone the Repository

Clone the NetPulse repository into your home directory (or workspace of choice):

```bash
git clone https://github.com/Kenrich64/Netpulse.git ~/Netpulse
cd ~/Netpulse
```

---

## 6. Python Virtual Environment & Backend Setup

Create an isolated virtual environment and install all backend and protocol dependencies:

```bash
cd ~/Netpulse/backend

# 1. Create Python virtual environment
python3 -m venv .venv

# 2. Activate virtual environment
source .venv/bin/activate

# 3. Upgrade packaging tools
pip install --upgrade pip setuptools wheel

# 4. Install backend dependencies (FastAPI, SQLAlchemy, Uvicorn, psycopg2, aioquic, cryptography)
pip install -r requirements.txt
```

---

## 7. Frontend Setup

Install the Next.js dependencies:

```bash
cd ~/Netpulse/frontend
npm install
```

---

## 8. PostgreSQL Database Configuration

### Step 8.1: Create Database User and Database
Run the following PostgreSQL commands as the `postgres` superuser:

```bash
sudo -u postgres psql <<EOF
CREATE USER netpulse_user WITH PASSWORD 'CHANGE_ME';
CREATE DATABASE netpulse OWNER netpulse_user;
GRANT ALL PRIVILEGES ON DATABASE netpulse TO netpulse_user;
\c netpulse
GRANT ALL ON SCHEMA public TO netpulse_user;
EOF
```

> [!NOTE]
> Replace `'CHANGE_ME'` with your preferred local password. Remember to update the matching value in `.env`. Never commit real passwords to Git.

### Step 8.2: Configure Environment File (`.env`)
From the repository root:

```bash
cd ~/Netpulse
cp .env.example .env
```

Open `.env` in your text editor and ensure the configuration matches your local database:

```ini
# ============================================================
# NetPulse backend environment configuration
# Copy this file to .env and fill in real values.
# NEVER commit .env to version control.
# ============================================================

# PostgreSQL connection string
# Format: postgresql://ROLE:PASSWORD@HOST:PORT/DATABASE
DATABASE_URL=postgresql://netpulse_user:CHANGE_ME@localhost:5432/netpulse

# Frontend origin allowed by FastAPI CORS
CORS_ORIGIN=http://localhost:3000

# Execution mode: "simulation" or "real"
# Use "simulation" for safe mock execution without root helper.
# Set to "real" for full Mininet + Open vSwitch + tc/netem + iperf3/aioquic benchmarks.
NETPULSE_EXECUTION_MODE=simulation
```

### Step 8.3: Initialize Database Tables
Initialize the SQLAlchemy tables (`experiments` and `results`):

```bash
cd ~/Netpulse/backend
source .venv/bin/activate
python3 -c "from app.db.database import create_tables, check_db_connection; ok, msg = check_db_connection(); print('DB status:', msg); create_tables(); print('Database tables initialized successfully!')"
```

---

## 9. Privileged Runner & Security Configuration

### Why the Runner Requires Root / Sudo
NetPulse executes **real network measurements** in isolated Linux network namespaces. Specifically:
1. **Mininet** creates virtual network interfaces (`veth` pairs) and assigns them to isolated network namespaces (`netns`).
2. **Open vSwitch (OVS)** creates software bridge switches (`s1`, `s2`) and configures OpenFlow datapaths.
3. **Linux Traffic Control (`tc/netem`)** installs kernel queueing disciplines (`qdisc`) on virtual network interfaces to apply precise delay, jitter, loss, and rate limiting.

All of these operations require Linux `CAP_NET_ADMIN` and root privilege.

### Security Model: Scoped Sudo Execution
To avoid running the entire FastAPI backend or Next.js frontend as root:
- The FastAPI application runs as your standard **non-root** user.
- Privileged operations are delegated exclusively to a single root-owned script installed at `/usr/local/libexec/netpulse-runner`.
- Sudo access is granted **only** to `/usr/local/libexec/netpulse-runner` and `/usr/bin/mn -c`.

### Step 9.1: Install the Privileged Helper
```bash
# 1. Create target directory
sudo mkdir -p /usr/local/libexec

# 2. Copy helper script from experiments directory
sudo cp ~/Netpulse/experiments/privileged_helper.py /usr/local/libexec/netpulse-runner

# 3. Restrict ownership and permissions
sudo chown root:root /usr/local/libexec/netpulse-runner
sudo chmod 0755 /usr/local/libexec/netpulse-runner
```

### Step 9.2: Configure Scoped Sudoers Rule
Add the scoped rule for your current user:

```bash
echo "$(id -un) ALL=(root) NOPASSWD: /usr/local/libexec/netpulse-runner, /usr/bin/mn -c" | sudo tee /etc/sudoers.d/netpulse
sudo chmod 0440 /etc/sudoers.d/netpulse

# Validate sudoers configuration syntax
sudo visudo -c -f /etc/sudoers.d/netpulse
```

---

## 10. Automated Installation Alternative

Instead of running sections 6–9 manually, you can run our automated installer:

```bash
cd ~/Netpulse
./scripts/install_netpulse.sh
```

The script will check all dependencies, create directories, set up the backend virtual environment, create `.env`, and prompt you to install the privileged helper automatically.

---

## 11. Verifying Complete Installation

Run these verification steps to confirm everything is operational:

### 1. Verify Mininet & Open vSwitch Connectivity
```bash
sudo /usr/local/libexec/netpulse-runner --action verify
```
Expected output:
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

### 2. Verify Linux `tc/netem` Impairment Injection
```bash
sudo /usr/local/libexec/netpulse-runner --action impairment_test --bandwidth 10 --latency 50 --packet-loss 2
```
Expected output:
`"success": true`, with higher impaired ping RTT and clean qdisc restoration.

### 3. Run Test Suite
```bash
cd ~/Netpulse/backend
source .venv/bin/activate
python3 -m unittest discover -s ~/Netpulse/tests
```
Expected output:
`Ran 45 tests in ...s - OK`

---

## 12. Common Setup Errors & Solutions

| Problem | Cause | Solution |
| :--- | :--- | :--- |
| `FATAL: password authentication failed for user "netpulse_user"` | PostgreSQL password mismatch | Ensure password in `.env` (`DATABASE_URL`) matches the password set in `CREATE USER netpulse_user WITH PASSWORD '...'`. |
| `could not connect to server: Connection refused` | PostgreSQL daemon stopped | Run `sudo systemctl start postgresql` and verify with `sudo systemctl status postgresql`. |
| `ovsdb-server: could not connect to socket` | Open vSwitch daemon not running | Run `sudo systemctl start openvswitch-switch`. |
| `sudo: /usr/local/libexec/netpulse-runner: command not found` | Helper not copied | Run `sudo cp ~/Netpulse/experiments/privileged_helper.py /usr/local/libexec/netpulse-runner && sudo chmod 0755 /usr/local/libexec/netpulse-runner`. |
| `sudo: a password is required` | Sudoers rule incorrect | Verify `/etc/sudoers.d/netpulse` contains `YOUR_USERNAME ALL=(root) NOPASSWD: /usr/local/libexec/netpulse-runner, /usr/bin/mn -c`. |
| `Cannot find a default OpenFlow controller` | Mininet trying to connect to external controller | The helper uses `OVSSwitch` in `standalone` mode (`failMode="standalone"`) without requiring an OpenFlow controller. Use the privileged helper. |
| `Cannot allocate memory` / Next.js crash | Insufficient VM RAM | Increase VM RAM to at least 4 GB (8 GB recommended). |
| `ModuleNotFoundError: No module named 'mininet'` | Running helper with custom Python instead of system Python | Ensure `/usr/local/libexec/netpulse-runner` uses `#!/usr/bin/env python3` where `mininet` package is installed via `apt install mininet`. |
