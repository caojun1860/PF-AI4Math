#!/bin/zsh
PROJECT_DIR="${0:A:h}"
cd -- "$PROJECT_DIR" || exit 1
"$PROJECT_DIR/.venv/bin/python" -m ai4math_gateway.cli status
print
read '?按回车关闭…'
