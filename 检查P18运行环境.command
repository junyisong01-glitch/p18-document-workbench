#!/bin/zsh
cd -- "$(dirname -- "$0")" || exit 1
.venv/bin/python -B scripts/doctor.py
read -r '?检查完成，按回车关闭…'
