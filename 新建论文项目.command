#!/bin/zsh
set -u

PROJECT_DIR="${0:A:h}"
PYTHON="$PROJECT_DIR/.venv/bin/python"
cd -- "$PROJECT_DIR" || exit 1

print '请输入研究问题：'
read 'QUESTION?> '
print '请输入论文标题（可与问题相同）：'
read 'TITLE?> '
[[ -z "$TITLE" ]] && TITLE="$QUESTION"
print '请输入简短文件夹名，例如 symmetric-space-uap 或 对称空间-UAP：'
read 'SLUG?> '

if "$PYTHON" tools/paper_manager.py create --question "$QUESTION" --title "$TITLE" --slug "$SLUG"; then
  open "$PROJECT_DIR/papers/$SLUG"
else
  print '创建失败，请检查问题和文件夹名。'
fi
read '?按回车关闭…'
