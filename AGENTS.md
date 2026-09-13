# AI4Math 项目规则

- 明确数学对象、假设与目标；数值实验不能当作一般证明。
- 使用中文交流，保留数学符号和必要的英文术语。
- 通过本地预算网关调用模型；当前豆包专用总上限为 100,000,000 token、人民币 200 元估算和 500 次请求。达到任一上限立即停止，不自动发起长期循环任务。
- 引用必须能够定位原文；缺少原文时写明缺失。
- 不读取或输出凭据文件，不把密钥和完整会话日志提交到 Git。
- 修改前读取 state/current.md；结果写入 reports/，并更新研究状态。
- 交付说明结论、证据位置、实际执行的检查、未解决问题和下一步。
- 验证标签区分猜想、实验支持、证明草稿、人工审查、Lean 检查通过。
- Git 提交前检查范围；发布、远程推送和 Overleaf 同步需要用户指示。

## 模型路由与预算

- `fast`、`reasoning`、`reader`、`reviewer` 是稳定研究角色名；`utility` 只承担标题生成等内部轻任务。供应商映射位于 config/gateway.yaml。
- 所有自动编排必须走 `ai4math-gateway`。`doubao-ark` 直接入口绕过本地账本，只用于人工故障排查。
- 当前启用豆包质量模式：总控使用 `reasoning`；简单任务直接处理，复杂研究最多按依赖顺序委派五个专业 Agent，不自动循环。
- 未经完整证明加独立审查、精确文献定理位置或 Lean 同命题核验，不得把科研结论标为“已证明”或使用绿色勾选。
- 高总额度由 `allowed_provider_prefixes` 锁定到 `openai/doubao-`。接入 GPT、Kimi、DeepSeek 等路由前必须另设预算，不得沿用豆包高额度。
- 账本只记录模型别名、token、费用估算、状态和时间，不记录 prompt 或回复正文。
- 上游失败、流式中断或缺少 usage 时按预留上限保守结算；是否重置由用户决定。
- 金额是按配置单价计算的本地估算，以供应商账单为准；调整预算使用 `.venv/bin/python -m ai4math_gateway.cli set` 或“调整预算.command”。

## Zotero 只读文献入口

- Zotero 运行且本地 API 启用时，可运行 `.venv/bin/python tools/zotero_read.py search "关键词"`，每次最多10条。
- 查看已选条目：`.venv/bin/python tools/zotero_read.py item UP6AQ5UP`；附件目录用 `children`。仅支持 GET，不提供文献库写入。
- 附件记录不等于本地文件存在；全文引用必须核对实际文件、版本和页码，索引文本不能可靠提供页码。
- 第一张演示证据卡位于 literature/notes/treil-evidence.md。条目键与 BibTeX 引用键不同。
- OpenCode 使用 `zotero_local` MCP；它没有写入工具，索引全文单次最多返回 20,000 字符且不提供本地附件路径。只需识别引用时优先使用 `zotero_get_citation_metadata`，它只返回 key、标题、作者、日期、DOI 和 URL。
- 将 Zotero 工具结果交给外部模型前，需要用户明确允许发送本次选中的元数据或文本；纯本地 MCP 检查不需要模型。

## Agent 编排

- `research-orchestrator` 是主 Agent；其余十一个角色覆盖推导、计算、文献发现、Zotero 阅读、单篇深读、跨文献综合、引用审计、Lean、证明审查、稿件审查和研究写作，均为单层子 Agent。
- 复杂研究单轮最多依次委派五个子 Agent，按依赖顺序执行；子 Agent 禁止编辑文件和继续委派。
- 项目内 GitHub skills 必须固定提交并记录在 `config/skills-lock.json`；第三方 skill 的网络、脚本和外部模型依赖只有在项目权限中明确开放后才能使用。
- `literature-reader` 自动允许最小引用元数据工具，其他 Zotero 读取操作逐次询问；`lean-verifier` 只允许项目 `formal/` 范围内的 Lean MCP；其余角色默认不使用 MCP。
- 首轮任务读取 `tasks/T001-agent-workflow-pilot.md`，至少为总控汇总保留 8,000 token。
