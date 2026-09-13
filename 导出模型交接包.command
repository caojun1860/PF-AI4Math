#!/bin/zsh
set -u

PROJECT_DIR="${0:A:h}"
cd -- "$PROJECT_DIR" || exit 1
"$PROJECT_DIR/.venv/bin/python" tools/export_handoff.py
open "$PROJECT_DIR/.handoff"
print
read '?交接包已经生成。按回车关闭…'
