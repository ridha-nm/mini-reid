#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
printf '\n=== %s ===\n' "$(date '+%Y-%m-%d %H:%M:%S')" >> model.log
.venv/bin/python -m mini_reid.cli --days 1 --model llama3.2:3b >> model.log 2>&1
