#!/bin/zsh
set -u

PROJECT_DIR="${0:A:h}"
cd -- "$PROJECT_DIR" || exit 1
export PATH="$HOME/.opencode/bin:$HOME/.local/bin:$HOME/.elan/bin:/Library/TeX/texbin:$PATH"

if [[ ! -x "$PROJECT_DIR/.venv/bin/python" ]]; then
  print '项目 Python 环境不存在，请返回搭建任务继续安装。'
  read '?按回车关闭…'
  exit 1
fi

"$PROJECT_DIR/.venv/bin/python" tools/check_mcp_agents.py
STATUS=$?
if [[ "$STATUS" -eq 0 ]]; then
  print '\n全部本地检查通过。'
else
  print '\n检查未通过，请把上面的错误留在窗口中。'
fi
read '?按回车关闭…'
exit "$STATUS"
