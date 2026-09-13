#!/bin/zsh
set -u

URL='http://127.0.0.1:4747'
if curl --silent --fail --max-time 2 "$URL" >/dev/null 2>&1; then
  open "$URL"
else
  print '并行面板尚未运行。请先启动 Agent 研究面板，并保持其窗口打开。'
  read '?按回车关闭…'
fi
