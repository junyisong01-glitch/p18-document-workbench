#!/bin/zsh
set +x
TASK_ROOT="$(cd "$(dirname "$0")" && pwd)"
exec /usr/bin/env -u DEEPSEEK_API_KEY "$TASK_ROOT/.venv/bin/python" -B "$TASK_ROOT/scripts/experience.py" --local
