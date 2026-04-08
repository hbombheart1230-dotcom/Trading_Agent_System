#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME="${1:-trading-agent-scheduler-dev}"
SERVICE_SRC="deploy\m28_launch_templates\linux\scheduler.service"
SERVICE_DST="/etc/systemd/system/${SERVICE_NAME}.service"

if [ ! -f "$SERVICE_SRC" ]; then
  echo "missing_service_template path=$SERVICE_SRC" >&2
  exit 3
fi

sudo cp "$SERVICE_SRC" "$SERVICE_DST"
sudo systemctl daemon-reload
sudo systemctl enable "${SERVICE_NAME}.service"
sudo systemctl restart "${SERVICE_NAME}.service"

echo "ok role=scheduler profile=dev service=${SERVICE_NAME}"
