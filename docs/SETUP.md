# NetPulse Environment Setup & Prerequisites

This guide provides detailed system-level installation instructions for Ubuntu Linux systems (Ubuntu 22.04 LTS and Ubuntu 24.04 LTS).

---

## 1. Operating System Packages

Update your package index and install required packages:

```bash
sudo apt update
sudo apt install -y \
  python3 \
  python3-venv \
  python3-pip \
  git \
  postgresql \
  postgresql-contrib \
  mininet \
  openvswitch-switch \
  iperf3 \
  iproute2 \
  build-essential \
  curl
```

Verify service status:
```bash
sudo systemctl enable --now postgresql
sudo systemctl enable --now openvswitch-switch
```

---

## 2. Node.js & npm (Frontend)

If Node.js is not already installed on your system:

```bash
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs
```

Verify versions:
```bash
node --version # v18+ or v20+
npm --version
```

---

## 3. PostgreSQL Role & Database Configuration

Create the database user and grant schema permissions:

```bash
sudo -u postgres psql <<EOF
CREATE USER netpulse_user WITH PASSWORD 'CHANGE_ME';
CREATE DATABASE netpulse OWNER netpulse_user;
GRANT ALL PRIVILEGES ON DATABASE netpulse TO netpulse_user;
\c netpulse
GRANT ALL ON SCHEMA public TO netpulse_user;
EOF
```

---

## 4. Python Virtual Environment Setup

From the NetPulse repository root:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip setuptools wheel
pip install -r requirements.txt
```

---

## 5. Automated Setup Alternative

You can automate steps 4 and 5 by executing:

```bash
./scripts/install_netpulse.sh
```

Follow [RUN_PROJECT.md](RUN_PROJECT.md) for full runtime and testing instructions.
