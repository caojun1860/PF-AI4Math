"""Read-only terminal status panel for the local AI4Math workspace."""

from __future__ import annotations

import json
import sqlite3
import subprocess
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
SAFE_TOKENS = 40_000
SAFE_CNY = 0.05
SAFE_REQUESTS = 4


def bar(used: float, limit: float, width: int = 24) -> str:
    ratio = 1.0 if limit <= 0 else min(1.0, max(0.0, used / limit))
    filled = round(width * ratio)
    return "█" * filled + "░" * (width - filled)


def budget_status(config: dict[str, Any]) -> dict[str, Any]:
    database = Path(config["server"]["database"])
    if not database.is_absolute():
        database = ROOT / database
    connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        row = connection.execute(
            "SELECT * FROM budgets WHERE id = ?", (config["budget"]["id"],)
        ).fetchone()
    finally:
        connection.close()
    if row is None:
        raise RuntimeError("预算账本尚未初始化")
    value = dict(row)
    value["used_cny"] = value["used_cny_nano"] / 1_000_000_000
    value["reserved_cny"] = value["reserved_cny_nano"] / 1_000_000_000
    value["cny_limit"] = value["cny_limit_nano"] / 1_000_000_000
    value["available_tokens"] = (
        value["token_limit"] - value["used_tokens"] - value["reserved_tokens"]
    )
    value["available_cny"] = (
        value["cny_limit"] - value["used_cny"] - value["reserved_cny"]
    )
    value["available_requests"] = (
        value["request_limit"] - value["used_requests"] - value["reserved_requests"]
    )
    return value


def agent_rows() -> list[tuple[str, str, str]]:
    rows = []
    for path in sorted((ROOT / ".opencode" / "agents").glob("*.md")):
        text = path.read_text(encoding="utf-8")
        header = yaml.safe_load(text.split("---", 2)[1])
        rows.append((path.stem, header["mode"], header["model"].split("/", 1)[-1]))
    return rows


def git_status() -> tuple[str, str]:
    head = subprocess.check_output(
        ["git", "log", "-1", "--format=%h %s"], cwd=ROOT, text=True
    ).strip()
    dirty = subprocess.check_output(
        ["git", "status", "--porcelain"], cwd=ROOT, text=True
    ).strip()
    return head, "有未提交修改" if dirty else "工作区干净"


def active_paper() -> str:
    path = ROOT / ".runtime" / "active-paper.json"
    if not path.exists():
        return "尚未建立"
    try:
        slug = json.loads(path.read_text(encoding="utf-8"))["slug"]
        return f"papers/{slug}"
    except (KeyError, ValueError, OSError):
        return "状态文件需修复"


def main() -> None:
    config = yaml.safe_load((ROOT / "config" / "gateway.yaml").read_text(encoding="utf-8"))
    opencode = json.loads((ROOT / "opencode.json").read_text(encoding="utf-8"))
    budget = budget_status(config)
    head, worktree = git_status()

    print("┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓")
    print("┃                 AI4Math 本地研究状态                    ┃")
    print("┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛")
    print(f"\nGit    {head} · {worktree}")
    print(f"总控   {opencode['default_agent']} · 质量模式 / 豆包高总额度")
    print(f"并行   Ensemble · 默认 3 个，面板 http://127.0.0.1:4747")
    print(f"论文   {active_paper()}")

    token_used = budget["used_tokens"] + budget["reserved_tokens"]
    cny_used = budget["used_cny"] + budget["reserved_cny"]
    request_used = budget["used_requests"] + budget["reserved_requests"]
    print("\n预算")
    print(
        f"Token  [{bar(token_used, budget['token_limit'])}] "
        f"{token_used:,}/{budget['token_limit']:,}，可用 {budget['available_tokens']:,}"
    )
    print(
        f"金额   [{bar(cny_used, budget['cny_limit'])}] "
        f"¥{cny_used:.6f}/¥{budget['cny_limit']:.2f}"
    )
    print(
        f"请求   [{bar(request_used, budget['request_limit'])}] "
        f"{request_used}/{budget['request_limit']}，可用 {budget['available_requests']}"
    )

    safe = (
        budget["available_tokens"] >= SAFE_TOKENS
        and budget["available_cny"] >= SAFE_CNY
        and budget["available_requests"] >= SAFE_REQUESTS
    )
    print(f"启动   {'允许' if safe else '已锁定：余额低于安全线'}")

    print("\n模型角色（context / output）")
    for name, route in config["models"].items():
        print(
            f"  {name:<10} {route['max_context_tokens']:>6,} / "
            f"{route['max_output_tokens']:>4,}  → 豆包"
        )

    print("\nAgent")
    for name, mode, model in agent_rows():
        print(f"  {name:<24} {mode:<7} {model}")

    print("\nMCP")
    for name, server in opencode["mcp"].items():
        print(f"  {name:<16} {'已配置' if server.get('enabled') else '已停用'}")

    print("\n本地能力")
    capabilities = {
        "PDF 转 Markdown": ROOT / ".runtime" / "pdf-tools" / "bin" / "markitdown",
        "PDF OCR / 页面图": ROOT / ".runtime" / "pdf-tools" / "bin" / "lit",
        "库外文献搜索": ROOT / ".runtime" / "paper-search" / "bin" / "paper-search-mcp",
    }
    for label, path in capabilities.items():
        print(f"  {label:<18} {'已安装' if path.exists() else '缺失'}")

    print("\n建议")
    if safe:
        print("  可启动研究面板；独立子任务默认最多三个并行运行。")
    else:
        print("  继续使用本地 Python、Lean、Git、MCP 检查；暂不启动模型。")


if __name__ == "__main__":
    main()
