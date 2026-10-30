#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
.venv/bin/python -m mini_reid.watcher >> watcher.log 2>&1
