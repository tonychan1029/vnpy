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
install -d -o aiprj -g aiprj -m 0755 \
  /opt/aiprj/vnpy_patiming /opt/aiprj/cache
cp -r vnpy_patiming/* /opt/aiprj/vnpy_patiming/
chown -R aiprj:aiprj /opt/aiprj/vnpy_patiming
cp deploy/server_setup.sh /opt/aiprj/server_setup.sh
chown aiprj:aiprj /opt/aiprj/server_setup.sh
echo "[3/6] Python path + systemd service"
echo /opt/aiprj > /opt/aiprj/venv/lib/python3.12/site-packages/aiprj.pth
SERVICE_SRC="${PATIMING_SERVICE_SRC:-../quant-repo/deploy}"
cp "$SERVICE_SRC/patiming-engine.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable patiming-engine
echo "[4/6] Redis"
apt-get install -y redis-server > /dev/null
mkdir -p /etc/systemd/system/redis-server.service.d
cat > /etc/systemd/system/redis-server.service.d/aiprj-port.conf << 'REDISEOF'
[Service]
ExecStart=
ExecStart=/usr/bin/redis-server /etc/redis/redis.conf --supervised systemd --daemonize no --port 6381
REDISEOF
systemctl daemon-reload
systemctl restart redis-server
systemctl enable redis-server
echo "[5/6] Done. Run preflight:"
echo "  python -m vnpy_patiming.preflight"
echo "[6/6] Start engine:"
echo "  systemctl start patiming-engine"
