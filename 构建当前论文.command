#!/bin/zsh
set -u

PROJECT_DIR="${0:A:h}"
PYTHON="$PROJECT_DIR/.venv/bin/python"
export PATH="/Library/TeX/texbin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"
cd -- "$PROJECT_DIR" || exit 1

if "$PYTHON" tools/paper_manager.py build; then
  SLUG="$($PYTHON -c 'import json; print(json.load(open(".runtime/active-paper.json"))["slug"])')"
  open "$PROJECT_DIR/papers/$SLUG/deliverables"
else
  print '构建失败。日志位于当前论文的 build/latexmk-output.txt。'
fi
read '?按回车关闭…'
