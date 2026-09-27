#!/bin/bash
set -euo pipefail

STAGE="${1:-/home/tony/patiming_stage}"
REDIS_DATA=/var/lib/redis
REDIS_RDB="$REDIS_DATA/dump.rdb"

echo "[1/9] Stop PA Timing services"
systemctl stop patiming-engine patiming-mcp 2>/dev/null || true
systemctl disable patiming-mcp 2>/dev/null || true

echo "[2/9] Validate/move aside native Redis persistence"
if [[ -f "$REDIS_RDB" ]]; then
    if ! redis-check-rdb "$REDIS_RDB" >/dev/null 2>&1; then
        backup="dump.rdb.failed-$(date +%Y%m%d%H%M%S)"
        mv "$REDIS_RDB" "$REDIS_DATA/$backup"
        echo "Moved invalid RDB to $REDIS_DATA/$backup"
    fi
fi

echo "[3/9] Isolate native Redis on 127.0.0.1:6381"
mkdir -p /etc/systemd/system/redis-server.service.d
cat > /etc/systemd/system/redis-server.service.d/aiprj-port.conf <<'EOF'
[Service]
ExecStart=
ExecStart=/usr/bin/redis-server /etc/redis/redis.conf --supervised systemd --daemonize no --port 6381
EOF
systemctl daemon-reload
if ! systemctl is-active --quiet redis-server; then
    systemctl restart redis-server
fi
systemctl enable redis-server >/dev/null

echo "[4/9] Install current engine code"
install -d -o aiprj -g aiprj -m 0755 /opt/aiprj/vnpy_patiming
cp -a "$STAGE/vnpy_patiming/." /opt/aiprj/vnpy_patiming/
echo /opt/aiprj > /opt/aiprj/venv/lib/python3.12/site-packages/aiprj.pth

echo "[5/9] Install missing runtime dependency"
if compgen -G "$STAGE/wheels/*.whl" >/dev/null; then
    /opt/aiprj/venv/bin/pip install --disable-pip-version-check \
        --no-index --find-links "$STAGE/wheels" akshare
else
    /opt/aiprj/venv/bin/pip install --disable-pip-version-check akshare
fi

echo "[6/9] Install single-writer service unit"
install -m 0644 "$STAGE/patiming-engine.service" /etc/systemd/system/patiming-engine.service
rm -f /etc/systemd/system/patiming-mcp.service
systemctl daemon-reload

echo "[7/9] Preserve token and write service environment"
install -d -o aiprj -g aiprj -m 0750 /etc/aiprj
TOKEN_FILE=/etc/aiprj/patiming_mcp_token
if [[ ! -s "$TOKEN_FILE" ]]; then
    openssl rand -hex 32 > "$TOKEN_FILE"
fi
chown aiprj:aiprj "$TOKEN_FILE"
chmod 0600 "$TOKEN_FILE"
cat > /etc/aiprj/patiming.env <<'EOF'
PATIMING_DB=/opt/aiprj/patiming.db
PATIMING_MCP_TOKEN_FILE=/etc/aiprj/patiming_mcp_token
PATIMING_REDIS_URL=redis://127.0.0.1:6381/0
PATIMING_STREAM=patiming:alerts
PATIMING_ENABLE_POLLER=1
PATIMING_DATA_MODE=akshare_poll
PATIMING_POLL_INTERVAL_S=5
TRADEPLAY_DATA=/opt/aiprj/tradereplay/data
QUANT_REPO_PATH=/opt/aiprj/quant-repo
PYTHONUTF8=1
EOF
chown aiprj:aiprj /etc/aiprj/patiming.env
chmod 0640 /etc/aiprj/patiming.env

echo "[8/9] Preflight"
runuser -u aiprj -- bash -c 'set -a; source /etc/aiprj/patiming.env; set +a; \
    /opt/aiprj/venv/bin/python -m vnpy_patiming.preflight'

echo "[9/9] Start engine"
systemctl reset-failed patiming-engine redis-server
systemctl enable patiming-engine >/dev/null
systemctl restart patiming-engine
sleep 3
systemctl is-active redis-server patiming-engine
ss -ltn | grep -E ':(6381|8801)\b'
echo "PATIMING_REPAIR_OK"
