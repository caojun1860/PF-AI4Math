#!/bin/zsh
set -u

PROJECT_DIR="${0:A:h}"
cd -- "$PROJECT_DIR" || exit 1
"$PROJECT_DIR/.venv/bin/python" tools/github_release_check.py
print
read '?按回车关闭…'
