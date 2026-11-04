#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
printf '\n=== %s ===\n' "$(date '+%Y-%m-%d %H:%M:%S')" >> run.log
.venv/bin/python -m mini_reid.cli --days 1 --deliver >> run.log 2>&1
.venv/bin/python -m mini_reid.members --digest >> run.log 2>&1
