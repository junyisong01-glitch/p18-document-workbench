#!/bin/zsh
cd -- "$(dirname -- "$0")"
exec .venv/bin/python -B scripts/experience.py --ai
