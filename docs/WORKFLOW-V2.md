# AI4Math 多智能体研究工作流 V2

## 一次研究的默认流程

1. 总控为研究问题创建 `papers/<问题短名>/`，写入问题、题目和基础 LaTeX 结构。
2. `literature-reader` 搜索本地 Zotero；`scholarly-searcher` 同时搜索 OpenAlex、Semantic Scholar、arXiv 和 Crossref。Undermind 登录后作为深度检索和引文追踪补充。
3. 多篇候选论文由多个 `paper-reader` 并行深读。普通 PDF 用 MarkItDown；扫描件、公式和版面定位用 LiteParse/OCR 与页面截图。
4. 数学推导、符号反例和必要的 Lean 检验可与论文深读并行。每个结果标记为严格证明、文献支持、计算支持、候选路线或未验证。
5. `proof-reviewer` 与 `citation-auditor` 分别检查证明和引用支持关系。失败项建立新一次尝试，旧结果保留。
6. `literature-synthesizer` 和 `research-writer` 在上游通过后形成正文，总控写入 `sections/`、`references.bib` 和 `evidence/`。
7. 总控调用构建工具，`deliverables/` 生成 PDF、TeX、源文件 ZIP 和 `manifest.json`。

## 并行任务与反馈

OpenCode Ensemble 默认最多同时运行三个 Agent，首批先启动两个；任务板用依赖关系控制顺序。适合并行的是不同数据源检索、不同论文深读、互不依赖的证明路线和独立审查；综合与最终写作必须等待输入齐全。

浏览器面板位于 `http://127.0.0.1:4747`，显示每个 Agent 的状态、当前任务、耗时、消息、任务依赖和完成进度。在总控对话中可以：

- 暂停或恢复新任务派发；
- 调整未开始任务的内容和优先级；
- 给正在运行的 Agent 发送补充要求；
- 对失败或证据不足的节点创建新一次尝试；
- 调整总问题后保留仍然有效的已完成节点。

所有研究 Agent 使用同一豆包预算网关。网关最多放行两个模型请求，并以六秒间隔平滑启动；排队和长思考期间每十五秒发送一次连接心跳。豆包触发请求突增保护时，网关最多四次指数退避重试。证明漏洞、缺少 PDF、权限或预算问题进入等待处理状态。

## PDF 和论文目录

```text
papers/<问题短名>/
  question.yaml
  main.tex
  sections/
  figures/
  sources/
  parsed/
  references.bib
  evidence/
  build/
  deliverables/
    <问题短名>.pdf
    <问题短名>.tex
    <问题短名>-source.zip
    manifest.json
```

本地 PDF 只允许从项目、Documents、Downloads、Desktop、Zotero 存储或临时附件目录读取；解析结果只能写入对应问题文件夹。MarkItDown 的云端转换与第三方插件未启用。

## 文献源边界

- OpenAlex、Semantic Scholar、arXiv 和 Crossref：自动、只读、结构化发现。
- Undermind：官方远程 MCP，需一次浏览器 OAuth；用于深度搜索、引文追踪和并行全文阅读。
- Zotero：本地只读元数据与已索引全文。
- Google Scholar：没有公开的官方批量 API，只提供人工核验入口。
- 付费墙：不绕过。全文来自合法开放链接或用户有权提供的文件。

## 常用入口

- `AI4Math控制台.command`：统一菜单。
- `启动研究面板.command`：启动预算网关、OpenCode 和并行进度面板。
- `连接Undermind.command`：完成一次 OAuth。
- `新建论文项目.command`：建立默认问题目录。
- `构建当前论文.command`：编译并打包可下载成果。
- `Google Scholar人工核验.command`：打开人工查询。
