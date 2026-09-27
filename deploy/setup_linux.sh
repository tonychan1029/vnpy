#!/bin/bash
set -e
echo "=== PA Timing Engine Linux Deployment ==="

if [ "$1" != "--prod" ]; then
  echo "Usage: $0 --prod  (this script performs system-level changes)"
  exit 1
fi

echo "[1/6] Python venv + deps"
python3.12 -m venv /opt/aiprj/venv
source /opt/aiprj/venv/bin/activate
pip install --upgrade pip
pip install vnpy --no-deps
pip install tzlocal numpy pandas loguru requests polars pyarrow \
  alphalens-reloaded fastmcp redis httpx akshare "peewee>=3.17.9"
echo "[2/6] Copy code"
mkdir -p /opt/aiprj/vnpy_patiming /opt/aiprj/quant-repo
cp -r vnpy_patiming/* /opt/aiprj/vnpy_patiming/
cp -r vnpy /opt/aiprj/vnpy_pkg/
echo "[3/6] Systemd services"
cp deploy/patiming-engine.service deploy/patiming-mcp.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable patiming-engine patiming-mcp
echo "[4/6] Redis"
apt-get install -y redis-server > /dev/null
systemctl enable --now redis-server
echo "[5/6] Done. Run preflight:"
echo "  python -m vnpy_patiming.preflight"
echo "[6/6] Start engine:"
echo "  systemctl start patiming-engine"
