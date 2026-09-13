# PF-AI4Math

PF-AI4Math 是一个本地、模型无关的 AI4Math 多智能体研究工作流。它使用 OpenCode 提供交互面板，通过本地网关连接豆包或其他 OpenAI-compatible 模型，并组合 Git、Zotero、PDF 解析、文献搜索、Python、Lean 和 LaTeX。

## 隐私边界

本仓库公开工作流框架，不公开使用者产生的科研任务产品。`papers/`、`reports/`、`state/`、`tasks/`、`research/`、`experiments/`、`literature/` 与 `formal/` 默认被 Git 忽略。只有明确改变忽略规则并单独提交，科研内容才可能进入版本历史。

API Key、OAuth 会话、Zotero 数据库、PDF 原件和本地运行时不会进入 Git。

## 安装

1. 安装 Git、Python 3.12、uv、OpenCode、Lean 4 和 `lean-lsp-mcp`。
2. 运行 `python3 tools/bootstrap.py`，恢复 Python 环境、PDF/检索运行时和固定版本的第三方 Skills。
3. 双击 `配置豆包网关密钥.command`，密钥只写入 macOS 钥匙串。
4. 双击 `检查MCP与Agent.command` 验证本地能力。
5. 通过 `AI4Math控制台.command` 打开研究面板。

模型和预算路由位于 `config/gateway.yaml`；跨供应商模板位于 `config/provider-route.example.yaml`。Agent 定义位于 `.opencode/agents/`，第三方 Skill 来源和固定版本位于 `config/skills-lock.json`。

## 许可

本仓库原创部分未授予开源许可证，保留全部权利。第三方组件仍适用各自的许可证和版权声明，详见 `THIRD_PARTY_NOTICES.md`。未经明确许可，不得公开或再分发本工作流产生的科研任务产品。
