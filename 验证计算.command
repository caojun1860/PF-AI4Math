#!/bin/zsh
cd -- "${0:A:h}" || exit 1
export PATH="$HOME/.local/bin:/Library/TeX/texbin:$PATH"
if ! command -v uv >/dev/null 2>&1; then
  print 'uv 尚未安装完成。'
  read '?按回车关闭…'
  exit 1
fi
uv run --locked python experiments/verify_identity.py
read '?按回车关闭…'
