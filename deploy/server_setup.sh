#!/bin/bash
set -e
TOKEN=$(openssl rand -hex 32)
mkdir -p /etc/aiprj
if [ ! -s /etc/aiprj/patiming_mcp_token ]; then
  echo "$TOKEN" > /etc/aiprj/patiming_mcp_token
fi
chown aiprj:aiprj /etc/aiprj/patiming_mcp_token
chmod 600 /etc/aiprj/patiming_mcp_token
cat > /etc/aiprj/patiming.env << ENVEOF
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
ENVEOF
chmod 640 /etc/aiprj/patiming.env
chown aiprj:aiprj /etc/aiprj/patiming.env
systemctl daemon-reload
systemctl disable --now patiming-mcp 2>/dev/null || true
systemctl restart patiming-engine
echo "SETUP_OK token_file=/etc/aiprj/patiming_mcp_token"
