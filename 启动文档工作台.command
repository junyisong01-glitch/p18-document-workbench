#!/bin/zsh
cd -- "$(dirname -- "$0")" || exit 1
if [[ ! -x .venv/bin/python ]]; then
  print '缺少项目运行环境，请参考 README.md 的首次安装说明，或让助手完成安装。'
  read -r '?按回车关闭窗口…'
  exit 1
fi
.venv/bin/python -B scripts/experience.py
if [[ $? -ne 0 ]]; then
  read -r '?启动未完成，按回车关闭窗口…'
fi
