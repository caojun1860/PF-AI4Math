# GitHub 发布与克隆恢复

## 推荐发布边界

首次发布建议使用私有仓库，确认论文正文和实验材料的公开范围后再改为公开。
仓库可包含工作流代码、Agent、Skill、配置模板、测试和自有研究文本。以下内容保持本地：

- API Key、OAuth 会话、`.env` 与 macOS 钥匙串内容；
- Zotero 数据库、原始附件和受版权限制的 PDF；
- `.venv/`、`.runtime/`、Lean `.lake/` 和构建缓存；
- `papers/*/deliverables/` 等可重新生成的交付包。

发布前运行 `检查GitHub发布.command`。它会阻止已跟踪版本中的常见凭据、个人绝对路径、PDF、数据库和构建文件。

## 创建远端仓库

在 GitHub 创建一个空仓库，不要让网页自动添加 README、`.gitignore` 或许可证。然后在项目根目录执行：

```bash
git remote add origin <GitHub 仓库地址>
git push -u origin main
```

若已经存在 `origin`，先用 `git remote -v` 核对地址。公开前还应为原创代码选择许可证；第三方 Skill 的来源和固定版本见 `THIRD_PARTY_NOTICES.md` 与 `config/skills-lock.json`。

## 克隆后恢复

另一台机器取得仓库后：

1. 安装 Git、Python 3.12、uv、OpenCode、Lean 4 与 `lean-lsp-mcp`；
2. 在项目根目录运行 `uv sync --frozen`，恢复 Python 环境；
3. 按 `README.md` 配置豆包密钥，本机重新完成 Zotero 和 Undermind 授权；
4. 运行 `检查MCP与Agent.command`，确认 PDF、文献检索、Zotero 与 Lean；
5. 运行测试，再通过 `AI4Math控制台.command` 打开研究面板。

`.runtime/` 中的 PDF 和文献搜索辅助环境不会进入 Git，需要按项目安装说明在每台机器上重新建立。只需让另一个模型阅读研究状态时，可以直接使用 `.handoff/` 中的交接 ZIP，无需恢复全部工具链。

## 多模型协作

每个模型使用单独的分支或 worktree，例如 `model/doubao-topic-a`、`model/kimi-review`。各分支把结果写入独立报告或证据文件，由总控 Agent 审查后合并。`state/current.md` 与论文主文件应指定单一写入者，避免并发覆盖。
