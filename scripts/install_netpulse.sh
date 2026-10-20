#!/usr/bin/env bash
# ==============================================================================
# NetPulse Environment Setup & Installation Script
#
# Safe, portable setup script for NetPulse on Ubuntu/Linux.
# Detects current user and project path dynamically.
# Prompts for explicit user approval before any privileged/sudo operation.
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
CURRENT_USER="$(id -un)"

# Terminal colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[OK]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

echo "======================================================"
echo "          NetPulse Environment Setup Script          "
echo "======================================================"
echo "Project Directory: ${PROJECT_ROOT}"
echo "Current User:      ${CURRENT_USER}"
echo ""

# 1. Verify OS
if [[ "$(uname -s)" != "Linux" ]]; then
    log_error "NetPulse experiments require a Linux environment (Ubuntu 22.04/24.04 recommended)."
    exit 1
fi
log_success "Linux environment detected: $(uname -sr)"

# 2. Check Prerequisites
log_info "Checking system prerequisites..."
MISSING_TOOLS=0

check_tool() {
    local cmd="$1"
    local name="$2"
    if command -v "$cmd" >/dev/null 2>&1; then
        log_success "$name found: $($cmd --version 2>&1 | head -n 1)"
    else
        log_error "$name ($cmd) is NOT installed."
        MISSING_TOOLS=1
    fi
}

check_tool python3 "Python 3"
check_tool git "Git"
check_tool psql "PostgreSQL Client (psql)"
check_tool mn "Mininet"
check_tool ovs-vsctl "Open vSwitch"
check_tool iperf3 "iperf3"
check_tool tc "Traffic Control (tc)"
check_tool ip "iproute2 (ip)"

if [[ "$MISSING_TOOLS" -ne 0 ]]; then
    log_error "One or more required system packages are missing."
    echo "Install missing packages on Ubuntu using:"
    echo "  sudo apt update && sudo apt install -y python3 python3-venv python3-pip git postgresql mininet openvswitch-switch iperf3 iproute2"
    exit 1
fi

# 3. Create Result Directories
log_info "Creating result storage directories..."
mkdir -p "${PROJECT_ROOT}/results/raw"
mkdir -p "${PROJECT_ROOT}/results/processed"
mkdir -p "${PROJECT_ROOT}/results/plots"
log_success "Result directories initialized."

# 4. Backend Virtual Environment Setup
log_info "Setting up Python virtual environment..."
VENV_DIR="${PROJECT_ROOT}/backend/.venv"
if [[ ! -d "$VENV_DIR" ]]; then
    python3 -m venv "$VENV_DIR"
    log_success "Created virtual environment at ${VENV_DIR}"
fi

log_info "Installing Python dependencies..."
"${VENV_DIR}/bin/pip" install --upgrade pip >/dev/null 2>&1 || true
"${VENV_DIR}/bin/pip" install -r "${PROJECT_ROOT}/backend/requirements.txt"
log_success "Backend dependencies installed successfully."

# 5. Environment File (.env)
ENV_FILE="${PROJECT_ROOT}/.env"
ENV_EXAMPLE="${PROJECT_ROOT}/.env.example"
if [[ ! -f "$ENV_FILE" ]]; then
    cp "$ENV_EXAMPLE" "$ENV_FILE"
    log_warn "Created .env from .env.example. Please update your DATABASE_URL in ${ENV_FILE}"
else
    log_success ".env file already exists."
fi

# 6. Database Connectivity Check
log_info "Checking PostgreSQL connection via backend..."
if PYTHONPATH="${PROJECT_ROOT}/backend" "${VENV_DIR}/bin/python" -c "from app.db.database import check_db_connection; ok, msg = check_db_connection(); exit(0 if ok else 1)" 2>/dev/null; then
    log_success "Database connection verified."
else
    log_warn "Could not connect to PostgreSQL. Please ensure PostgreSQL service is running and DATABASE_URL in .env is configured."
fi

# 7. Privileged Helper & Sudoers Setup (Requires User Confirmation)
echo ""
echo "======================================================"
echo "          Privileged Helper Installation             "
echo "======================================================"
echo "Mininet network isolation requires a root-owned helper executable."
echo "Target helper path: /usr/local/libexec/netpulse-runner (root:root, 0755)"
echo "Target sudoers file: /etc/sudoers.d/netpulse"
echo "Scoped permission:   ${CURRENT_USER} ALL=(root) NOPASSWD: /usr/local/libexec/netpulse-runner, /usr/bin/mn -c"
echo ""

read -rp "Would you like to install the privileged helper and configure scoped sudoers now? [y/N]: " CONFIRM_SUDO

if [[ "$CONFIRM_SUDO" =~ ^[Yy]$ ]]; then
    log_info "Installing /usr/local/libexec/netpulse-runner..."
    sudo mkdir -p /usr/local/libexec
    sudo cp "${PROJECT_ROOT}/experiments/privileged_helper.py" /usr/local/libexec/netpulse-runner
    sudo chown root:root /usr/local/libexec/netpulse-runner
    sudo chmod 0755 /usr/local/libexec/netpulse-runner
    log_success "Installed netpulse-runner executable."

    log_info "Configuring /etc/sudoers.d/netpulse..."
    TMP_SUDOERS=$(mktemp)
    echo "${CURRENT_USER} ALL=(root) NOPASSWD: /usr/local/libexec/netpulse-runner, /usr/bin/mn -c" > "$TMP_SUDOERS"
    sudo cp "$TMP_SUDOERS" /etc/sudoers.d/netpulse
    sudo chmod 0440 /etc/sudoers.d/netpulse
    rm -f "$TMP_SUDOERS"

    if sudo visudo -c -f /etc/sudoers.d/netpulse; then
        log_success "Sudoers configuration verified."
    else
        log_error "Sudoers validation failed! Reverting /etc/sudoers.d/netpulse..."
        sudo rm -f /etc/sudoers.d/netpulse
        exit 1
    fi

    log_info "Testing basic Mininet verification..."
    if sudo /usr/local/libexec/netpulse-runner --action verify; then
        log_success "Mininet verification passed successfully!"
    else
        log_warn "Mininet verification encountered an issue. Check Open vSwitch service: 'sudo systemctl status openvswitch-switch'"
    fi
else
    log_info "Skipped privileged helper installation. You can install it manually later by following docs/RUN_PROJECT.md"
fi

echo ""
echo "======================================================"
log_success "NetPulse setup completed!"
echo "To run the backend:"
echo "  cd ${PROJECT_ROOT}/backend"
echo "  source .venv/bin/activate"
echo "  uvicorn app.main:app --reload --host 0.0.0.0 --port 8000"
echo ""
echo "To run the frontend:"
echo "  cd ${PROJECT_ROOT}/frontend"
echo "  npm install"
echo "  npm run dev"
echo "======================================================"
