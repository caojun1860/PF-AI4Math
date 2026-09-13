#!/bin/zsh
set -u

PROJECT_DIR="${0:A:h}"
OPENCODE="$HOME/.opencode/bin/opencode"
cd -- "$PROJECT_DIR" || exit 1

print '将打开浏览器连接 Undermind。请在网页中登录并批准访问。'
"$OPENCODE" mcp auth undermind
print '完成后请重新启动 AI4Math 研究面板。'
read '?按回车关闭…'
