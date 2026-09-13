#!/bin/zsh
set -u

PROJECT_DIR="${0:A:h}"
PYTHON="$PROJECT_DIR/.venv/bin/python"
print '请输入要在 Google Scholar 人工核验的标题、作者或关键词：'
read 'QUERY?> '
URL="$($PYTHON -c 'import sys,urllib.parse; print("https://scholar.google.com/scholar?q="+urllib.parse.quote(sys.argv[1]))' "$QUERY")"
open "$URL"
