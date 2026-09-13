#!/bin/zsh
set -u

PROJECT_DIR="${0:A:h}"
PYTHON="$PROJECT_DIR/.venv/bin/python"
OPENCODE="$HOME/.opencode/bin/opencode"
CONFIG="$PROJECT_DIR/config/gateway.yaml"
HEALTH_URL='http://127.0.0.1:4001/health'
HEALTH_FILE="$PROJECT_DIR/.runtime/gateway/health.json"
LOG_FILE="$PROJECT_DIR/.runtime/gateway/server.log"
GATEWAY_PID=''

pause_and_exit() {
  print "$1"
  read '?按回车关闭…'
  exit 1
}

if [[ ! -x "$PYTHON" ]]; then
  pause_and_exit 'Python 环境尚未完成，请返回搭建任务继续安装。'
fi
if [[ ! -x "$OPENCODE" ]]; then
  pause_and_exit 'OpenCode 尚未安装完成，请返回搭建任务继续安装。'
fi

mkdir -p "$PROJECT_DIR/.runtime/gateway"
cd -- "$PROJECT_DIR" || pause_and_exit '无法进入项目目录。'
export PATH="$HOME/.opencode/bin:$HOME/.local/bin:$HOME/.elan/bin:/Library/TeX/texbin:$PATH"

# 一个项目只保留一个 OpenCode/Ensemble 实例。所有研究问题都在同一面板中
# 建立独立 team，避免重复实例共同冲击模型接口和争用 Git 快照锁。
if curl --silent --fail --max-time 2 'http://127.0.0.1:4747' >/dev/null 2>&1; then
  print 'AI4Math 研究面板已经运行。本次不会再启动第二个实例。'
  open 'http://127.0.0.1:4747'
  print '请回到原来的 OpenCode 终端继续输入任务。'
  read '?按回车关闭此重复启动窗口…'
  exit 0
fi

if ! "$PYTHON" -m ai4math_gateway.cli --config "$CONFIG" preflight \
  --min-tokens 40000 --min-cny 0.05 --min-requests 4; then
  pause_and_exit '当前余额不足以安全启动研究面板。可运行本地检查，或由你决定是否调整预算。'
fi

gateway_ready() {
  curl --silent --fail --max-time 2 "$HEALTH_URL" > "$HEALTH_FILE" 2>/dev/null || return 1
  "$PYTHON" -c 'import json,sys; d=json.load(open(sys.argv[1])); raise SystemExit(0 if d.get("status")=="ok" and d.get("credential_configured") else 1)' "$HEALTH_FILE"
}

cleanup() {
  if [[ -n "$GATEWAY_PID" ]]; then
    kill "$GATEWAY_PID" >/dev/null 2>&1 || true
    wait "$GATEWAY_PID" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT INT TERM

if ! gateway_ready; then
  "$PYTHON" -m ai4math_gateway.app --config "$CONFIG" >> "$LOG_FILE" 2>&1 &
  GATEWAY_PID=$!
  READY=0
  for _ in {1..60}; do
    if gateway_ready; then
      READY=1
      break
    fi
    if ! kill -0 "$GATEWAY_PID" >/dev/null 2>&1; then
      break
    fi
    sleep 0.25
  done
  if [[ "$READY" -ne 1 ]]; then
    pause_and_exit '网关未能启动。请先运行“配置豆包网关密钥.command”；若已配置，请查看 .runtime/gateway/server.log。'
  fi
fi

print 'AI4Math 本地预算网关已就绪。默认 Agent：research-orchestrator。'
print '按 Tab 可切换专业 Agent；总控可并行派发任务；任务面板会在浏览器自动打开。'

(
  for _ in {1..40}; do
    if curl --silent --fail --max-time 1 'http://127.0.0.1:4747' >/dev/null 2>&1; then
      open 'http://127.0.0.1:4747'
      exit 0
    fi
    sleep 0.5
  done
) &!

"$OPENCODE" --agent research-orchestrator
