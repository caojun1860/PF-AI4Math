#!/bin/zsh
set -eu

SERVICE='AI4Math Doubao Ark'
ACCOUNT="${USER:-$(id -un)}"

print '为本地预算网关保存豆包 API Key。'
print '密钥只写入 macOS“钥匙串访问”，不会写入项目或显示在屏幕上。'
print '请输入火山方舟 API Key（输入时屏幕不会出现字符）：'
read -rs ARK_KEY
print

if [[ -z "$ARK_KEY" ]]; then
  print '未输入内容，未作修改。'
  read '?按回车关闭…'
  exit 1
fi

if [[ "$ARK_KEY" == apikey-* || "$ARK_KEY" == doubao-* ]]; then
  unset ARK_KEY
  print '这看起来是 API Key 名称或模型 ID，不是鉴权密钥值。'
  print '请在火山方舟“API Key 管理”中点该密钥右侧的查看/复制按钮，再运行本文件。'
  read '?按回车关闭…'
  exit 1
fi

trap 'unset ARK_KEY' EXIT
security add-generic-password -U -a "$ACCOUNT" -s "$SERVICE" -w "$ARK_KEY" >/dev/null
unset ARK_KEY
trap - EXIT

print '已安全保存。现在可以双击“启动研究面板.command”。'
read '?按回车关闭…'
