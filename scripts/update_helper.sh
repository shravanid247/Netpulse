#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

echo "Updating /usr/local/libexec/netpulse-runner..."
sudo cp "${PROJECT_ROOT}/experiments/privileged_helper.py" /usr/local/libexec/netpulse-runner
sudo chown root:root /usr/local/libexec/netpulse-runner
sudo chmod 0755 /usr/local/libexec/netpulse-runner
echo "Successfully updated /usr/local/libexec/netpulse-runner"
ls -la /usr/local/libexec/netpulse-runner
