# PF-AI4Math — AI4Math 本地多智能体研究工作流

PF-AI4Math 是一个**本地、模型无关**的 AI4Math 多智能体研究工作流。它用 OpenCode 提供交互面板，通过本地预算网关连接豆包或其他 OpenAI-compatible 模型，并组合 Git、Zotero、PDF 解析、文献检索、Python、Lean 和 LaTeX，把数学研究的文献发现、路线推导、形式化验证、论文成文与审查组织成可复现、可移交的流水线。

## 架构

```
上游模型（豆包 / OpenAI 兼容）
        │
        ▼
本地预算网关  ai4math_gateway/   FastAPI · 127.0.0.1:4001 · SQLite 预算账本
        │                        并发保护 · 错峰启动 · 失败重试 · 供应商白名单
        ▼
OpenCode 12-Agent 编排  .opencode/agents/   Ensemble 面板 http://127.0.0.1:4747
        │
        ▼
最小权限本地 MCP  ai4math_mcp/   PDF 深读 · 文献检索 · Zotero · Lean · Python 计算
        │
        ▼
文件化研究产物  papers/ · formal/ · reports/ · state/ · tasks/（默认不入库）
```

## 隐私边界（重要）

本仓库**只公开工作流框架，不公开使用者产生的科研成果**。以下目录默认被 Git 忽略：

`papers/`、`paper/`、`reports/`、`state/`、`tasks/`、`research/`、`experiments/`、`literature/`、`formal/`、`.handoff/`

API Key、OAuth 会话、Zotero 数据库、PDF 原件、`.venv/`、`.runtime/`、`.opencode/node_modules/` 不会进入 Git。密钥只写入 macOS 钥匙串或本机 `.env`（`.env` 不提交，仓库仅保留 `.env.example` 模板）。发布边界、建库步骤与克隆恢复方法见 [`GITHUB-PUBLISHING.md`](GITHUB-PUBLISHING.md)。

## 目录结构（框架部分）

| 路径 | 作用 |
|---|---|
| `ai4math_gateway/` | 本地预算网关：角色路由、并发保护、硬预算、SQLite 账本 |
| `ai4math_mcp/` | 本地 MCP 服务：PDF、文献、Zotero、Lean、Python 工具 |
| `tools/` | 维护脚本：发布检查、MCP/Agent 自检、论文构建、交接包导出 |
| `tests/` | 单元测试 |
| `config/` | 网关预算、供应商路由模板、Skill 版本锁定 |
| `.opencode/agents/` | 12 个专业 Agent 定义 |
| `.opencode/skills/` | 锁定版本的第三方 Skill（来源见 `THIRD_PARTY_NOTICES.md`） |
| `.opencode/ensemble.json` | OpenCode Ensemble 面板配置 |
| `.github/workflows/ci.yml` | CI：uv 同步 + 单元测试 + 发布检查 |
| `docs/`、`templates/` | 工作流文档与结果模板 |
| `*.command` | macOS 双击启动脚本（控制台、面板、密钥配置、检查等） |
| `AGENTS.md` | 项目治理规则（证据分级、不读写凭据、不擅自 push 等） |
| `MODEL-HANDOFF.md` | 多模型交接与协作规范 |
| `pyproject.toml` / `uv.lock` | Python 依赖锁定 |

## 安装

1. 安装 Git、Python 3.12、`uv`、Node.js（OpenCode 运行时）；可选安装 Lean 4 与 `lean-lsp-mcp`。
2. 在项目根目录运行 `uv sync --frozen`，恢复 Python 环境。
3. 进入 `.opencode/` 运行 `npm install`，恢复 OpenCode 插件依赖。
4. 双击「配置豆包网关密钥.command」，把 `ARK_API_KEY` 写入 macOS 钥匙串（与 OpenCode 已存凭据相互独立）。
5. 双击「检查MCP与Agent.command」，做一次完全本地的能力复查（不消耗 token）。
6. 双击「AI4Math控制台.command」进入总菜单。

## 快速开始

控制台把 Agent 面板、本地状态、MCP 检查、Lean 构建和预算管理放在同一菜单。选择“打开 Agent 研究面板”并通过预算闸门后，默认进入 `research-orchestrator` 总控 Agent；按 `Tab` 可在十二个专业角色间切换，总控会把相互独立的文献发现、PDF 深读、数学路线和审查任务并行派发。OpenCode Ensemble 在 `http://127.0.0.1:4747` 显示 Agent 卡片、任务依赖、完成进度、消息与时间线。

新建研究问题使用「新建论文项目.command」，它会在 `papers/<问题短名>/` 下建立 LaTeX、证据、文献与交付物目录（该目录默认不入库）。

## 十二个专业 Agent

`research-orchestrator`（总控）、`math-deriver`（路线推导）、`proof-reviewer`（证明审查）、`lean-verifier`（形式化）、`symbolic-checker`（符号计算）、`literature-reader`（文献深读）、`literature-synthesizer`（文献综合）、`scholarly-searcher`（检索）、`paper-reader`（论文阅读）、`citation-auditor`（引用审计）、`manuscript-reviewer`（成稿审查）、`research-writer`（成文）。

## 预算与并发

模型与预算路由位于 [`config/gateway.yaml`](config/gateway.yaml)，跨供应商模板位于 `config/provider-route.example.yaml`。默认预算为 100,000,000 token / 200 元 / 500 次请求，供应商白名单 `openai/doubao-`，并发上限 2、启动错峰 6 秒、失败重试 4 次。研究面板启动前会检查剩余额度，为首批并行任务和最终汇总预留空间。

## 多模型协作

本工作流设计为可被多个模型依次或并行管理。交接规范见 [`MODEL-HANDOFF.md`](MODEL-HANDOFF.md)：每个模型使用独立 Git 分支或 worktree（如 `model/doubao-topic-a`），结果写入独立报告或证据文件，由总控审查后合并；`state/current.md` 与论文主文件在同一时间只允许一个写入者，避免并发覆盖。

## 测试与发布检查

```bash
uv run python -m unittest discover -v     # 单元测试
python3 tools/github_release_check.py      # 发布前凭据/路径/文件类型检查
```

CI（`.github/workflows/ci.yml`）在每次 push 时自动运行上述两项。

## 许可

本仓库原创部分未授予开源许可证，保留全部权利。第三方组件仍适用各自的许可证与版权声明，详见 [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) 与 `config/skills-lock.json`。未经明确许可，不得公开或再分发本工作流产生的科研任务产品。
