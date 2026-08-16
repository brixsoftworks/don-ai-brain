#!/usr/bin/env bash
# Open the DON wake overlay fullscreen (docs/component-16a §6).
# Usage: ./ui/launch/laptop.sh [URL]
set -euo pipefail
URL="${1:-http://localhost:8080/ui}"
BROWSER=""
for b in firefox chromium chromium-browser google-chrome; do
  if command -v "$b" >/dev/null 2>&1; then BROWSER="$b"; break; fi
done
if [ -z "$BROWSER" ]; then echo "no browser found"; exit 1; fi

case "$BROWSER" in
  firefox) "$BROWSER" --kiosk "$URL" & ;;
  chromium*|google-chrome) "$BROWSER" --kiosk --app="$URL" & ;;
esac
