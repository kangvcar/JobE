#!/bin/sh
set -eu
API="${VITE_API_BASE:-http://localhost:8000}"
MOCK="${VITE_USE_MOCK:-true}"
cat > /usr/share/nginx/html/config.js <<EOF
window.__JOBE_API_BASE__ = "${API}";
window.__JOBE_USE_MOCK__ = "${MOCK}";
EOF
exec nginx -g "daemon off;"
