#!/usr/bin/env bash
set -euo pipefail

XVFB_WHD="${SCREEN_WIDTH}x${SCREEN_HEIGHT}x${SCREEN_DEPTH}"

echo "[vnc] Starting Xvfb on ${DISPLAY} with ${XVFB_WHD}"
Xvfb "${DISPLAY}" -screen 0 "${XVFB_WHD}" -ac +extension RANDR >/tmp/xvfb.log 2>&1 &

echo "[vnc] Starting fluxbox"
fluxbox >/tmp/fluxbox.log 2>&1 &

echo "[vnc] Starting x11vnc on :5900"
x11vnc -display "${DISPLAY}" -forever -shared -rfbport 5900 -nopw >/tmp/x11vnc.log 2>&1 &

echo "[vnc] Starting noVNC on :6080"
websockify --web=/usr/share/novnc 6080 localhost:5900 >/tmp/websockify.log 2>&1 &

echo "[mcp] Starting Playwright MCP on :8931"
cmd=(node cli.js --browser "${MCP_BROWSER}" --no-sandbox --port 8931 --output-dir /app/reports)
if [ "${MCP_HEADLESS:-false}" = "true" ]; then
  cmd+=(--headless)
fi

echo "[mcp] Browser=${MCP_BROWSER} Headless=${MCP_HEADLESS:-false}"
exec "${cmd[@]}"
