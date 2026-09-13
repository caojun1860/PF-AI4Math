# AI4Math 模型接管说明

本项目把研究状态保存在文件中，不依赖某一次聊天记录。任何能够读取本地目录、运行命令或连接 MCP 的大语言模型，都可以从同一状态继续工作。

## 接管顺序

新模型开始工作时依次读取：

1. `AGENTS.md`：研究规则、证据标准和权限边界；
2. `state/current.md`：当前判断、进度和下一步；
3. `tasks/` 与 `research/questions/`：任务目标和验收条件；
4. `papers/*/question.yaml`、`sections/` 与 `evidence/`：每个论文问题的正文和证据；
5. `reports/`：已经完成的推导、综述、验证与审查；
6. `config/skills-lock.json` 与 `.opencode/agents/`：能力版本和角色分工。

聊天记录不是权威状态。若聊天内容与上述文件冲突，以最新文件、可复现实验和人工确认结果为准。

## 推荐接管提示词

```text
你正在接管一个已有的 AI4Math 本地研究项目。请先读取 AGENTS.md、
MODEL-HANDOFF.md、state/current.md、tasks/、research/questions/，再检查
papers/ 和 reports/ 中已有成果。不要重复已经完成的任务，不要把猜想标成
证明。先报告：当前目标、已完成内容、证据等级、未完成节点和你准备执行的
下一步。所有新结果继续写回原有目录结构。
```

## 同机接管

让新的 Agent 工具把此仓库作为工作目录打开即可。豆包、DeepSeek、Kimi、GPT 或本地模型只负责推理；项目文件、Git、MCP 和验证工具保持不变。若新工具支持 OpenAI-compatible API，可在 `config/gateway.yaml` 中增加一个独立路由，并为该供应商设置独立预算。

“豆包本地模式”可能指豆包桌面端读取本地文件，也可能指通过 OpenCode 在本机操作文件并调用豆包云端 API。本项目支持后一种方式；若某个客户端只能上传文件，请使用“导出模型交接包.command”生成脱敏 ZIP 后再交给它。

## 多模型同时工作

- 每个模型使用独立 Git 分支或 worktree；
- 同一时刻只指定一个 Agent 写入 `state/current.md` 和论文主文件；
- 其他 Agent 输出到独立报告或证据文件；
- 汇总 Agent 审查后再合并，避免两个模型覆盖同一段 LaTeX；
- 密钥只放环境变量、macOS 钥匙串或模型工具自己的凭据存储中。

## 跨机器接管

运行：

```bash
.venv/bin/python tools/export_handoff.py
```

输出位于 `.handoff/`。ZIP 包含可继续研究的文本、代码和配置，并附带 SHA-256 清单；不包含 `.env`、`.runtime`、本地数据库、OAuth 凭据、PDF 原件和构建缓存。

如果另一台机器需要完整运行工具链，而不只是阅读项目内容，请按
`GITHUB-PUBLISHING.md` 的“克隆后恢复”步骤安装本机运行时。密钥和 OAuth 授权不会随 Git 或交接包迁移，需要在新机器重新配置。
