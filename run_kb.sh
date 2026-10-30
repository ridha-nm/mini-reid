#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
printf '\n=== %s ===\n' "$(date '+%Y-%m-%d %H:%M:%S')" >> kb.log
.venv/bin/python -m mini_reid.kb --build >> kb.log 2>&1
