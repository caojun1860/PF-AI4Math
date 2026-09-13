#!/bin/zsh
cd -- "${0:A:h}" || exit 1
export PATH="$HOME/.opencode/bin:$HOME/.local/bin:$HOME/.elan/bin:/Library/TeX/texbin:$PATH"
if [[ ! -x "$HOME/.opencode/bin/opencode" ]]; then
  print 'OpenCode 尚未安装完成。请返回搭建任务继续安装。'
  read '?按回车关闭…'
  exit 1
fi
print '这是不经过项目预算账本的故障排查入口。'
"$HOME/.opencode/bin/opencode" -m doubao-ark/doubao-seed-2-1-turbo-260628
