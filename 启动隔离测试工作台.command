#!/bin/zsh
set +x
TASK_ROOT="$(cd "$(dirname "$0")" && pwd)"
exec /usr/bin/env -u DEEPSEEK_API_KEY "$TASK_ROOT/.venv/bin/python" "$TASK_ROOT/scripts/launch_unified_preview.py"
