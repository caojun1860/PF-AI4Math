#!/bin/zsh
set -u
PROJECT_DIR="${0:A:h}"
cd -- "$PROJECT_DIR" || exit 1

"$PROJECT_DIR/.venv/bin/python" -m ai4math_gateway.cli status
print
print '请输入新的总上限。已使用量不会被清零。'
read 'TOKENS?Token 上限（例如 100000）：'
read 'CNY?金额上限，人民币估算（例如 2.00）：'
read 'REQUESTS?请求数上限（例如 100）：'

if "$PROJECT_DIR/.venv/bin/python" -m ai4math_gateway.cli set \
  --tokens "$TOKENS" --cny "$CNY" --requests "$REQUESTS"; then
  print '预算已更新。'
else
  print '更新失败，请检查三个输入是否均为正数且不低于已使用量。'
fi
print
read '?按回车关闭…'
