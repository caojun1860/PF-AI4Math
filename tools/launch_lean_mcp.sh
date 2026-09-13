#!/bin/zsh
set -euo pipefail

PROJECT_DIR="${0:A:h:h}"
export PATH="$HOME/.local/bin:$HOME/.elan/bin:/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin"

if ! command -v lean-lsp-mcp >/dev/null 2>&1; then
  print -u2 "找不到 lean-lsp-mcp。请先安装 Lean MCP，再重新运行检查。"
  exit 127
fi

cd -- "$PROJECT_DIR"
exec lean-lsp-mcp "$@"
