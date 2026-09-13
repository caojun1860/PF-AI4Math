#!/bin/zsh
set -u

PROJECT_DIR="${0:A:h}"
PYTHON="$PROJECT_DIR/.venv/bin/python"
export PATH="$HOME/.opencode/bin:$HOME/.local/bin:$HOME/.elan/bin:/Library/TeX/texbin:$PATH"
cd -- "$PROJECT_DIR" || exit 1

if [[ ! -x "$PYTHON" ]]; then
  print '项目 Python 环境不存在，请返回搭建任务继续安装。'
  read '?按回车关闭…'
  exit 1
fi

wait_for_key() {
  print
  read '?按回车返回控制台…'
}

while true; do
  clear
  "$PYTHON" tools/status_panel.py
  print
  print '────────────────────────────────────────────────────────────'
  print '1  打开 Agent 研究面板（先检查预算）'
  print '2  刷新本地状态'
  print '3  检查 MCP 与 Agent（不调用模型）'
  print '4  验证 Lean 项目（不调用模型）'
  print '5  查看预算明细'
  print '6  调整本地预算上限'
  print '7  新建问题论文文件夹'
  print '8  构建并打包当前论文'
  print '9  打开并行任务进度面板'
  print '10  连接 Undermind 文献研究'
  print '11  Google Scholar 人工核验'
  print '12  导出给其他模型的接管包'
  print '13  检查是否可以发布到 GitHub'
  print '0  退出'
  print '────────────────────────────────────────────────────────────'
  read 'CHOICE?请选择：'

  case "$CHOICE" in
    1)
      "$PROJECT_DIR/启动研究面板.command"
      wait_for_key
      ;;
    2)
      ;;
    3)
      "$PYTHON" tools/check_mcp_agents.py --skip-lean-build
      wait_for_key
      ;;
    4)
      (cd -- "$PROJECT_DIR/formal" && lake build)
      wait_for_key
      ;;
    5)
      "$PYTHON" -m ai4math_gateway.cli --config config/gateway.yaml status
      wait_for_key
      ;;
    6)
      "$PROJECT_DIR/调整预算.command"
      ;;
    7)
      "$PROJECT_DIR/新建论文项目.command"
      ;;
    8)
      "$PROJECT_DIR/构建当前论文.command"
      ;;
    9)
      "$PROJECT_DIR/打开并行任务面板.command"
      ;;
    10)
      "$PROJECT_DIR/连接Undermind.command"
      ;;
    11)
      "$PROJECT_DIR/Google Scholar人工核验.command"
      ;;
    12)
      "$PROJECT_DIR/导出模型交接包.command"
      ;;
    13)
      "$PROJECT_DIR/检查GitHub发布.command"
      ;;
    0)
      exit 0
      ;;
    *)
      print '请输入 0—13。'
      sleep 1
      ;;
  esac
done
